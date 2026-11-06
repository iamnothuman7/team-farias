"""Fluxo de caixa: mensalidades realizadas e lançamentos administrativos.

Mensalidades não são copiadas para o livro manual. A fonte continua sendo Payment,
de modo que uma reabertura imediatamente retire o recebimento do saldo.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from .models import FinancialCategory, FinancialEntry, FinancialEvent, Invoice, Payment


ZERO = Decimal("0.00")
EDITABLE_FIELDS = ("kind", "category_id", "description", "counterparty", "amount", "due_date", "notes")
SNAPSHOT_FIELDS = (*EDITABLE_FIELDS, "status", "settled_at", "method", "is_archived")


def _snapshot(entry):
    result = {}
    for name in SNAPSHOT_FIELDS:
        value = getattr(entry, name)
        result[name] = str(value) if isinstance(value, (Decimal, date)) else value
    result["category_name"] = entry.category.name
    return result


def _event(entry, action, user, before=None):
    FinancialEvent.objects.create(
        entry=entry, action=action, actor=user,
        details={"before": before, "after": _snapshot(entry)},
    )


def _repeated_submission(existing, candidate):
    created = existing.events.filter(action=FinancialEvent.Action.CREATED).first()
    original = created.details["after"] if created else _snapshot(existing)
    proposed = _snapshot(candidate)
    if any(original.get(field, False if field == "is_archived" else None) != proposed.get(field) for field in SNAPSHOT_FIELDS):
        raise ValidationError("Este formulário já foi usado. Abra Novo lançamento para registrar outra entrada ou despesa.")
    return existing


@transaction.atomic
def save_financial_entry(entry, *, user, expected_updated_at=None):
    """Persiste um ModelForm(commit=False), com histórico e proteção contra repetição.

    A criação repetida com a mesma chave devolve o primeiro lançamento. Na edição,
    campos de baixa não podem ser alterados; use as transições explícitas abaixo.
    """
    if entry._state.adding:
        existing = FinancialEntry.objects.filter(submission_key=entry.submission_key).first()
        if existing:
            return _repeated_submission(existing, entry)
        if entry.status not in (FinancialEntry.Status.PENDING, FinancialEntry.Status.SETTLED):
            raise ValidationError("Um novo lançamento deve estar pendente ou realizado.")
        # A trava também impede uma desativação concorrente pela tela de categorias.
        category = FinancialCategory.objects.select_for_update().get(pk=entry.category_id)
        if not category.is_active:
            raise ValidationError({"category": "Escolha uma categoria ativa."})
        entry.category = category
        entry.created_by = user
        entry.updated_by = user
        entry.full_clean(validate_unique=False)
        try:
            # Savepoint permite tratar duas requisições simultâneas com a mesma chave.
            with transaction.atomic():
                entry.save(force_insert=True)
        except IntegrityError:
            existing = FinancialEntry.objects.filter(submission_key=entry.submission_key).first()
            if existing:
                return _repeated_submission(existing, entry)
            raise
        _event(entry, FinancialEvent.Action.CREATED, user)
        return entry

    locked = FinancialEntry.objects.select_for_update(of=("self",)).select_related("category").get(pk=entry.pk)
    if locked.status != FinancialEntry.Status.PENDING:
        raise ValidationError("Reabra o lançamento antes de editar seus dados.")
    expected = expected_updated_at or entry.updated_at
    if expected and locked.updated_at != expected:
        raise ValidationError("Este lançamento foi atualizado em outra janela. Recarregue a página antes de editar.")
    if entry.status != FinancialEntry.Status.PENDING or entry.settled_at or entry.method:
        raise ValidationError("Use a ação de baixa para registrar um recebimento ou pagamento.")
    category = FinancialCategory.objects.select_for_update().get(pk=entry.category_id)
    if not category.is_active and category.pk != locked.category_id:
        raise ValidationError({"category": "Escolha uma categoria ativa."})
    before = _snapshot(locked)
    for field in EDITABLE_FIELDS:
        setattr(locked, field, getattr(entry, field))
    locked.category = category
    locked.full_clean()
    if before != _snapshot(locked):
        locked.updated_by = user
        locked.save()
        _event(locked, FinancialEvent.Action.UPDATED, user, before)
    return locked


@transaction.atomic
def transition_financial_entry(pk, action, *, user=None, settled_at=None, method=""):
    entry = FinancialEntry.objects.select_for_update(of=("self",)).select_related("category").get(pk=pk)
    before = _snapshot(entry)
    if action == FinancialEvent.Action.ARCHIVED:
        if entry.is_archived:
            return entry
        if entry.status == FinancialEntry.Status.SETTLED:
            raise ValidationError("Reabra o lançamento realizado antes de excluir.")
        entry.is_archived = True
        entry.status = FinancialEntry.Status.CANCELLED
    elif action == FinancialEvent.Action.RESTORED:
        if not entry.is_archived:
            return entry
        entry.is_archived = False
        entry.status = FinancialEntry.Status.PENDING
    elif entry.is_archived:
        raise ValidationError("Restaure o lançamento da lixeira antes de alterá-lo.")
    elif action == FinancialEvent.Action.SETTLED:
        if entry.status == FinancialEntry.Status.SETTLED:
            return entry
        if entry.status != FinancialEntry.Status.PENDING:
            raise ValidationError("Reabra o lançamento cancelado antes de registrar a baixa.")
        entry.status = FinancialEntry.Status.SETTLED
        entry.settled_at = settled_at or timezone.localdate()
        entry.method = method
    elif action == FinancialEvent.Action.REOPENED:
        if entry.status == FinancialEntry.Status.PENDING:
            return entry
        entry.status = FinancialEntry.Status.PENDING
        entry.settled_at = None
        entry.method = ""
    elif action == FinancialEvent.Action.CANCELLED:
        if entry.status == FinancialEntry.Status.CANCELLED:
            return entry
        if entry.status != FinancialEntry.Status.PENDING:
            raise ValidationError("Reabra o lançamento realizado antes de cancelar.")
        entry.status = FinancialEntry.Status.CANCELLED
    else:
        raise ValidationError("Ação financeira inválida.")
    entry.full_clean()
    entry.updated_by = user
    entry.save()
    _event(entry, action, user, before)
    return entry


def _sum(queryset, expression="amount"):
    return queryset.aggregate(total=Sum(expression))["total"] or ZERO


def _validate_range(start, end):
    if not isinstance(start, date) or not isinstance(end, date) or end < start:
        raise ValueError("Informe um período válido.")


def finance_summary(start, end):
    """Valores inclusivos do período; saldo realizado calculado pela data de caixa.

    Pendências usam vencimento, inclusive datas futuras do período selecionado.
    Saldo anterior/acumulado considera apenas registros existentes no sistema,
    sem pressupor um saldo bancário inicial.
    """
    _validate_range(start, end)
    today = timezone.localdate()
    realized_end = min(end, today)
    payments = Payment.objects.filter(invoice__status=Invoice.Status.PAGA, paid_at__lte=today)
    realized = FinancialEntry.objects.filter(status=FinancialEntry.Status.SETTLED, settled_at__lte=today)
    previous_entries = realized.filter(settled_at__lt=start)
    opening = (
        _sum(payments.filter(paid_at__lt=start))
        + _sum(previous_entries.filter(kind=FinancialEntry.Kind.INCOME))
        - _sum(previous_entries.filter(kind=FinancialEntry.Kind.EXPENSE))
    )
    period_entries = realized.filter(settled_at__range=(start, realized_end))
    tuition_income = _sum(payments.filter(paid_at__range=(start, realized_end)))
    other_income = _sum(period_entries.filter(kind=FinancialEntry.Kind.INCOME))
    expenses = _sum(period_entries.filter(kind=FinancialEntry.Kind.EXPENSE))
    income = tuition_income + other_income

    pending = FinancialEntry.objects.filter(status=FinancialEntry.Status.PENDING, due_date__range=(start, end))
    invoices = Invoice.objects.filter(status=Invoice.Status.ABERTA, due_date__range=(start, end))
    invoice_total = F("amount") - F("discount")
    # Os formulários validam descontos; Greatest protege contra dados legados.
    from django.db.models.functions import Greatest
    invoice_total = Greatest(invoice_total, ZERO)
    pending_tuition = _sum(invoices, invoice_total)
    pending_income = _sum(pending.filter(kind=FinancialEntry.Kind.INCOME)) + pending_tuition
    pending_expenses = _sum(pending.filter(kind=FinancialEntry.Kind.EXPENSE))
    overdue_income = (
        _sum(pending.filter(kind=FinancialEntry.Kind.INCOME, due_date__lt=today))
        + _sum(invoices.filter(due_date__lt=today), invoice_total)
    )
    overdue_expenses = _sum(pending.filter(kind=FinancialEntry.Kind.EXPENSE, due_date__lt=today))
    expense_categories = list(
        period_entries.filter(kind=FinancialEntry.Kind.EXPENSE)
        .values("category__name").annotate(total=Sum("amount")).order_by("-total", "category__name")
    )
    return {
        "opening_balance": opening,
        "income": income,
        "expenses": expenses,
        "net": income - expenses,
        "closing_balance": opening + income - expenses,
        "tuition_income": tuition_income,
        "other_income": other_income,
        "pending_tuition": pending_tuition,
        "pending_income": pending_income,
        "pending_expenses": pending_expenses,
        "overdue_income": overdue_income,
        "overdue_expenses": overdue_expenses,
        "expense_categories": expense_categories,
        "projected_balance": opening + income - expenses + pending_income - pending_expenses,
        "start": start,
        "end": end,
    }


def finance_movements(start, end, kind="", status="", category="", q=""):
    """Lista unificada, para paginação/exportação pela camada de apresentação.

    Categoria ``tuition`` seleciona mensalidades; categorias numéricas selecionam
    lançamentos manuais. ``overdue`` é situação calculada, sem ser gravada.
    """
    _validate_range(start, end)
    today = timezone.localdate()
    q = (q or "").strip()[:160]
    kind, status, category = str(kind or ""), str(status or ""), str(category or "")
    if kind not in ("", *FinancialEntry.Kind.values) or status not in ("", "pending", "settled", "cancelled", "overdue", "archived"):
        return []
    entries = FinancialEntry.objects.select_related("category").filter(
        Q(status=FinancialEntry.Status.SETTLED, settled_at__range=(start, min(end, today)))
        | Q(status__in=[FinancialEntry.Status.PENDING, FinancialEntry.Status.CANCELLED], due_date__range=(start, end))
    )
    entries = entries.filter(is_archived=(status == "archived"))
    invoices = Invoice.objects.filter(status=Invoice.Status.ABERTA, due_date__range=(start, end)).select_related("student__user", "plan")
    payments = Payment.objects.filter(invoice__status=Invoice.Status.PAGA, paid_at__range=(start, min(end, today))).select_related("invoice__student__user", "invoice__plan")
    if kind:
        entries = entries.filter(kind=kind)
        if kind == FinancialEntry.Kind.EXPENSE:
            invoices, payments = invoices.none(), payments.none()
    if status:
        if status == "overdue":
            entries = entries.filter(status=FinancialEntry.Status.PENDING, due_date__lt=today)
            invoices = invoices.filter(due_date__lt=today)
        elif status != "archived":
            entries = entries.filter(status=status)
        if status not in ("pending", "overdue"):
            invoices = invoices.none()
        if status != "settled":
            payments = payments.none()
    if category:
        if category == "tuition":
            entries = entries.none()
        elif category.isdecimal() and len(category) <= 18:
            entries = entries.filter(category_id=int(category))
            invoices, payments = invoices.none(), payments.none()
        else:
            return []
    if q:
        entries = entries.filter(Q(description__icontains=q) | Q(counterparty__icontains=q) | Q(category__name__icontains=q))
        invoice_search = Q(student__user__first_name__icontains=q) | Q(student__user__last_name__icontains=q) | Q(student__nickname__icontains=q)
        payment_search = Q(invoice__student__user__first_name__icontains=q) | Q(invoice__student__user__last_name__icontains=q) | Q(invoice__student__nickname__icontains=q)
        if q.lower() not in "mensalidade":
            invoices = invoices.filter(invoice_search)
            payments = payments.filter(payment_search)

    rows = []
    for entry in entries:
        rows.append({
            "source": "entry", "id": entry.pk, "entry": entry, "invoice": None,
            "date": entry.settled_at if entry.status == entry.Status.SETTLED else entry.due_date,
            "due_date": entry.due_date, "description": entry.description,
            "counterparty": entry.counterparty, "kind": entry.kind,
            "category": entry.category.name, "category_id": entry.category_id,
            "amount": entry.amount, "status": "archived" if entry.is_archived else entry.status, "status_label": entry.status_label,
            "is_overdue": entry.is_overdue, "method": entry.get_method_display() if entry.method else "—",
            "method_key": entry.method, "notes": entry.notes,
        })
    for payment in payments:
        invoice = payment.invoice
        rows.append({
            "source": "payment", "id": payment.pk, "entry": None, "invoice": invoice,
            "date": payment.paid_at, "due_date": invoice.due_date,
            "description": f"Mensalidade · {invoice.competence_short}",
            "counterparty": invoice.student.display_name, "kind": "income",
            "category": "Mensalidades", "category_id": "tuition",
            "amount": payment.amount, "status": "settled", "status_label": "Recebido",
            "is_overdue": False, "method": payment.get_method_display(),
            "method_key": payment.method, "notes": payment.note,
        })
    for invoice in invoices:
        rows.append({
            "source": "invoice", "id": invoice.pk, "entry": None, "invoice": invoice,
            "date": invoice.due_date, "due_date": invoice.due_date,
            "description": f"Mensalidade · {invoice.competence_short}",
            "counterparty": invoice.student.display_name, "kind": "income",
            "category": "Mensalidades", "category_id": "tuition",
            "amount": invoice.total, "status": "pending",
            "status_label": "Vencido" if invoice.is_overdue else "A receber",
            "is_overdue": invoice.is_overdue, "method": "—", "method_key": "", "notes": invoice.notes,
        })
    rows.sort(key=lambda row: (row["date"], row["id"], row["source"]), reverse=True)
    return rows
