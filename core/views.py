from __future__ import annotations

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache

from accounts.models import Student
from billing.models import Plan
from school.models import Announcement, ClassGroup, ScheduleSlot, Session


def _public_groups():
    return (
        ClassGroup.objects.filter(is_active=True)
        .select_related("professor", "venue")
        .prefetch_related("slots", "enrollments")
        .order_by("category", "name")
    )


def _public_announcements():
    return Announcement.objects.filter(is_published=True, audience=Announcement.Audience.PUBLICO)


CATEGORY_ORDER = {"sub13": 0, "sub15": 1, "sub17": 2, "livre": 3, "adulto": 4}


def home(request):
    groups = sorted(_public_groups(), key=lambda g: (CATEGORY_ORDER.get(g.category, 9), g.name))
    plans = list(Plan.objects.filter(is_active=True).order_by("monthly_fee"))
    news = list(_public_announcements()[:3])
    today = timezone.localdate()
    from dashboard.services import ranking

    top = ranking()[:1]
    context = {
        "leader": top[0] if top else None,
        "groups": groups,
        "plans": plans,
        "news": news,
        "stats": {
            "students": Student.objects.filter(status=Student.Status.ATIVO).count(),
            "groups": len(groups),
            "weekly_sessions": ScheduleSlot.objects.filter(class_group__is_active=True).count(),
            "sessions_month": Session.objects.filter(date__year=today.year, date__month=today.month).count(),
        },
        "next_session": Session.objects.filter(date__gte=today, status=Session.Status.AGENDADO)
        .select_related("class_group", "venue")
        .order_by("date", "start_time")
        .first(),
        "featured": news[0] if news else None,
    }
    return render(request, "core/home.html", context)


def news_list(request):
    announcements = _public_announcements()
    kind = request.GET.get("tipo")
    if kind in dict(Announcement.Kind.choices):
        announcements = announcements.filter(kind=kind)
    context = {
        "announcements": announcements,
        "active_kind": kind or "",
        "kinds": Announcement.Kind.choices,
    }
    return render(request, "core/news_list.html", context)


def news_detail(request, slug):
    announcement = get_object_or_404(_public_announcements(), slug=slug)
    related = _public_announcements().exclude(pk=announcement.pk)[:3]
    return render(request, "core/news_detail.html", {"announcement": announcement, "related": related})


def enroll_redirect(request):
    """A matrícula passou a ser feita pela administração. Mantém o link antigo vivo."""
    messages.info(
        request,
        "As matrículas do Team Farias são feitas pela equipe. Fale com a gente para entrar na areia.",
    )
    return redirect(f"{reverse('core:home')}#contato")


def privacy(request):
    return render(request, "core/privacy.html")


def offline(request):
    return render(request, "core/offline.html")


@never_cache
def service_worker(request):
    """Service worker na raiz para controlar todo o escopo do site."""
    response = HttpResponse(
        render_to_string("core/sw.js", {"version": "v4"}),
        content_type="application/javascript",
    )
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response


def health(request):
    return HttpResponse("ok", content_type="text/plain")


def forbidden(request, exception=None):
    return render(request, "errors/403.html", status=403)


def not_found(request, exception=None):
    return render(request, "errors/404.html", status=404)
