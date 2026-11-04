import json

from django.conf import settings
from django.db import transaction, IntegrityError
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.cache import never_cache

from school.models import PushSubscription
from school.push import validate_subscription, validate_endpoint
from .decorators import student_required


@student_required
@require_GET
@never_cache
def configuration(request):
    return JsonResponse({"publicKey": settings.WEBPUSH_PUBLIC_KEY, "configured": bool(settings.WEBPUSH_PRIVATE_KEY and settings.WEBPUSH_PUBLIC_KEY)})


@student_required
@require_POST
@never_cache
def subscription(request):
    if len(request.body) > 4096:
        return JsonResponse({"error": "Dados muito grandes."}, status=400)
    try:
        data = json.loads(request.body)
        if data.get("action") == "remove":
            endpoint = validate_endpoint(data.get("endpoint"))
            PushSubscription.objects.filter(user=request.user, endpoint=endpoint).delete()
            request.session.pop("push_subscription_id", None)
            return JsonResponse({"enabled": False})
        endpoint, keys = validate_subscription(data)
    except (ValueError, KeyError, TypeError, AttributeError):
        return JsonResponse({"error": "Não foi possível reconhecer este aparelho."}, status=400)
    if not settings.WEBPUSH_PRIVATE_KEY or not settings.WEBPUSH_PUBLIC_KEY:
        return JsonResponse({"error": "Notificações ainda não configuradas."}, status=503)
    if request.user.student.status != "ativo":
        return JsonResponse({"error": "A conta precisa estar ativa."}, status=403)
    try:
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            obj = PushSubscription.objects.select_for_update().filter(endpoint=endpoint).first()
            if obj and obj.user_id != request.user.pk:
                return JsonResponse({"error": "Desative a inscrição antiga neste aparelho e tente novamente."}, status=409)
            if not obj and request.user.push_subscriptions.count() >= 10:
                return JsonResponse({"error": "Limite de aparelhos atingido. Fale com a equipe."}, status=400)
            if obj:
                obj.p256dh, obj.auth = keys["p256dh"], keys["auth"]
                obj.save(update_fields=["p256dh", "auth", "updated_at"])
            else:
                obj = PushSubscription.objects.create(endpoint=endpoint, user=request.user, p256dh=keys["p256dh"], auth=keys["auth"])
    except IntegrityError:
        return JsonResponse({"error": "Este aparelho já foi vinculado. Tente novamente."}, status=409)
    request.session["push_subscription_id"] = obj.pk
    return JsonResponse({"enabled": True})
