from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("noticias/", views.news_list, name="news_list"),
    path("noticias/<slug:slug>/", views.news_detail, name="news_detail"),
    # A matrícula agora é feita pela administração. Mantém redirecionamento para links antigos.
    path("matricula/", views.enroll_redirect, name="enroll"),
    path("matricula/enviada/", views.enroll_redirect, name="enroll_success"),
    path("privacidade/", views.privacy, name="privacy"),
    path("offline/", views.offline, name="offline"),
    path("health/", views.health, name="health"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
]
