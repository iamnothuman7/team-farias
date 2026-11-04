"""Private web push: an authenticated reader opens the message in the app."""
import base64
import json
from datetime import timedelta
from urllib.parse import urlsplit

import requests
from cryptography.hazmat.primitives.asymmetric import ec
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from pywebpush import webpush, WebPushException

from .models import Announcement, PushSubscription, PushDelivery


def validate_endpoint(endpoint):
    if not isinstance(endpoint, str) or len(endpoint) > 2048:
        raise ValueError("Endereço de notificação inválido.")
    url = urlsplit(endpoint)
    host = url.hostname or ""
    allowed = host == "fcm.googleapis.com" or any(
        host == domain or host.endswith("." + domain)
        for domain in ("push.services.mozilla.com", "push.apple.com", "notify.windows.com")
    )
    if not allowed or url.scheme != "https" or url.port not in (None, 443) or url.username or url.password or url.fragment:
        raise ValueError("Serviço de notificação não reconhecido.")
    return endpoint


def validate_subscription(data):
    endpoint = validate_endpoint(data["endpoint"])
    keys = data["keys"]
    if not all(isinstance(keys[k], str) and len(keys[k]) <= 128 for k in ("p256dh", "auth")):
        raise ValueError("Chaves inválidas.")
    public = base64.b64decode(keys["p256dh"] + "=" * (-len(keys["p256dh"]) % 4), altchars=b"-_", validate=True)
    auth = base64.b64decode(keys["auth"] + "=" * (-len(keys["auth"]) % 4), altchars=b"-_", validate=True)
    if len(public) != 65 or len(auth) != 16:
        raise ValueError("Chaves inválidas.")
    ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public)
    return endpoint, keys


class PushSession(requests.Session):
    def request(self, method, url, **kwargs):
        validate_endpoint(url)
        kwargs["allow_redirects"] = False
        return super().request(method, url, **kwargs)


def queue_announcements():
    now = timezone.now()
    with transaction.atomic():
        announcements = Announcement.objects.select_for_update(skip_locked=True).filter(
            is_published=True, published_at__lte=now, push_queued_at__isnull=True,
        )
        for announcement in announcements:
            if announcement.audience == Announcement.Audience.ALUNOS:
                subscriptions = PushSubscription.objects.filter(user__is_active=True, user__role="aluno", user__student__status="ativo")
                PushDelivery.objects.bulk_create([
                    PushDelivery(announcement=announcement, subscription=s, user_id=s.user_id)
                    for s in subscriptions
                ], ignore_conflicts=True)
            announcement.push_queued_at = now
            announcement.save(update_fields=["push_queued_at"])


def dispatch(limit=100):
    if not settings.WEBPUSH_PRIVATE_KEY or not settings.WEBPUSH_PUBLIC_KEY:
        return {"configured": False, "sent": 0}
    queue_announcements()
    sent = 0
    for _ in range(limit):
        with transaction.atomic():
            delivery = PushDelivery.objects.select_for_update(skip_locked=True).filter(
                status="pending", next_attempt__lte=timezone.now(),
            ).order_by("pk").first()
            if not delivery:
                break
            subscription, announcement = delivery.subscription, delivery.announcement
            eligible = subscription.user_id == delivery.user_id and subscription.user.is_active and subscription.user.role == "aluno" and hasattr(subscription.user, "student") and subscription.user.student.status == "ativo"
            if not eligible or not announcement.is_published or announcement.audience != "alunos" or announcement.published_at > timezone.now():
                delivery.status = "cancelled"
                delivery.save(update_fields=["status"])
                continue
            delivery.attempts += 1
            try:
                # No private title or body is shown on the lock screen.
                with PushSession() as session:
                    session.trust_env = False
                    response = webpush(
                        subscription_info={"endpoint": validate_endpoint(subscription.endpoint), "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth}},
                        data=json.dumps({"url": announcement.get_absolute_url(), "tag": f"notice-{announcement.pk}"}),
                        vapid_private_key=settings.WEBPUSH_PRIVATE_KEY,
                        vapid_claims={"sub": settings.WEBPUSH_SUBJECT},
                        ttl=86400, timeout=8, requests_session=session,
                    )
                    if not 200 <= response.status_code < 300:
                        raise ValueError("Unexpected status")
                delivery.status = "sent"
                delivery.sent_at = timezone.now()
                delivery.last_code = "accepted"
                sent += 1
            except (WebPushException, requests.RequestException, ValueError, OSError) as exc:
                response = getattr(exc, "response", None)
                code = response.status_code if response is not None else None
                if code in (404, 410):
                    subscription.delete()
                    continue
                delivery.last_code = str(code or "delivery_error")
                delivery.status = "failed" if delivery.attempts >= 5 else "pending"
                delivery.next_attempt = timezone.now() + timedelta(minutes=2 ** delivery.attempts)
            delivery.save()
    return {"configured": True, "sent": sent}
