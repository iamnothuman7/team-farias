from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.models import Student
from billing.models import Invoice, Payment
from core.testing import make_group, make_invoice, make_plan, make_student


class InvoiceModelTests(TestCase):
    def setUp(self):
        self.plan = make_plan(due_day=10)
        self.group = make_group()
        self.student = make_student(group=self.group, plan=self.plan)

    def test_total_applies_discount(self):
        invoice = make_invoice(self.student, fee="200.00")
        invoice.discount = Decimal("30.00")
        self.assertEqual(invoice.total, Decimal("170.00"))

    def test_overdue_flag(self):
        overdue = make_invoice(self.student, days_overdue=5)
        self.assertTrue(overdue.is_overdue)
        self.assertEqual(overdue.situacao, "Vencida")
        self.assertEqual(overdue.situacao_key, "vencida")

    def test_mark_paid_creates_payment_and_reopen_removes_it(self):
        invoice = make_invoice(self.student)
        invoice.mark_paid(method=Invoice.Method.PIX, paid_at=timezone.localdate())
        self.assertEqual(invoice.status, Invoice.Status.PAGA)
        self.assertEqual(Payment.objects.filter(invoice=invoice).count(), 1)
        self.assertFalse(invoice.is_overdue)

        invoice.reopen()
        self.assertEqual(invoice.status, Invoice.Status.ABERTA)
        self.assertEqual(invoice.payments.count(), 0)

    def test_competence_label(self):
        invoice = make_invoice(self.student)
        self.assertEqual(invoice.competence_label, f"{['janeiro','fevereiro','março','abril','maio','junho','julho','agosto','setembro','outubro','novembro','dezembro'][invoice.competence.month-1].capitalize()}/{invoice.competence.year}")


class InvoiceGenerationTests(TestCase):
    def test_generate_only_active_enrollments_and_idempotent(self):
        from dashboard.services import generate_invoices

        plan = make_plan()
        group = make_group()
        active = make_student(email="ativo@exemplo.com", group=group, plan=plan)
        pending = make_student(email="pendente@exemplo.com", status=Student.Status.PENDENTE)

        competence = timezone.localdate().replace(day=1)
        created = generate_invoices(competence)
        self.assertEqual(created, 1)
        self.assertTrue(Invoice.objects.filter(student=active, competence=competence).exists())
        self.assertFalse(Invoice.objects.filter(student=pending, competence=competence).exists())

        self.assertEqual(generate_invoices(competence), 0)


class FinanceOverviewTests(TestCase):
    def test_overview_totals(self):
        from dashboard.services import finance_overview

        plan = make_plan()
        group = make_group()
        student = make_student(group=group, plan=plan)
        competence = timezone.localdate().replace(day=1)
        paid = make_invoice(student)
        paid.mark_paid(method=Invoice.Method.PIX)
        other = make_student(email="b@exemplo.com", group=group, plan=plan)
        make_invoice(other)

        overview = finance_overview(competence)
        self.assertEqual(overview["count"], 2)
        self.assertEqual(overview["paid"], Decimal("180.00"))
        self.assertEqual(overview["open"], Decimal("180.00"))
        self.assertEqual(overview["paid_rate"], 50)
