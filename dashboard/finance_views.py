from __future__ import annotations

import csv
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import add_never_cache_headers
from django.views.decorators.http import require_http_methods

from billing.finance import finance_movements, finance_summary, save_financial_entry, transition_financial_entry
from billing.models import FinancialCategory, FinancialEntry
from .decorators import staff_required
from .finance_forms import FinancialCategoryForm, FinancialEntryForm, FinanceFilterForm, SettlementForm


def _event_changes(event):
    before = event.details.get("before") or {}
    after = event.details.get("after") or {}
    labels = {"description": "Descrição", "kind": "Tipo", "category_name": "Categoria", "counterparty": "Cliente / fornecedor", "amount": "Valor", "due_date": "Vencimento", "status": "Situação", "settled_at": "Data da baixa", "method": "Forma de pagamento", "notes": "Observações"}

    def display(key, value):
        if value in (None, ""):
            return "—"
        if key in ("due_date", "settled_at"):
            return date.fromisoformat(value).strftime("%d/%m/%Y")
        if key == "amount":
            return "R$ " + format(Decimal(value), ".2f").replace(".", ",")
        choices = {"kind": dict(FinancialEntry.Kind.choices), "status": dict(FinancialEntry.Status.choices), "method": dict(FinancialEntry._meta.get_field("method").choices)}
        return choices.get(key, {}).get(value, value)

    return [{"label": label, "before": display(key, before.get(key)), "after": display(key, after.get(key))} for key, label in labels.items() if before.get(key) != after.get(key)]


def _form_error(form, exc):
    if hasattr(exc, "message_dict"):
        for field, errors in exc.message_dict.items():
            form.add_error(field if field in form.fields else None, errors)
    else:
        form.add_error(None, exc)


def _csv_text(value):
    value = str(value or "")
    # Excel and similar tools may evaluate a quoted CSV cell as a formula.
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def _export(rows, start, end):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    add_never_cache_headers(response)
    response["Content-Disposition"] = f'attachment; filename="financeiro-{start.isoformat()}-{end.isoformat()}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Data", "Vencimento", "Tipo", "Categoria", "Descrição", "Cliente / fornecedor", "Valor (R$)", "Situação", "Forma", "Origem"])
    for row in rows:
        writer.writerow([
            row["date"].strftime("%d/%m/%Y"), row["due_date"].strftime("%d/%m/%Y"),
            "Entrada" if row["kind"] == "income" else "Saída", _csv_text(row["category"]),
            _csv_text(row["description"]), _csv_text(row["counterparty"]), format(row["amount"], ".2f").replace(".", ","),
            {"pending": "Pendente", "settled": "Realizado", "cancelled": "Cancelado", "archived": "Excluído"}.get(row["status"], row["status"]),
            _csv_text(row["method"]), "Lançamento" if row["source"] == "entry" else "Mensalidade",
        ])
    return response


@staff_required
@require_http_methods(["GET"])
def finance(request):
    today = timezone.localdate()
    start = today.replace(day=1)
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    data = request.GET.copy()
    if "start" not in data:
        data["start"] = start.isoformat()
    if "end" not in data:
        data["end"] = end.isoformat()
    form = FinanceFilterForm(data)
    valid = form.is_valid()
    rows, summary = [], None
    if valid:
        values = form.cleaned_data
        start, end = values["start"], values["end"]
        summary = finance_summary(start, end)
        rows = finance_movements(start, end, **{key: values.get(key, "") for key in ("kind", "status", "category", "q")})
        if request.GET.get("export") == "csv":
            return _export(rows, start, end)
    data.pop("page", None)
    data.pop("export", None)
    return render(request, "painel/finance.html", {
        "filter_form": form, "summary": summary, "period_start": start, "period_end": end,
        "page_obj": Paginator(rows, 30).get_page(request.GET.get("page")),
        "query_string": data.urlencode(), "export_url": f"{reverse('dashboard:finance')}?{data.urlencode()}&export=csv",
    })


@staff_required
@require_http_methods(["GET", "POST"])
def finance_edit(request, pk=None):
    entry = get_object_or_404(FinancialEntry.objects.select_related("category"), pk=pk) if pk else None
    if entry and entry.status != FinancialEntry.Status.PENDING:
        messages.warning(request, "Reabra o lançamento antes de editar. O histórico será preservado.")
        return redirect("dashboard:finance_detail", pk=pk)
    initial = {"kind": request.GET.get("tipo") if request.GET.get("tipo") in ("income", "expense") else "expense", "status": "pending"}
    form = FinancialEntryForm(request.POST if request.method == "POST" else None, instance=entry, initial=initial if not entry else None)
    if request.method == "POST" and form.is_valid():
        candidate = form.save(commit=False)
        candidate.submission_key = form.cleaned_data["submission_key"] if not pk else entry.submission_key
        try:
            saved = save_financial_entry(candidate, user=request.user, expected_updated_at=form.cleaned_data.get("version") if pk else None)
        except ValidationError as exc:
            _form_error(form, exc)
        else:
            messages.success(request, "Lançamento atualizado." if pk else "Lançamento registrado.")
            return redirect("dashboard:finance_detail", pk=saved.pk)
    return render(request, "painel/finance_form.html", {"form": form, "entry": entry})


@staff_required
@require_http_methods(["GET", "POST"])
def finance_detail(request, pk):
    entry = get_object_or_404(FinancialEntry.objects.select_related("category", "created_by", "updated_by"), pk=pk)
    settle_form = SettlementForm(request.POST if request.method == "POST" and request.POST.get("action") == "settle" else None)
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "settle":
                if settle_form.is_valid():
                    entry.settle(user=request.user, date=settle_form.cleaned_data["date"], method=settle_form.cleaned_data["method"])
                    messages.success(request, "Recebimento confirmado." if entry.kind == "income" else "Pagamento confirmado.")
                    return redirect("dashboard:finance_detail", pk=pk)
            elif action == "restore":
                transition_financial_entry(pk, "restored", user=request.user)
                messages.success(request, "Lançamento restaurado como pendente.")
                return redirect("dashboard:finance_detail", pk=pk)
            elif action in ("reopen", "cancel"):
                getattr(entry, action)(user=request.user)
                messages.success(request, "Lançamento reaberto." if action == "reopen" else "Lançamento cancelado. O histórico foi preservado.")
                return redirect("dashboard:finance_detail", pk=pk)
            else:
                return HttpResponse("Ação inválida.", status=400)
        except ValidationError as exc:
            if action == "settle":
                entry.refresh_from_db()
                if entry.status != FinancialEntry.Status.PENDING:
                    messages.error(request, "; ".join(exc.messages))
                    return redirect("dashboard:finance_detail", pk=pk)
                _form_error(settle_form, exc)
            else:
                messages.error(request, "; ".join(exc.messages))
                return redirect("dashboard:finance_detail", pk=pk)
        entry.refresh_from_db()
    events = list(entry.events.select_related("actor").order_by("-created_at", "-pk"))
    for event in events:
        event.changes = _event_changes(event)
    return render(request, "painel/finance_detail.html", {
        "entry": entry, "settle_form": settle_form,
        "events": events,
    })


@staff_required
@require_http_methods(["GET", "POST"])
def finance_categories(request, pk=None):
    category = get_object_or_404(FinancialCategory, pk=pk) if pk else None
    form = FinancialCategoryForm(request.POST if request.method == "POST" else None, instance=category)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                if pk:
                    locked = FinancialCategory.objects.select_for_update().get(pk=pk)
                    for name in ("name", "kind", "is_active"):
                        setattr(locked, name, form.cleaned_data[name])
                    locked.full_clean()
                    locked.save()
                else:
                    form.save()
        except ValidationError as exc:
            _form_error(form, exc)
        except IntegrityError:
            form.add_error("name", "Já existe uma categoria desse tipo com este nome.")
        else:
            messages.success(request, "Categoria atualizada." if pk else "Categoria criada.")
            return redirect("dashboard:finance_categories")
    return render(request, "painel/finance_category_form.html" if pk else "painel/finance_categories.html", {
        "form": form, "category": category, "categories": FinancialCategory.objects.order_by("kind", "name"),
    })
