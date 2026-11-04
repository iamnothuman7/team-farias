"""Regression audit: role boundaries, enrollment, finance and private notifications."""
import base64
import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch, Mock

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone

from billing.models import Plan, Invoice
from core.testing import make_admin, make_professor, make_group, make_plan, make_student, make_session, make_invoice
from dashboard.forms import AdminEnrollmentForm, InvoiceForm, SessionForm, ScheduleSlotForm
from dashboard.services import finance_overview, generate_invoices
from school.models import Announcement, Enrollment, PushSubscription, PushDelivery, Session
from school.push import dispatch, queue_announcements, validate_endpoint


class WorkflowAuditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = make_admin()
        cls.professor = make_professor()
        cls.other_professor = make_professor(email="other@example.test")
        cls.plan = make_plan()
        cls.second_plan = make_plan(name="Treino extra", fee="270.00")
        cls.group = make_group(professor=cls.professor)
        cls.other_group = make_group(name="Outra turma", professor=cls.other_professor)
        cls.student = make_student(group=cls.group, plan=cls.plan)
        cls.other_student = make_student(email="other-student@example.test", group=cls.other_group, plan=cls.second_plan)
        cls.session = make_session(cls.group)
        cls.other_session = make_session(cls.other_group)
        cls.announcement = Announcement.objects.create(title="Recado reservado", body="Somente alunos", audience="alunos")

    def test_get_route_matrix_by_role_and_htmx(self):
        admin_only = ["plans", "plan_create", "enrollments", "enrollment_create", "billing", "settings", "reports", "announcement_create", "class_create"]
        team = ["painel", "students", "classes", "sessions", "session_create", "points_admin", "announcements_admin"]
        student = ["home", "profile", "points", "agenda", "invoices", "announcements", "password_change"]
        for user, role in [(self.admin,"admin"),(self.professor,"professor"),(self.student.user,"student")]:
            self.client.force_login(user)
            for name in admin_only + team + student + ["help"]:
                expected = 200 if name=="help" or (name in admin_only and role=="admin") or (name in team and role!="student") or (name in student and role=="student") else (403 if name in admin_only+team else 302)
                with self.subTest(role=role, route=name):
                    response=self.client.get(reverse("dashboard:"+name), HTTP_HX_BOOSTED="true")
                    self.assertEqual(response.status_code,expected)
                    if expected==200:
                        self.assertIn("no-store",response["Cache-Control"])
                        self.assertIn("Como usar o sistema",response.content.decode())

    def test_plan_create_edit_deactivate_and_preserve_agreed_price(self):
        self.client.force_login(self.admin)
        data={"name":"Individual", "description":"", "monthly_fee":"350.00", "due_day":"31", "sessions_per_week":"3", "is_active":"on"}
        self.assertEqual(self.client.post(reverse("dashboard:plan_create"),data).status_code,302)
        self.assertEqual(Plan.objects.filter(is_active=True).count(),3)
        data["monthly_fee"]="500.00"; data.pop("is_active")
        self.assertEqual(self.client.post(reverse("dashboard:plan_edit",args=[self.plan.pk]),data).status_code,302)
        self.assertEqual(self.student.active_enrollment.monthly_fee,Decimal("180.00"))
        self.assertNotIn(self.plan,list(AdminEnrollmentForm().fields["plan"].queryset))

    def test_invalid_plan_is_rejected(self):
        self.client.force_login(self.admin)
        for fee,day,frequency in [("-1","10","2"),("100","0","2"),("100","32","2"),("100","10","0")]:
            with self.subTest(fee=fee,day=day,frequency=frequency):
                response=self.client.post(reverse("dashboard:plan_create"),{"name":"Inválido","monthly_fee":fee,"due_day":day,"sessions_per_week":frequency})
                self.assertEqual(response.status_code,200)
                self.assertTrue(response.context["form"].errors)

    def enrollment_data(self):
        return {"first_name":"Atleta", "last_name":"Novo", "email":"new@example.test", "phone":"88999999999", "birth_date":"2000-01-01", "level":"iniciante", "class_group":self.group.pk, "plan":self.second_plan.pk}

    def test_enrollment_selected_plan_and_first_invoice(self):
        self.client.force_login(self.admin)
        response=self.client.post(reverse("dashboard:enrollment_create"),self.enrollment_data())
        self.assertEqual(response.status_code,302)
        enrollment=Enrollment.objects.get(student__user__email="new@example.test")
        self.assertEqual(enrollment.plan,self.second_plan)
        self.assertEqual(enrollment.monthly_fee,Decimal("270.00"))
        self.assertEqual(enrollment.student.invoices.get().amount,Decimal("270.00"))
        self.assertEqual(self.client.get(response["Location"]).status_code,200)
        self.assertEqual(self.client.get(response["Location"]).status_code,302)

    def test_missing_inactive_or_invalid_plan_rejected(self):
        self.second_plan.is_active=False; self.second_plan.save()
        for plan_id in ["",self.second_plan.pk,999999]:
            data=self.enrollment_data();data["plan"]=plan_id
            self.assertFalse(AdminEnrollmentForm(data).is_valid())

    def test_full_group_and_minor_without_guardian_rejected(self):
        data=self.enrollment_data(); data["birth_date"]="2014-01-01"
        self.assertIn("guardian_name",AdminEnrollmentForm(data).errors)
        self.group.capacity=1;self.group.save()
        self.assertIn("class_group",AdminEnrollmentForm(self.enrollment_data()).errors)

    def test_cannot_approve_pending_enrollment_into_full_group(self):
        self.group.capacity=1;self.group.save()
        student=make_student(email="pending@example.test")
        enrollment=Enrollment.objects.create(student=student,class_group=self.group,plan=self.plan,monthly_fee=180)
        self.client.force_login(self.admin)
        self.client.post(reverse("dashboard:enrollments"),{"action":"approve","enrollment":enrollment.pk})
        enrollment.refresh_from_db();self.assertEqual(enrollment.status,"pendente")
        self.assertFalse(student.invoices.exists())

    def test_professor_cannot_read_or_edit_other_session(self):
        self.client.force_login(self.professor)
        url=reverse("dashboard:session_edit",args=[self.other_session.pk])
        self.assertEqual(self.client.get(url).status_code,404)
        self.assertEqual(self.client.post(url,{}).status_code,404)
        self.assertEqual(self.client.get(reverse("dashboard:student_detail",args=[self.other_student.pk])).status_code,403)

    def test_professor_generates_only_own_sessions(self):
        self.client.force_login(self.professor)
        before=Session.objects.filter(class_group=self.other_group).count()
        self.client.post(reverse("dashboard:sessions"),{"action":"generate"})
        self.assertEqual(Session.objects.filter(class_group=self.other_group).count(),before)
        self.assertGreater(Session.objects.filter(class_group=self.group).count(),1)

    def test_professor_cannot_change_student_registration(self):
        self.client.force_login(self.professor)
        response=self.client.post(reverse("dashboard:student_detail",args=[self.student.pk]),{"action":"edit","status":"inativo","level":"iniciante"})
        self.assertEqual(response.status_code,403)

    def test_end_before_start_rejected(self):
        for form in [ScheduleSlotForm({"weekday":1,"start_time":"18:00","end_time":"17:00"}),SessionForm({"class_group":self.group.pk,"date":"2026-11-05","start_time":"18:00","end_time":"17:00","status":"agendado"},user=self.admin)]:
            self.assertIn("end_time",form.errors)

    def test_student_without_group_never_sees_other_calendars(self):
        student=make_student(email="without-group@example.test")
        self.client.force_login(student.user)
        response=self.client.get(reverse("dashboard:agenda"))
        self.assertFalse(any(day["sessions"] for week in response.context["calendar"]["weeks"] for day in week))

    def test_professor_points_only_own_groups(self):
        from school.models import PointEntry
        PointEntry.objects.create(student=self.other_student,points=87,reason="Private other group")
        self.client.force_login(self.professor)
        response=self.client.get(reverse("dashboard:points_admin"))
        self.assertNotContains(response,"Private other group")
        self.assertEqual(response.context["total_points_month"],0)
        self.assertEqual(self.client.get(reverse("dashboard:points_admin"),{"turma":self.other_group.pk}).status_code,404)

    def test_professor_can_read_only_published_team_notices(self):
        notice=Announcement.objects.create(title="Para professores",body="x",audience="interno")
        self.client.force_login(self.professor)
        self.assertContains(self.client.get(reverse("dashboard:announcements_admin")),notice.title)
        self.assertEqual(self.client.get(reverse("dashboard:announcement_team_detail",args=[notice.pk])).status_code,200)
        self.assertEqual(self.client.get(reverse("dashboard:announcement_team_detail",args=[self.announcement.pk])).status_code,404)
        self.assertEqual(self.client.post(reverse("dashboard:announcement_toggle",args=[notice.pk])).status_code,403)

    def test_bad_filters_do_not_cause_server_errors(self):
        self.client.force_login(self.admin)
        for name in ["students","points_admin"]:
            self.assertEqual(self.client.get(reverse("dashboard:"+name),{"turma":"not-a-number"}).status_code,404)
        self.assertEqual(self.client.get(reverse("dashboard:billing"),{"competencia":"9999-12"}).status_code,200)
        self.assertEqual(self.client.get(reverse("dashboard:sessions"),{"inicio":"0001-01-01"}).status_code,200)
        self.assertEqual(self.client.post(reverse("dashboard:billing"),{"action":"pay","invoice":"invalid"}).status_code,404)
        self.client.force_login(self.student.user)
        self.assertEqual(self.client.get(reverse("dashboard:agenda"),{"ano":"999999","mes":"4"}).status_code,200)

    def test_invoice_create_defaults_open_and_normalizes_month(self):
        self.client.force_login(self.admin)
        data={"action":"create","student":self.student.pk,"plan":self.plan.pk,"competence":"2027-02-20","due_date":"2027-02-28","amount":"180","discount":"20"}
        self.assertEqual(self.client.post(reverse("dashboard:billing"),data).status_code,302)
        invoice=self.student.invoices.get()
        self.assertEqual(invoice.status,"aberta")
        self.assertEqual(invoice.competence.day,1)
        self.assertEqual(invoice.total,Decimal("160"))

    def test_invoice_invalid_discount_returns_field_errors(self):
        self.client.force_login(self.admin)
        data={"action":"create","student":self.student.pk,"plan":self.plan.pk,"competence":"2027-02-20","due_date":"2027-02-28","amount":"180","discount":"200"}
        response=self.client.post(reverse("dashboard:billing"),data)
        self.assertEqual(response.status_code,200)
        self.assertIn("discount",response.context["invoice_form"].errors)

    def test_payment_and_monthly_generation_are_idempotent(self):
        invoice=make_invoice(self.student)
        invoice.mark_paid(user=self.admin,method="pix");invoice.mark_paid(user=self.admin,method="pix")
        self.assertEqual(invoice.payments.count(),1)
        generate_invoices(timezone.localdate());generate_invoices(timezone.localdate())
        self.assertEqual(self.student.invoices.count(),1)

    def test_finance_considers_discount(self):
        invoice=make_invoice(self.student);invoice.discount=Decimal("30");invoice.save();invoice.mark_paid(method="pix")
        overview=finance_overview()
        self.assertEqual(overview["billed"],Decimal("150"))
        self.assertEqual(overview["paid"],Decimal("150"))
        self.assertEqual(overview["paid_rate"],100)

    def test_private_future_and_draft_notices(self):
        draft=Announcement.objects.create(title="Rascunho",body="segredo",is_published=False)
        future=Announcement.objects.create(title="Futuro",body="segredo",published_at=timezone.now()+timedelta(days=1))
        internal=Announcement.objects.create(title="Equipe",body="segredo",audience="interno")
        self.assertNotContains(self.client.get("/"),self.announcement.title)
        self.assertEqual(self.client.get("/noticias/").status_code,404)
        self.assertEqual(self.client.get("/noticias/"+self.announcement.slug+"/").status_code,404)
        self.client.force_login(self.student.user)
        for obj in (draft,future,internal):
            self.assertEqual(self.client.get(obj.get_absolute_url()).status_code,404)
        self.assertEqual(self.client.get(self.announcement.get_absolute_url()).status_code,200)


@override_settings(WEBPUSH_PUBLIC_KEY="public-test-key",WEBPUSH_PRIVATE_KEY="private-test-key")
class NotificationAuditTests(TestCase):
    def setUp(self):
        self.student=make_student()
        self.client.force_login(self.student.user)
        public=ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
        self.data={"endpoint":"https://fcm.googleapis.com/fcm/send/test-device","keys":{"p256dh":base64.urlsafe_b64encode(public).decode().rstrip("="),"auth":base64.urlsafe_b64encode(b"1234567890123456").decode().rstrip("=")}}
        self.url=reverse("dashboard:push_subscription")

    def subscribe(self):
        response=self.client.post(self.url,json.dumps(self.data),content_type="application/json")
        self.assertEqual(response.status_code,200)
        return PushSubscription.objects.get()

    def test_subscribe_repeat_and_disable(self):
        self.subscribe();self.subscribe();self.assertEqual(PushSubscription.objects.count(),1)
        response=self.client.post(self.url,json.dumps({"action":"remove","endpoint":self.data["endpoint"]}),content_type="application/json")
        self.assertEqual(response.status_code,200);self.assertFalse(PushSubscription.objects.exists())

    def test_no_cross_account_device_takeover(self):
        sub=self.subscribe();other=make_student(email="second@example.test")
        self.client.force_login(other.user)
        response=self.client.post(self.url,json.dumps(self.data),content_type="application/json")
        self.assertEqual(response.status_code,409);sub.refresh_from_db();self.assertEqual(sub.user_id,self.student.user_id)

    def test_logout_removes_only_current_device(self):
        self.subscribe()
        PushSubscription.objects.create(user=self.student.user,endpoint="https://fcm.googleapis.com/second",p256dh="x",auth="y")
        self.client.post(reverse("accounts:logout"))
        self.assertEqual(PushSubscription.objects.count(),1)
        self.assertTrue(PushSubscription.objects.filter(endpoint__endswith="/second").exists())

    def test_csrf_and_anonymous_protection(self):
        client=Client(enforce_csrf_checks=True);client.force_login(self.student.user)
        self.assertEqual(client.post(self.url,json.dumps(self.data),content_type="application/json").status_code,403)
        self.client.logout();self.assertEqual(self.client.post(self.url,{}).status_code,302)

    def test_endpoint_rejects_ssrf_and_invalid_keys(self):
        for url in ["http://fcm.googleapis.com/a","https://127.0.0.1/a","https://fcm.googleapis.com.attacker.test/a","https://user@fcm.googleapis.com/a","https://fcm.googleapis.com:8443/a"]:
            with self.subTest(url=url),self.assertRaises(ValueError): validate_endpoint(url)
        self.data["keys"]["auth"]="invalid"
        self.assertEqual(self.client.post(self.url,json.dumps(self.data),content_type="application/json").status_code,400)

    @patch("school.push.webpush")
    def test_publish_sends_once_without_private_text(self,send):
        self.subscribe();announcement=Announcement.objects.create(title="Private title",body="Private body")
        send.return_value=Mock(status_code=201)
        self.assertEqual(dispatch()["sent"],1);self.assertEqual(dispatch()["sent"],0)
        send.assert_called_once();payload=send.call_args.kwargs["data"]
        self.assertNotIn("Private",payload);self.assertIn(announcement.get_absolute_url(),payload)

    @patch("school.push.webpush")
    def test_drafts_scheduled_internal_and_inactive_students_not_sent(self,send):
        self.subscribe()
        Announcement.objects.create(title="Draft",body="x",is_published=False)
        Announcement.objects.create(title="Future",body="x",published_at=timezone.now()+timedelta(days=1))
        Announcement.objects.create(title="Staff",body="x",audience="interno")
        dispatch();send.assert_not_called()
        self.student.status="inativo";self.student.save()
        Announcement.objects.create(title="Active students",body="x")
        dispatch();send.assert_not_called()

    @patch("school.push.webpush")
    def test_unpublish_cancels_queued_delivery(self,send):
        self.subscribe();announcement=Announcement.objects.create(title="Notice",body="x")
        queue_announcements();announcement.is_published=False;announcement.save()
        dispatch();send.assert_not_called();self.assertEqual(PushDelivery.objects.get().status,"cancelled")

    @patch("school.push.webpush")
    def test_transport_failure_retries_without_sensitive_error_log(self,send):
        import requests
        self.subscribe();Announcement.objects.create(title="Notice",body="x")
        send.side_effect=requests.Timeout("private endpoint secret")
        dispatch();delivery=PushDelivery.objects.get()
        self.assertEqual(delivery.status,"pending");self.assertEqual(delivery.attempts,1)
        self.assertEqual(delivery.last_code,"delivery_error")
        self.assertGreater(delivery.next_attempt,timezone.now())

    @patch("school.push.webpush")
    def test_expired_endpoint_is_removed(self,send):
        from pywebpush import WebPushException
        self.subscribe();Announcement.objects.create(title="Notice",body="x")
        send.side_effect=WebPushException("gone",response=Mock(status_code=410))
        dispatch();self.assertFalse(PushSubscription.objects.exists())
