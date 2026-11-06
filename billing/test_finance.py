from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from billing.finance import finance_movements, finance_summary, save_financial_entry
from billing.models import FinancialCategory, FinancialEntry, FinancialEvent, Invoice, Payment
from core.testing import make_admin, make_invoice, make_student


class FinanceFixture:
    def setUp(self):
        self.today = date(2026, 11, 5)
        self.clock = patch("django.utils.timezone.localdate", return_value=self.today)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.user = make_admin()
        self.income = FinancialCategory.objects.create(name="Receita de teste", kind="income")
        self.expense = FinancialCategory.objects.create(name="Despesa de teste", kind="expense")

    def entry(self, **kwargs):
        values = dict(kind="expense", category=self.expense, description="Aluguel da quadra", amount=Decimal("250.00"), due_date=self.today)
        values.update(kwargs)
        return save_financial_entry(FinancialEntry(**values), user=self.user)


class FinanceEntryTests(FinanceFixture, TestCase):

    def test_creation_audit_and_submission_idempotency(self):
        key = uuid4()
        first = self.entry(submission_key=key)
        duplicate = self.entry(submission_key=key)
        self.assertEqual(first.pk, duplicate.pk)
        self.assertEqual(FinancialEntry.objects.count(), 1)
        self.assertEqual(first.events.count(), 1)
        event = first.events.get()
        self.assertEqual(event.action, "created")
        self.assertEqual(event.actor, self.user)
        self.assertEqual(event.details["after"]["amount"], "250.00")

    def test_settle_reopen_cancel_recover_and_repeated_actions(self):
        entry = self.entry()
        entry.settle(user=self.user, date=self.today, method="pix")
        entry.settle(user=self.user, date=self.today, method="pix")
        self.assertEqual(entry.status, "settled")
        self.assertEqual(entry.events.filter(action="settled").count(), 1)
        with self.assertRaises(ValidationError):
            entry.cancel(user=self.user)
        entry.reopen(user=self.user)
        entry.reopen(user=self.user)
        self.assertEqual(entry.status, "pending")
        self.assertIsNone(entry.settled_at)
        self.assertEqual(entry.method, "")
        entry.cancel(user=self.user)
        entry.cancel(user=self.user)
        self.assertEqual(entry.status, "cancelled")
        with self.assertRaises(ValidationError):
            entry.settle(user=self.user, method="pix")
        entry.reopen(user=self.user)
        self.assertEqual(entry.status, "pending")
        self.assertEqual(list(entry.events.order_by("pk").values_list("action", flat=True)), ["created", "settled", "reopened", "cancelled", "reopened"])

    def test_reused_form_cannot_silently_discard_different_values(self):
        key = uuid4()
        first = self.entry(submission_key=key)
        first.settle(user=self.user, method="pix")
        self.assertEqual(self.entry(submission_key=key).pk, first.pk)
        with self.assertRaisesMessage(ValidationError, "já foi usado"):
            self.entry(submission_key=key, amount=Decimal("10.00"))
        self.assertEqual(FinancialEntry.objects.count(), 1)

    def test_edit_pending_preserves_audit_and_rejects_stale_version(self):
        entry = self.entry()
        stale = FinancialEntry.objects.get(pk=entry.pk)
        entry.description = "Aluguel corrigido"
        entry.amount = Decimal("230.00")
        saved = save_financial_entry(entry, user=self.user, expected_updated_at=entry.updated_at)
        event = saved.events.get(action="updated")
        self.assertEqual(event.details["before"]["amount"], "250.00")
        self.assertEqual(event.details["after"]["amount"], "230.00")
        stale.amount = Decimal("9.00")
        with self.assertRaisesMessage(ValidationError, "outra janela"):
            save_financial_entry(stale, user=self.user, expected_updated_at=stale.updated_at)
        saved.refresh_from_db()
        self.assertEqual(saved.amount, Decimal("230.00"))

    def test_noop_edit_does_not_add_history(self):
        entry = self.entry()
        save_financial_entry(entry, user=self.user)
        self.assertEqual(entry.events.count(), 1)

    def test_edit_realized_requires_reopening(self):
        entry = self.entry(status="settled", settled_at=self.today, method="dinheiro")
        entry.amount = Decimal("100.00")
        with self.assertRaisesMessage(ValidationError, "Reabra"):
            save_financial_entry(entry, user=self.user)
        entry.refresh_from_db()
        self.assertEqual(entry.amount, Decimal("250.00"))

    def test_invalid_amount_category_future_or_method_are_rejected(self):
        for changes in ({"amount": 0}, {"amount": -1}, {"category": self.income}, {"description": "   "}, {"status": "cancelled"}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.entry(**changes)
        entry = self.entry()
        for method, day in (("unknown", self.today), ("", self.today), ("pix", self.today + timedelta(days=1))):
            with self.subTest(method=method, day=day), self.assertRaises(ValidationError):
                entry.settle(user=self.user, date=day, method=method)
        entry.refresh_from_db()
        self.assertEqual(entry.status, "pending")
        self.assertEqual(entry.events.count(), 1)

    def test_database_rejects_zero_and_inconsistent_settlement(self):
        for changes in ({"amount": 0}, {"status": "settled"}, {"settled_at": self.today}, {"kind": "other"}):
            with self.subTest(changes=changes), self.assertRaises(IntegrityError):
                with transaction.atomic():
                    values = dict(kind="expense", category=self.expense, description="Inválido", amount=Decimal("1.00"), due_date=self.today)
                    values.update(changes)
                    FinancialEntry.objects.create(**values)

    def test_inactive_category_can_remain_on_edit_but_cannot_receive_new_entry(self):
        entry = self.entry()
        self.expense.is_active = False
        self.expense.save()
        with self.assertRaises(ValidationError):
            self.entry()
        entry.description = "Descrição atualizada"
        self.assertEqual(save_financial_entry(entry, user=self.user).description, "Descrição atualizada")

    def test_category_type_and_deletion_protected_after_use(self):
        self.entry()
        self.expense.kind = "income"
        with self.assertRaises(ValidationError):
            self.expense.full_clean()
        with self.assertRaises(ProtectedError):
            self.expense.delete()

    def test_event_and_entry_deletion_protected(self):
        entry = self.entry()
        event = entry.events.get()
        event.action = "updated"
        with self.assertRaises(ValidationError):
            event.save()
        with self.assertRaises(ValidationError):
            event.delete()
        with self.assertRaises(ProtectedError):
            entry.delete()


class FinanceReportTests(FinanceFixture, TestCase):
    def test_summary_combines_cash_and_tuition_without_duplicates(self):
        previous = date(2026, 10, 31)
        self.entry(kind="income", category=self.income, amount=Decimal("1000.00"), status="settled", settled_at=previous, method="pix")
        self.entry(amount=Decimal("100.00"), status="settled", settled_at=previous, method="dinheiro")
        self.entry(kind="income", category=self.income, amount=Decimal("50.00"), status="settled", settled_at=self.today, method="pix")
        self.entry(amount=Decimal("70.00"), status="settled", settled_at=self.today, method="pix")
        cancelled = self.entry(amount=Decimal("999.00"))
        cancelled.cancel(user=self.user)
        self.entry(amount=Decimal("40.00"), due_date=date(2026, 11, 20))
        self.entry(amount=Decimal("30.00"), due_date=date(2026, 11, 1))
        self.entry(kind="income", category=self.income, amount=Decimal("90.00"), due_date=date(2026, 11, 1))
        paid = make_invoice(make_student(), fee="200.00")
        paid.discount = Decimal("20.00")
        paid.save()
        paid.mark_paid(user=self.user, method="pix")
        make_invoice(make_student(email="pending@example.test"), fee="120.00", days_overdue=1)
        # A competência antiga não impede a entrada na data em que foi recebida.
        paid.competence = date(2026, 10, 1)
        paid.save()
        result = finance_summary(date(2026, 11, 1), date(2026, 11, 30))
        expected = dict(opening_balance="900.00", tuition_income="180.00", other_income="50.00", income="230.00", expenses="70.00", net="160.00", closing_balance="1060.00", pending_income="210.00", pending_expenses="70.00", overdue_income="210.00", overdue_expenses="30.00")
        for key, amount in expected.items():
            with self.subTest(key=key):
                self.assertEqual(result[key], Decimal(amount))
        self.assertEqual(result["expense_categories"], [{"category__name": "Despesa de teste", "total": Decimal("70.00")}])
        paid.reopen()
        reopened = finance_summary(date(2026, 11, 1), date(2026, 11, 30))
        self.assertEqual(reopened["income"], Decimal("50.00"))
        self.assertEqual(reopened["pending_income"], Decimal("390.00"))
        self.assertEqual(Payment.objects.count(), 0)

    def test_future_realized_legacy_data_excluded_but_future_pending_included(self):
        future = date(2026, 11, 20)
        legacy = self.entry(amount=Decimal("50.00"))
        FinancialEntry.objects.filter(pk=legacy.pk).update(status="settled", settled_at=future, method="pix")
        self.entry(amount=Decimal("25.00"), due_date=future)
        invoice = make_invoice(make_student(), fee="150.00")
        invoice.mark_paid(method="pix", paid_at=future)
        summary = finance_summary(date(2026, 11, 1), date(2026, 11, 30))
        self.assertEqual(summary["income"], Decimal("0.00"))
        self.assertEqual(summary["expenses"], Decimal("0.00"))
        self.assertEqual(summary["pending_expenses"], Decimal("25.00"))
        self.assertEqual(len(finance_movements(date(2026, 11, 1), date(2026, 11, 30))), 1)

    def test_movements_filters_tuition_states_categories_and_search(self):
        pending = self.entry(counterparty="Fornecedor da areia", due_date=date(2026, 11, 1))
        income = self.entry(kind="income", category=self.income, description="Camisa treino", status="settled", settled_at=self.today, method="cartao")
        paid = make_invoice(make_student(), fee="180.00")
        paid.mark_paid(method="pix")
        open_invoice = make_invoice(make_student(email="open@example.test"), fee="100.00", days_overdue=1)
        start, end = date(2026, 11, 1), date(2026, 11, 30)
        rows = finance_movements(start, end)
        self.assertEqual(len(rows), 4)
        self.assertEqual(len(finance_movements(start, end, kind="expense")), 1)
        self.assertEqual(len(finance_movements(start, end, category="tuition")), 2)
        self.assertEqual(len(finance_movements(start, end, status="settled")), 2)
        self.assertEqual(len(finance_movements(start, end, status="overdue")), 2)
        self.assertEqual(finance_movements(start, end, category=str(self.income.pk))[0]["id"], income.pk)
        self.assertEqual(finance_movements(start, end, q="areia")[0]["id"], pending.pk)
        row = next(row for row in rows if row["source"] == "payment")
        self.assertEqual(row["invoice"], paid)
        self.assertEqual(row["method"], "Pix")
        self.assertEqual(row["method_key"], "pix")
        self.assertEqual(next(row for row in rows if row["source"] == "invoice")["invoice"], open_invoice)
        for bad in (dict(category="invalid"), dict(category="9" * 30), dict(kind="wrong"), dict(status="wrong")):
            self.assertEqual(finance_movements(start, end, **bad), [])

    def test_empty_period_is_decimal_zero_and_date_range_validated(self):
        summary = finance_summary(date(2026, 11, 1), date(2026, 11, 30))
        for key in ("income", "expenses", "opening_balance", "closing_balance", "pending_income", "pending_expenses"):
            self.assertEqual(summary[key], Decimal("0.00"))
        with self.assertRaises(ValueError):
            finance_summary(date(2026, 12, 1), date(2026, 11, 1))
