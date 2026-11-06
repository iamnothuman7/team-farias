"""Integration coverage for the school's cash management, without bank operations."""
from __future__ import annotations

import csv
import io
import uuid
from datetime import timedelta
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from billing.finance import save_financial_entry
from billing.models import FinancialCategory, FinancialEntry, Invoice
from core.testing import make_admin, make_invoice, make_professor, make_student


class FinanceDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = make_admin()
        cls.professor = make_professor()
        cls.student = make_student()
        cls.income_category = FinancialCategory.objects.create(name="Receita de teste", kind="income")
        cls.expense_category = FinancialCategory.objects.create(name="Despesa de teste", kind="expense")

    def setUp(self):
        self.today = timezone.localdate()
        self.client.force_login(self.admin)

    def url(self, name="finance", entry=None):
        return reverse("dashboard:" + name, kwargs={"pk": entry.pk} if entry else None)

    def entry(self, **changes):
        values = {
            "kind": "expense", "category": self.expense_category,
            "description": "Aluguel da quadra", "amount": Decimal("120.50"),
            "due_date": self.today, "status": "pending",
        }
        values.update(changes)
        return save_financial_entry(FinancialEntry(**values), user=self.admin)

    def payload(self, **changes):
        values = {
            "submission_key": str(uuid.uuid4()), "kind": "expense",
            "category": str(self.expense_category.pk), "description": "Compra de materiais",
            "counterparty": "Fornecedor de teste", "amount": "125.50",
            "due_date": self.today.isoformat(), "status": "pending",
            "settled_at": "", "method": "", "notes": "Bolas de treino",
        }
        values.update(changes)
        return values

    def assert_invalid(self, response, field=None):
        self.assertIn(response.status_code, (200, 400, 409))
        form = response.context["form"]
        self.assertTrue(form.errors)
        if field:
            self.assertIn(field, form.errors)

    def test_all_cash_routes_restrict_students_professors_and_anonymous(self):
        entry = self.entry()
        routes = [
            self.url(), self.url("finance_create"), self.url("finance_detail", entry),
            self.url("finance_edit", entry), self.url("finance_categories"),
            self.url("finance_category_edit", self.expense_category),
        ]
        for user in (self.professor, self.student.user):
            self.client.force_login(user)
            for path in routes:
                with self.subTest(user=user.role, path=path):
                    self.assertEqual(self.client.get(path).status_code, 403)
                    self.assertEqual(self.client.post(path, {}).status_code, 403)
            self.assertEqual(self.client.get(self.url(), {"export": "csv"}).status_code, 403)
        self.client.logout()
        for path in routes:
            with self.subTest(anonymous=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith("/entrar/"))

    def test_creation_and_transitions_require_csrf(self):
        entry = self.entry()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        before = FinancialEntry.objects.count()
        self.assertEqual(client.post(self.url("finance_create"), self.payload()).status_code, 403)
        self.assertEqual(client.post(self.url("finance_detail", entry), {
            "action": "settle", "date": self.today.isoformat(), "method": "pix",
        }).status_code, 403)
        self.assertEqual(FinancialEntry.objects.count(), before)
        entry.refresh_from_db()
        self.assertEqual(entry.status, "pending")

    def test_pending_creation_is_audited_and_repeated_submission_is_idempotent(self):
        data = self.payload()
        first = self.client.post(self.url("finance_create"), data)
        self.assertEqual(first.status_code, 302)
        entry = FinancialEntry.objects.get(submission_key=data["submission_key"])
        self.assertEqual(entry.amount, Decimal("125.50"))
        self.assertEqual(entry.created_by, self.admin)
        self.assertEqual(entry.status, "pending")
        self.assertEqual(entry.events.count(), 1)
        second = self.client.post(self.url("finance_create"), data)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(first["Location"], second["Location"])
        self.assertEqual(FinancialEntry.objects.filter(submission_key=data["submission_key"]).count(), 1)
        self.assertEqual(entry.events.count(), 1)

    def test_create_already_received_and_pending_does_not_count_in_cash(self):
        data = self.payload(kind="income", category=str(self.income_category.pk),
                            status="settled", settled_at=self.today.isoformat(), method="pix")
        self.assertEqual(self.client.post(self.url("finance_create"), data).status_code, 302)
        self.entry(amount=Decimal("35.00"))
        response = self.client.get(self.url(), {"start": self.today, "end": self.today})
        summary = response.context["summary"]
        self.assertEqual(summary["income"], Decimal("125.50"))
        self.assertEqual(summary["expenses"], Decimal("0.00"))
        self.assertEqual(summary["pending_expenses"], Decimal("35.00"))

    def test_brazilian_decimal_comma_is_saved_without_changing_the_amount(self):
        data = self.payload(amount="125,50")
        self.assertEqual(self.client.post(self.url("finance_create"), data).status_code, 302)
        entry = FinancialEntry.objects.get(submission_key=data["submission_key"])
        self.assertEqual(entry.amount, Decimal("125.50"))

    def test_empty_post_exposes_required_field_errors_and_never_creates_entry(self):
        before = FinancialEntry.objects.count()
        response = self.client.post(self.url("finance_create"), {}, HTTP_HX_REQUEST="true")
        self.assert_invalid(response, "description")
        self.assertEqual(FinancialEntry.objects.count(), before)

    def test_invalid_amount_category_or_settlement_never_creates_entry(self):
        invalid = [
            ({"amount": "0"}, "amount"),
            ({"amount": "-1"}, "amount"),
            ({"amount": "10000000000.00"}, "amount"),
            ({"amount": "12.345"}, "amount"),
            ({"category": str(self.income_category.pk)}, "category"),
            ({"status": "settled", "method": "pix"}, "settled_at"),
            ({"status": "settled", "settled_at": self.today.isoformat()}, "method"),
            ({"status": "settled", "settled_at": (self.today + timedelta(days=1)).isoformat(), "method": "pix"}, "settled_at"),
        ]
        before = FinancialEntry.objects.count()
        for changes, field in invalid:
            with self.subTest(changes=changes):
                self.assert_invalid(self.client.post(self.url("finance_create"), self.payload(**changes)), field)
        self.assertEqual(FinancialEntry.objects.count(), before)

    def test_get_cannot_settle_or_cancel_and_post_transition_is_idempotent(self):
        entry = self.entry()
        url = self.url("finance_detail", entry)
        for action in ("settle", "cancel", "reopen"):
            self.assertEqual(self.client.get(url, {"action": action}).status_code, 200)
            entry.refresh_from_db()
            self.assertEqual(entry.status, "pending")
        data = {"action": "settle", "date": self.today.isoformat(), "method": "dinheiro"}
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(self.client.post(url, data).status_code, 302)
        entry.refresh_from_db()
        self.assertEqual(entry.status, "settled")
        self.assertEqual(entry.method, "dinheiro")
        self.assertEqual(entry.events.filter(action="settled").count(), 1)

    def test_future_settlement_date_keeps_pending_and_displays_the_error(self):
        entry = self.entry()
        response = self.client.post(self.url("finance_detail", entry), {
            "action": "settle", "date": (self.today + timedelta(days=1)).isoformat(), "method": "pix",
        }, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertIn("date", response.context["settle_form"].errors)
        entry.refresh_from_db()
        self.assertEqual(entry.status, "pending")
        self.assertIsNone(entry.settled_at)
        self.assertFalse(entry.events.filter(action="settled").exists())

    def test_cancel_and_reopen_preserve_entry_and_history(self):
        entry = self.entry()
        url = self.url("finance_detail", entry)
        self.assertEqual(self.client.post(url, {"action": "cancel"}).status_code, 302)
        entry.refresh_from_db()
        self.assertEqual(entry.status, "cancelled")
        response = self.client.get(self.url(), {"start": self.today, "end": self.today})
        self.assertEqual(response.context["summary"]["pending_expenses"], 0)
        self.assertEqual(self.client.post(url, {"action": "reopen"}).status_code, 302)
        entry.refresh_from_db()
        self.assertEqual(entry.status, "pending")
        self.assertEqual(set(entry.events.values_list("action", flat=True)), {"created", "cancelled", "reopened"})

    def test_reopening_paid_expense_reverses_cash_without_erasing_history(self):
        entry = self.entry(status="settled", settled_at=self.today, method="pix")
        url = self.url("finance_detail", entry)
        self.client.post(url, {"action": "cancel"})
        entry.refresh_from_db()
        self.assertEqual(entry.status, "settled", "A paid entry must be reopened before cancellation.")
        self.assertEqual(self.client.post(url, {"action": "reopen"}).status_code, 302)
        entry.refresh_from_db()
        self.assertEqual(entry.status, "pending")
        self.assertIsNone(entry.settled_at)
        self.assertEqual(entry.method, "")
        summary = self.client.get(self.url(), {"start": self.today, "end": self.today}).context["summary"]
        self.assertEqual(summary["expenses"], 0)
        self.assertEqual(summary["pending_expenses"], entry.amount)
        self.assertTrue(entry.events.filter(action="reopened").exists())

    def test_settled_entry_cannot_be_edited_by_posting_directly(self):
        entry = self.entry(status="settled", settled_at=self.today, method="pix")
        data = self.payload(description="Tentativa de alterar valor pago", amount="999.00",
                            submission_key=str(entry.submission_key), version=entry.updated_at.isoformat())
        self.client.post(self.url("finance_edit", entry), data)
        entry.refresh_from_db()
        self.assertEqual(entry.amount, Decimal("120.50"))
        self.assertEqual(entry.description, "Aluguel da quadra")

    def test_pending_edit_tracks_change_and_stale_form_cannot_overwrite_it(self):
        entry = self.entry()
        data = self.payload(submission_key=str(entry.submission_key), version=entry.updated_at.isoformat(),
                            description="Aluguel conferido", amount="140.00")
        url = self.url("finance_edit", entry)
        self.assertEqual(self.client.post(url, data).status_code, 302)
        entry.refresh_from_db()
        self.assertEqual(entry.amount, Decimal("140.00"))
        self.assertTrue(entry.events.filter(action="updated").exists())
        data["amount"] = "999.00"
        response = self.client.post(url, data)
        self.assert_invalid(response)
        entry.refresh_from_db()
        self.assertEqual(entry.amount, Decimal("140.00"))

    def test_archived_category_cannot_be_used_for_new_entry_but_existing_can_be_edited(self):
        entry = self.entry()
        self.expense_category.is_active = False
        self.expense_category.save()
        self.assert_invalid(self.client.post(self.url("finance_create"), self.payload()), "category")
        response = self.client.post(self.url("finance_edit", entry), self.payload(
            submission_key=str(entry.submission_key), version=entry.updated_at.isoformat(),
            description="Despesa antiga revisada"))
        self.assertEqual(response.status_code, 302)
        entry.refresh_from_db()
        self.assertEqual(entry.description, "Despesa antiga revisada")

    def test_category_can_be_created_archived_and_cannot_change_kind_when_used(self):
        self.assertEqual(self.client.post(self.url("finance_categories"), {
            "name": "Arbitragem", "kind": "expense", "is_active": "on",
        }).status_code, 302)
        category = FinancialCategory.objects.get(name="Arbitragem")
        self.entry(category=category)
        url = self.url("finance_category_edit", category)
        self.assert_invalid(self.client.post(url, {"name": "Arbitragem", "kind": "income", "is_active": "on"}))
        category.refresh_from_db()
        self.assertEqual(category.kind, "expense")
        self.assertEqual(self.client.post(url, {"name": "Arbitragem", "kind": "expense"}).status_code, 302)
        category.refresh_from_db()
        self.assertFalse(category.is_active)

    def test_cash_uses_payment_date_once_and_monthly_reopen_updates_summary(self):
        invoice = make_invoice(self.student, fee="180.00")
        invoice.competence = (self.today.replace(day=1) - timedelta(days=1)).replace(day=1)
        invoice.save()
        invoice.mark_paid(user=self.admin, paid_at=self.today, method="pix")
        self.entry(kind="income", category=self.income_category, amount=Decimal("40.00"),
                   status="settled", settled_at=self.today, method="pix")
        self.entry(amount=Decimal("25.00"), status="settled", settled_at=self.today, method="pix")
        query = {"start": self.today.isoformat(), "end": self.today.isoformat()}
        response = self.client.get(self.url(), query)
        summary = response.context["summary"]
        self.assertEqual(summary["income"], Decimal("220.00"))
        self.assertEqual(summary["expenses"], Decimal("25.00"))
        self.assertEqual(summary["net"], Decimal("195.00"))
        rows = response.context["page_obj"].object_list
        self.assertEqual(sum(1 for row in rows if row["source"] == "payment"), 1)
        self.client.post(reverse("dashboard:billing"), {"action": "reopen", "invoice": invoice.pk})
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.ABERTA)
        summary = self.client.get(self.url(), query).context["summary"]
        self.assertEqual(summary["income"], Decimal("40.00"))
        self.assertEqual(summary["pending_income"], Decimal("180.00"))

    def test_filters_limit_list_but_do_not_misrepresent_period_summary(self):
        income = self.entry(kind="income", category=self.income_category, description="Venda de camisa",
                            amount=Decimal("60.00"), status="settled", settled_at=self.today, method="pix")
        self.entry(description="Material", amount=Decimal("10.00"), status="settled", settled_at=self.today, method="pix")
        response = self.client.get(self.url(), {"start": self.today, "end": self.today, "kind": "income", "q": "camisa"})
        rows = response.context["page_obj"].object_list
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], income.pk)
        self.assertEqual(response.context["summary"]["expenses"], Decimal("10.00"))

    def test_invalid_range_and_category_do_not_produce_csv(self):
        queries = [
            {"start": "not-a-date", "end": self.today.isoformat()},
            {"start": self.today.isoformat(), "end": (self.today - timedelta(days=1)).isoformat()},
            {"start": (self.today - timedelta(days=400)).isoformat(), "end": self.today.isoformat()},
            {"category": "not-a-category"},
        ]
        for query in queries:
            with self.subTest(query=query):
                response = self.client.get(self.url(), {**query, "export": "csv"})
                self.assertNotIn("text/csv", response.get("Content-Type", ""))
                self.assertTrue(response.context["filter_form"].errors)

    def test_csv_export_matches_filters_and_escapes_spreadsheet_formulas(self):
        self.entry(kind="income", category=self.income_category, description='=HYPERLINK("example.invalid")',
                   counterparty="@formula", amount=Decimal("60.25"), status="settled", settled_at=self.today, method="pix")
        self.entry(description="Não exportar despesa", amount=Decimal("10.00"))
        response = self.client.get(self.url(), {
            "start": self.today, "end": self.today, "kind": "income", "export": "csv",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("no-store", response["Cache-Control"])
        content = b"".join(response.streaming_content) if response.streaming else response.content
        self.assertTrue(content.startswith(b"\xef\xbb\xbf"))
        rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(len(rows), 2)
        cells = rows[1]
        self.assertIn("'=HYPERLINK(\"example.invalid\")", cells)
        self.assertIn("'@formula", cells)
        self.assertIn("60,25", cells)
        self.assertNotIn("Não exportar despesa", content.decode())

    def test_financial_badge_counts_overdue_invoices_and_manual_commitments(self):
        make_invoice(self.student, days_overdue=1)
        self.entry(due_date=self.today - timedelta(days=1))
        self.entry(due_date=self.today + timedelta(days=1))
        paid = self.entry(due_date=self.today - timedelta(days=1))
        paid.settle(user=self.admin, method="pix")
        response = self.client.get(self.url())
        self.assertEqual(response.context["nav_counts"]["overdue"], 2)

    def test_stale_settlement_popup_shows_message_if_entry_was_cancelled(self):
        entry = self.entry()
        entry.cancel(user=self.admin)
        response = self.client.post(self.url("finance_detail", entry), {
            "action": "settle", "date": self.today.isoformat(), "method": "pix",
        }, follow=True)
        self.assertContains(response, "Reabra o lançamento cancelado")
        entry.refresh_from_db()
        self.assertEqual(entry.status, "cancelled")
