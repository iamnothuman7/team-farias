"""Rotas do projeto Team Farias."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from core import views as core_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("sw.js", core_views.service_worker, name="service_worker"),
    path("", include("core.urls")),
    path("", include("accounts.urls")),
    path("", include("dashboard.urls")),
]

handler403 = "core.views.forbidden"
handler404 = "core.views.not_found"

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
