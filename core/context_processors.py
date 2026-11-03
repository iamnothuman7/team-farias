from django.conf import settings
from django.utils import timezone


def site(request):
    """Dados de marca, contato e contadores do painel."""
    counts = {}
    user = getattr(request, "user", None)
    if user and user.is_authenticated and user.is_admin_role:
        from billing.models import Invoice
        from school.models import Enrollment

        counts = {
            "pending": Enrollment.objects.filter(status=Enrollment.Status.PENDENTE).count(),
            "overdue": Invoice.objects.filter(
                status=Invoice.Status.ABERTA, due_date__lt=timezone.localdate()
            ).count(),
        }

    return {
        "site": {
            "name": settings.SITE_NAME,
            "tagline": settings.SITE_TAGLINE,
            "phone": settings.SITE_PHONE,
            "whatsapp": settings.SITE_WHATSAPP,
            "email": settings.SITE_EMAIL,
            "instagram": settings.SITE_INSTAGRAM,
            "city": settings.SITE_CITY,
            "state": settings.SITE_STATE,
            "address": settings.SITE_ADDRESS,
            "pix": settings.SITE_PIX_KEY,
        },
        "nav_counts": counts,
        "greeting": _greeting(),
        "today": timezone.localdate(),
        "current_year": timezone.localdate().year,
    }


def _greeting() -> str:
    hour = timezone.localtime().hour
    if hour < 12:
        return "Bom dia"
    if hour < 18:
        return "Boa tarde"
    return "Boa noite"
