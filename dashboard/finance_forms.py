from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
import uuid

from django import forms
from django.db.models import Q
from django.utils import timezone

from billing.models import FinancialCategory, FinancialEntry, Payment
from .forms import StyledFormMixin


class CategorySelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if hasattr(value, "instance"):
            option["attrs"]["data-kind"] = value.instance.kind
        return option


class FinancialEntryForm(StyledFormMixin, forms.ModelForm):
    # Excluded from ModelForm's uniqueness validation: a retried POST must return
    # the same entry, with the database constraint deciding concurrent requests.
    submission_key = forms.UUIDField(widget=forms.HiddenInput)
    version = forms.DateTimeField(required=False, widget=forms.HiddenInput)
    amount = forms.DecimalField(
        label="Valor (R$)", max_digits=12, decimal_places=2, min_value=Decimal("0.01"),
        localize=True, widget=forms.TextInput(attrs={"inputmode": "decimal", "placeholder": "0,00", "maxlength": 16}),
    )

    class Meta:
        model = FinancialEntry
        fields = ["kind", "description", "category", "counterparty", "amount", "due_date", "status", "settled_at", "method", "notes"]
        labels = {"kind": "Tipo", "description": "Descrição", "counterparty": "Cliente ou fornecedor (opcional)", "due_date": "Vencimento", "settled_at": "Data do recebimento ou pagamento", "method": "Forma de pagamento", "notes": "Observações (opcional)"}
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "settled_at": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notes": forms.Textarea(attrs={"rows": 3, "maxlength": 2000}),
            "category": CategorySelect,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        existing = bool(self.instance.pk)
        self.fields["submission_key"].initial = self.instance.submission_key or uuid.uuid4()
        self.fields["version"].initial = self.instance.updated_at.isoformat() if existing else ""
        categories = FinancialCategory.objects.filter(Q(is_active=True) | Q(pk=self.instance.category_id if existing else None))
        self.fields["category"].queryset = categories.order_by("kind", "name")
        self.fields["category"].label_from_instance = lambda cat: f"{cat.name} · {cat.get_kind_display()}"
        self.fields["category"].empty_label = "Selecione a categoria"
        self.fields["status"].choices = [("pending", "Pendente"), ("settled", "Já recebido ou pago")]
        self.fields["due_date"].initial = timezone.localdate()
        self.fields["amount"].help_text = "Informe o valor total. Para taxas separadas, registre uma saída na categoria Taxas."
        self.fields["counterparty"].help_text = "Ex.: nome do fornecedor, cliente ou patrocinador."
        self.fields["settled_at"].help_text = "Preencha somente se o dinheiro já entrou ou saiu."
        self.fields["notes"].help_text = "Você pode anotar a referência do recibo ou comprovante."
        if existing:
            self.fields["status"].disabled = True
            self.fields["version"].required = True
        self._style()

    def clean(self):
        data = super().clean()
        if data.get("status") == "settled":
            if not data.get("settled_at"):
                self.add_error("settled_at", "Informe a data em que o dinheiro entrou ou saiu.")
            if not data.get("method"):
                self.add_error("method", "Selecione a forma de pagamento.")
        else:
            data["settled_at"] = None
            data["method"] = ""
        if data.get("settled_at") and data["settled_at"] > timezone.localdate():
            self.add_error("settled_at", "Um pagamento realizado não pode ter data futura.")
        return data


class SettlementForm(StyledFormMixin, forms.Form):
    date = forms.DateField(label="Data do recebimento ou pagamento", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    method = forms.ChoiceField(label="Forma de pagamento", choices=[("", "Selecione")] + list(Payment.Method.choices))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date"].initial = timezone.localdate()
        self._style()

    def clean_date(self):
        value = self.cleaned_data["date"]
        if value > timezone.localdate():
            raise forms.ValidationError("Informe hoje ou uma data anterior.")
        return value


class FinancialCategoryForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = FinancialCategory
        fields = ["name", "kind", "is_active"]
        labels = {"name": "Nome da categoria", "kind": "Tipo", "is_active": "Ativa para novos lançamentos"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()
        self.fields["is_active"].help_text = "Desativar preserva todos os lançamentos e o histórico."


class FinanceFilterForm(StyledFormMixin, forms.Form):
    start = forms.DateField(label="De", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    end = forms.DateField(label="Até", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    kind = forms.ChoiceField(label="Tipo", required=False, choices=[("", "Entradas e saídas"), ("income", "Entradas"), ("expense", "Saídas")])
    status = forms.ChoiceField(label="Situação", required=False, choices=[("", "Todas"), ("pending", "Pendentes"), ("settled", "Recebidos / pagos"), ("overdue", "Em atraso"), ("cancelled", "Cancelados")])
    category = forms.ChoiceField(label="Categoria", required=False)
    q = forms.CharField(label="Buscar", required=False, max_length=160, widget=forms.TextInput(attrs={"type": "search", "placeholder": "Descrição ou pessoa"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].choices = [("", "Todas as categorias"), ("tuition", "Mensalidades (automáticas)")] + [(str(c.pk), f"{c.name} · {c.get_kind_display()}") for c in FinancialCategory.objects.order_by("kind", "name")]
        self._style()

    def clean(self):
        data = super().clean()
        start, end = data.get("start"), data.get("end")
        if start and end:
            if end < start:
                self.add_error("end", "A data final deve ser igual ou posterior à inicial.")
            elif end - start > timedelta(days=365):
                self.add_error("end", "Selecione um período de até 366 dias.")
        return data
