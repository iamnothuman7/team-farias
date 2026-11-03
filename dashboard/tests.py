from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Student, User
from billing.models import Invoice
from core.testing import (
    make_admin,
    make_group,
    make_invoice,
    make_plan,
    make_professor,
    make_session,
    make_student,
)
from school.models import Attendance, Enrollment, PointEntry, Session


class AccessControlTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = make_admin()
        cls.professor = make_professor()
        cls.plan = make_plan()
        cls.group = make_group(professor=cls.professor)
        cls.student = make_student(group=cls.group, plan=cls.plan)

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(reverse("dashboard:painel"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/entrar/"))

    def test_student_cannot_open_panel(self):
        self.client.force_login(self.student.user)
        response = self.client.get(reverse("dashboard:painel"))
        self.assertEqual(response.status_code, 403)

    def test_professor_cannot_open_enrollments_or_billing(self):
        self.client.force_login(self.professor)
        self.assertEqual(self.client.get(reverse("dashboard:enrollments")).status_code, 403)
        self.assertEqual(self.client.get(reverse("dashboard:billing")).status_code, 403)

    def test_professor_can_open_own_dashboard_and_agenda(self):
        self.client.force_login(self.professor)
        self.assertEqual(self.client.get(reverse("dashboard:painel")).status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard:sessions")).status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard:points_admin")).status_code, 200)

    def test_role_redirect_by_role(self):
        self.client.force_login(self.student.user)
        self.assertRedirects(self.client.get(reverse("dashboard:redirect")), reverse("dashboard:home"))
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.get(reverse("dashboard:redirect")), reverse("dashboard:painel"))


class StudentAreaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = make_admin()
        cls.plan = make_plan()
        cls.group = make_group(professor=cls.admin)
        cls.student = make_student(group=cls.group, plan=cls.plan)
        PointEntry.objects.create(student=cls.student, points=25, reason="Destaque", source=PointEntry.Source.DESEMPENHO)
        PointEntry.objects.create(student=cls.student, points=-5, reason="Ajuste", source=PointEntry.Source.AJUSTE)
        cls.invoice = make_invoice(cls.student)
        make_session(cls.group, days_ago=-2)

    def setUp(self):
        self.client.force_login(self.student.user)

    def test_home_shows_points_and_invoice(self):
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.group.name)
        self.assertEqual(response.context["total_points"], 20)
        self.assertContains(response, "20")

    def test_points_page_and_ranking(self):
        response = self.client.get(reverse("dashboard:points"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Histórico de pontos")
        self.assertEqual(response.context["position"], 1)

    def test_agenda_shows_upcoming_session(self):
        response = self.client.get(reverse("dashboard:agenda"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.group.name)

    def test_invoices_page(self):
        response = self.client.get(reverse("dashboard:invoices"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mensalidades")
        self.assertContains(response, f"{self.invoice.total:.2f}".replace(".", ","))

    def test_profile_update(self):
        response = self.client.post(
            reverse("dashboard:profile"),
            {"nickname": "Aninha", "position": "bloqueio", "health_notes": "", "phone": "(85) 90000-1111"},
        )
        self.assertRedirects(response, reverse("dashboard:profile"))
        self.student.refresh_from_db()
        self.assertEqual(self.student.nickname, "Aninha")
        self.assertEqual(self.student.user.phone, "(85) 90000-1111")


class EnrollmentApprovalTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.plan = make_plan()
        self.group = make_group()
        self.client.force_login(self.admin)

    def _pending(self):
        student = make_student(email="pendente@exemplo.com", status=Student.Status.PENDENTE)
        return Enrollment.objects.create(
            student=student,
            class_group=self.group,
            plan=self.plan,
            status=Enrollment.Status.PENDENTE,
            monthly_fee=Decimal("180.00"),
        )

    def test_approve_activates_enrollment_and_creates_invoice(self):
        enrollment = self._pending()
        response = self.client.post(
            reverse("dashboard:enrollments"),
            {"enrollment": enrollment.pk, "action": "approve", "class_group": self.group.pk, "plan": self.plan.pk},
        )
        self.assertEqual(response.status_code, 302)

        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, Enrollment.Status.ATIVA)
        self.assertEqual(enrollment.student.status, Student.Status.ATIVO)
        self.assertTrue(
            Invoice.objects.filter(student=enrollment.student, competence=timezone.localdate().replace(day=1)).exists()
        )

    def test_reject_deactivates_student(self):
        enrollment = self._pending()
        self.client.post(reverse("dashboard:enrollments"), {"enrollment": enrollment.pk, "action": "reject"})
        enrollment.refresh_from_db()
        enrollment.student.refresh_from_db()
        self.assertEqual(enrollment.status, Enrollment.Status.REJEITADA)
        self.assertEqual(enrollment.student.status, Student.Status.INATIVO)


class AttendanceTests(TestCase):
    def setUp(self):
        self.professor = make_professor()
        self.plan = make_plan()
        self.group = make_group(professor=self.professor)
        self.student = make_student(group=self.group, plan=self.plan)
        self.session = make_session(self.group)
        self.client.force_login(self.professor)

    def test_register_attendance(self):
        response = self.client.post(
            reverse("dashboard:session_attendance", args=[self.session.pk]),
            {f"status_{self.student.pk}": Attendance.Status.PRESENTE, "mark_done": "1"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Attendance.objects.filter(session=self.session, student=self.student).exists())
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, Session.Status.REALIZADO)

    def test_professor_cannot_access_other_group_session(self):
        other = make_group(name="Outra turma", professor=None)
        other_session = make_session(other)
        response = self.client.get(reverse("dashboard:session_attendance", args=[other_session.pk]))
        self.assertEqual(response.status_code, 302)

    def test_admin_can_generate_week_sessions(self):
        self.client.force_login(make_admin())
        response = self.client.post(reverse("dashboard:sessions"), {"action": "generate"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Session.objects.filter(class_group=self.group).exists())


class PointsTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.plan = make_plan()
        self.group = make_group()
        self.student = make_student(group=self.group, plan=self.plan)
        self.client.force_login(self.admin)

    def test_single_entry(self):
        response = self.client.post(
            reverse("dashboard:points_admin"),
            {
                "action": "single",
                "student": self.student.pk,
                "points": 15,
                "reason": "Evolução",
                "source": PointEntry.Source.DESEMPENHO,
                "rule": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.student.total_points, 15)

    def test_bulk_entry_applies_to_group(self):
        make_student(email="outro@exemplo.com", group=self.group, plan=self.plan)
        response = self.client.post(
            reverse("dashboard:points_admin"),
            {
                "action": "bulk",
                "class_group": self.group.pk,
                "points": 10,
                "reason": "Presença no treino",
                "source": PointEntry.Source.PRESENCA,
                "rule": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PointEntry.objects.count(), 2)
        self.assertEqual(PointEntry.objects.first().points, 10)

    def test_rule_creation(self):
        self.client.post(
            reverse("dashboard:points_admin"),
            {"action": "rule", "name": "Atitude", "points": 5, "description": "Boa postura", "is_active": "on"},
        )
        self.assertTrue(self.group.sessions.model._meta.apps.get_model("school", "PointRule").objects.filter(name="Atitude").exists())


class BillingActionTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.plan = make_plan()
        self.group = make_group()
        self.student = make_student(group=self.group, plan=self.plan)
        self.invoice = make_invoice(self.student)
        self.client.force_login(self.admin)

    def test_mark_invoice_paid_creates_payment(self):
        response = self.client.post(
            reverse("dashboard:billing"),
            {"action": "pay", "invoice": self.invoice.pk, "method": Invoice.Method.PIX},
        )
        self.assertEqual(response.status_code, 302)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.PAGA)
        self.assertEqual(self.invoice.payments.count(), 1)

    def test_reopen_invoice(self):
        self.invoice.mark_paid(method=Invoice.Method.PIX)
        self.client.post(reverse("dashboard:billing"), {"action": "reopen", "invoice": self.invoice.pk})
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.ABERTA)
        self.assertEqual(self.invoice.payments.count(), 0)

    def test_generate_month(self):
        competence = (timezone.localdate().replace(day=1) - timedelta(days=40)).replace(day=1)
        response = self.client.post(
            reverse("dashboard:billing"),
            {"action": "generate", "competence": competence.strftime("%Y-%m")},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Invoice.objects.filter(student=self.student, competence=competence).exists())


class AnnouncementAdminTests(TestCase):
    def test_create_announcement(self):
        admin = make_admin()
        self.client.force_login(admin)
        response = self.client.post(
            reverse("dashboard:announcement_create"),
            {
                "title": "Novo horário",
                "summary": "Mudança na turma",
                "body": "A partir de segunda.",
                "kind": "aviso",
                "audience": "publico",
                "is_published": "on",
                "published_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
            },
        )
        self.assertEqual(response.status_code, 302)
        from school.models import Announcement

        self.assertTrue(Announcement.objects.filter(title="Novo horário").exists())


class AdminEnrollmentTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.professor = make_professor()
        self.plan = make_plan()
        self.group = make_group()
        self.client.force_login(self.admin)

    def payload(self, **overrides):
        data = {
            "first_name": "Sofia",
            "last_name": "Ramos",
            "email": "nova@exemplo.com",
            "phone": "(85) 99999-1234",
            "birth_date": (timezone.localdate() - timedelta(days=16 * 365)).isoformat(),
            "level": Student.Level.INICIANTE,
            "position": "defesa",
            "health_notes": "",
            "class_group": self.group.pk,
            "plan": self.plan.pk,
            "guardian_name": "Débora Ramos",
            "guardian_phone": "(85) 98888-1234",
            "guardian_email": "debora@exemplo.com",
            "password": "senhaMuitoForte123",
        }
        data.update(overrides)
        return data

    def test_only_admin_can_open_enrollment_form(self):
        self.assertEqual(self.client.get(reverse("dashboard:enrollment_create")).status_code, 200)
        self.client.force_login(self.professor)
        self.assertEqual(self.client.get(reverse("dashboard:enrollment_create")).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("dashboard:enrollment_create")).status_code, 302)

    def test_creates_active_student_with_invoice(self):
        response = self.client.post(reverse("dashboard:enrollment_create"), self.payload())
        self.assertEqual(response.status_code, 302)

        user = User.objects.get(email="nova@exemplo.com")
        student = Student.objects.get(user=user)
        enrollment = Enrollment.objects.get(student=student)

        self.assertEqual(student.status, Student.Status.ATIVO)
        self.assertEqual(enrollment.status, Enrollment.Status.ATIVA)
        self.assertEqual(enrollment.class_group, self.group)
        self.assertIsNotNone(enrollment.approved_by)
        self.assertTrue(user.check_password("senhaMuitoForte123"))
        self.assertTrue(
            Invoice.objects.filter(student=student, competence=timezone.localdate().replace(day=1)).exists()
        )
        self.assertEqual(response.url, reverse("dashboard:enrollment_created", args=[student.pk]))

    def test_generated_password_is_shown_once(self):
        response = self.client.post(
            reverse("dashboard:enrollment_create"), self.payload(password=""), follow=True
        )
        self.assertEqual(response.status_code, 200)
        credentials = response.context["credentials"]
        self.assertTrue(credentials["password"].startswith("TF"))
        self.assertTrue(credentials["generated"])
        self.assertContains(response, credentials["password"])

        response = self.client.get(reverse("dashboard:enrollment_created", args=[credentials["student_id"]]))
        self.assertEqual(response.status_code, 302)

    def test_duplicate_email_is_blocked(self):
        make_student(email="nova@exemplo.com", group=self.group, plan=self.plan)
        response = self.client.post(reverse("dashboard:enrollment_create"), self.payload())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Já existe uma conta com este e-mail")
        self.assertEqual(Enrollment.objects.filter(student__user__email="nova@exemplo.com").count(), 1)

    def test_minor_requires_guardian(self):
        response = self.client.post(
            reverse("dashboard:enrollment_create"), self.payload(guardian_name="", guardian_phone="")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "informe nome e WhatsApp do responsável")

    def test_public_enrollment_is_gone(self):
        self.client.logout()
        response = self.client.get(reverse("core:enroll"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].endswith("/#contato"))
