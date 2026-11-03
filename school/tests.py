from __future__ import annotations


from django.test import TestCase
from django.utils import timezone

from accounts.models import Student
from core.testing import make_group, make_plan, make_session, make_student
from school.models import Attendance, Enrollment, PointEntry, Session


class SessionGenerationTests(TestCase):
    def test_generates_sessions_from_schedule_without_duplicates(self):
        from dashboard.services import generate_sessions

        group = make_group(slot_weekday=timezone.localdate().weekday())
        created = generate_sessions(weeks=2)
        self.assertGreaterEqual(created, 2)
        self.assertEqual(created, Session.objects.filter(class_group=group).count())
        self.assertEqual(generate_sessions(weeks=2), 0)


class RankingTests(TestCase):
    def test_ranking_orders_by_points(self):
        from dashboard.services import ranking

        plan = make_plan()
        group = make_group()
        ana = make_student(email="ana@exemplo.com", group=group, plan=plan)
        bia = make_student(email="bia@exemplo.com", group=group, plan=plan)
        PointEntry.objects.create(student=ana, points=10, reason="x")
        PointEntry.objects.create(student=bia, points=30, reason="y")

        rows = ranking()
        self.assertEqual([r["student"].pk for r in rows], [bia.pk, ana.pk])
        self.assertEqual(rows[0]["position"], 1)
        self.assertEqual(rows[0]["points"], 30)

    def test_ranking_can_scope_by_group(self):
        from dashboard.services import ranking

        plan = make_plan()
        group_a = make_group(name="A")
        group_b = make_group(name="B")
        make_student(email="a@exemplo.com", group=group_a, plan=plan)
        make_student(email="b@exemplo.com", group=group_b, plan=plan)
        self.assertEqual(len(ranking(group_a)), 1)


class AttendanceModelTests(TestCase):
    def test_attendance_rate_and_occupancy(self):
        plan = make_plan()
        group = make_group(capacity=4)
        student = make_student(group=group, plan=plan)
        session = make_session(group, status=Session.Status.REALIZADO)
        Attendance.objects.create(session=session, student=student, status=Attendance.Status.PRESENTE)

        self.assertEqual(session.confirmed_count, 1)
        self.assertEqual(session.attendance_rate, 100)
        self.assertEqual(group.occupied, 1)
        self.assertEqual(group.free_spots, 3)
        self.assertEqual(group.occupancy_pct, 25)


class EnrollmentModelTests(TestCase):
    def test_approve_sets_student_active_and_guardian(self):
        from accounts.models import Guardian

        plan = make_plan()
        group = make_group()
        guardian = Guardian.objects.create(name="Débora", phone="(85) 99999-0000")
        student = make_student(status=Student.Status.PENDENTE)
        student.guardian = guardian
        student.save()

        enrollment = Enrollment.objects.create(
            student=student, class_group=group, plan=plan, monthly_fee=plan.monthly_fee
        )
        admin = make_student(email="admin2@exemplo.com").user
        enrollment.approve(admin)

        student.refresh_from_db()
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, Enrollment.Status.ATIVA)
        self.assertEqual(student.status, Student.Status.ATIVO)
        self.assertEqual(student.joined_at, timezone.localdate())
