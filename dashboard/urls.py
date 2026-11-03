from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("inicio/", views.role_redirect, name="redirect"),
    # ------------------------------------------------------------ área do aluno
    path("app/", views.app_home, name="home"),
    path("app/perfil/", views.app_profile, name="profile"),
    path("app/pontos/", views.app_points, name="points"),
    path("app/agenda/", views.app_agenda, name="agenda"),
    path("app/mensalidades/", views.app_invoices, name="invoices"),
    path("app/comunicados/", views.app_announcements, name="announcements"),
    path("app/comunicados/<int:pk>/", views.app_announcement_detail, name="announcement_detail"),
    path("app/senha/", views.StudentPasswordChangeView.as_view(), name="password_change"),
    # ------------------------------------------------------------ painel da equipe
    path("painel/", views.painel_home, name="painel"),
    path("painel/matriculas/", views.painel_enrollments, name="enrollments"),
    path("painel/matriculas/nova/", views.painel_enrollment_create, name="enrollment_create"),
    path("painel/matriculas/criada/<int:pk>/", views.painel_enrollment_created, name="enrollment_created"),
    path("painel/alunos/", views.painel_students, name="students"),
    path("painel/alunos/<int:pk>/", views.painel_student_detail, name="student_detail"),
    path("painel/turmas/", views.painel_classes, name="classes"),
    path("painel/turmas/nova/", views.painel_class_form, name="class_create"),
    path("painel/turmas/<int:pk>/editar/", views.painel_class_form, name="class_edit"),
    path("painel/agenda/", views.painel_agenda, name="sessions"),
    path("painel/agenda/nova/", views.painel_session_form, name="session_create"),
    path("painel/agenda/<int:pk>/editar/", views.painel_session_form, name="session_edit"),
    path("painel/agenda/<int:pk>/presenca/", views.painel_attendance, name="session_attendance"),
    path("painel/pontos/", views.painel_points, name="points_admin"),
    path("painel/financeiro/", views.painel_billing, name="billing"),
    path("painel/comunicados/", views.painel_announcements, name="announcements_admin"),
    path("painel/comunicados/novo/", views.painel_announcement_form, name="announcement_create"),
    path("painel/comunicados/<int:pk>/editar/", views.painel_announcement_form, name="announcement_edit"),
    path("painel/comunicados/<int:pk>/publicar/", views.painel_announcement_toggle, name="announcement_toggle"),
    path("painel/relatorios/", views.painel_reports, name="reports"),
]
