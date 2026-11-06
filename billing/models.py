from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models, transaction
from django.db.models.functions import Lower
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone


class Plan(models.Model):
    name = models.CharField("nome do plano", max_length=80)
    description = models.CharField("descrição", max_length=200, blank=True)
    monthly_fee = models.DecimalField("valor mensal", max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])
    due_day = models.PositiveSmallIntegerField("dia de vencimento", default=10, validators=[MinValueValidator(1), MaxValueValidator(31)])
    sessions_per_week = models.PositiveSmallIntegerField("treinos por semana", default=2, validators=[MinValueValidator(1), MaxValueValidator(7)])
    is_active = models.BooleanField("ativo", default=True)

    class Meta:
        verbose_name = "plano"
        verbose_name_plural = "planos"
        ordering = ["monthly_fee"]

    def __str__(self) -> str:
        return f"{self.name} — R$ {self.monthly_fee}"

    @property
    def due_day_label(self) -> str:
        return f"todo dia {self.due_day}"


class InvoiceQuerySet(models.QuerySet):
    def open(self):
        return self.filter(status=Invoice.Status.ABERTA)

    def overdue(self):
        return self.filter(status=Invoice.Status.ABERTA, due_date__lt=timezone.localdate())

    def for_competence(self, competence: date):
        return self.filter(competence__year=competence.year, competence__month=competence.month)


class Invoice(models.Model):
    class Status(models.TextChoices):
        ABERTA = "aberta", "Em aberto"
        PAGA = "paga", "Paga"
        ISENTA = "isenta", "Isenta"
        CANCELADA = "cancelada", "Cancelada"

    class Method(models.TextChoices):
        PIX = "pix", "Pix"
        DINHEIRO = "dinheiro", "Dinheiro"
        CARTAO = "cartao", "Cartão"
        TRANSFERENCIA = "transferencia", "Transferência"
        BOLETO = "boleto", "Boleto"

    student = models.ForeignKey("accounts.Student", on_delete=models.CASCADE, related_name="invoices", verbose_name="aluno")
    plan = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True, blank=True, related_name="invoices", verbose_name="plano")
    competence = models.DateField("competência", help_text="Primeiro dia do mês de referência")
    amount = models.DecimalField("valor", max_digits=8, decimal_places=2)
    discount = models.DecimalField("desconto", max_digits=8, decimal_places=2, default=0)
    due_date = models.DateField("vencimento")
    status = models.CharField("situação", max_length=12, choices=Status.choices, default=Status.ABERTA)
    paid_at = models.DateField("pago em", null=True, blank=True)
    payment_method = models.CharField("forma de pagamento", max_length=16, choices=Method.choices, blank=True)
    notes = models.CharField("observações", max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = InvoiceQuerySet.as_manager()

    class Meta:
        verbose_name = "mensalidade"
        verbose_name_plural = "mensalidades"
        ordering = ["-competence", "due_date", "student__user__first_name"]
        constraints = [
            models.UniqueConstraint(fields=["student", "competence"], name="unique_invoice_per_month")
        ]
        indexes = [models.Index(fields=["status", "due_date"])]

    def __str__(self) -> str:
        return f"{self.student} — {self.competence:%m/%Y}"

    @property
    def total(self) -> Decimal:
        return max(self.amount - self.discount, Decimal("0.00"))

    @property
    def competence_label(self) -> str:
        months = [
            "janeiro", "fevereiro", "março", "abril", "maio", "junho",
            "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
        ]
        return f"{months[self.competence.month - 1].capitalize()}/{self.competence.year}"

    @property
    def competence_short(self) -> str:
        return self.competence.strftime("%m/%Y")

    @property
    def is_overdue(self) -> bool:
        return self.status == self.Status.ABERTA and self.due_date < timezone.localdate()

    @property
    def days_until_due(self) -> int:
        return (self.due_date - timezone.localdate()).days

    @property
    def situacao(self) -> str:
        """Rótulo amigável considerando atraso calculado em tempo real."""
        if self.is_overdue:
            return "Vencida"
        return self.get_status_display()

    @property
    def situacao_key(self) -> str:
        if self.is_overdue:
            return "vencida"
        return self.status

    @property
    def reference_month(self) -> str:
        return self.competence.strftime("%Y-%m")

    @transaction.atomic
    def mark_paid(self, *, user=None, method: str = "", paid_at: date | None = None, note: str = ""):
        locked = Invoice.objects.select_for_update().get(pk=self.pk)
        if locked.status == self.Status.PAGA:
            self.refresh_from_db()
            return self
        if locked.status != self.Status.ABERTA:
            raise ValidationError("Somente mensalidades em aberto podem receber pagamento.")
        if method and method not in self.Method.values:
            raise ValidationError("Forma de pagamento inválida.")
        self.refresh_from_db()
        paid_at = paid_at or timezone.localdate()
        self.status = self.Status.PAGA
        self.paid_at = paid_at
        self.payment_method = method or self.payment_method
        if note:
            self.notes = note[:200]
        self.save()
        Payment.objects.create(
            invoice=self,
            amount=self.total,
            paid_at=paid_at,
            method=self.payment_method or Payment.Method.PIX,
            note=note[:200],
            created_by=user,
        )
        return self

    @transaction.atomic
    def reopen(self):
        Invoice.objects.select_for_update().get(pk=self.pk)
        self.refresh_from_db()
        self.status = self.Status.ABERTA
        self.paid_at = None
        self.payment_method = ""
        self.save()
        self.payments.all().delete()

    def get_absolute_url(self) -> str:
        return reverse("dashboard:billing")


class Payment(models.Model):
    class Method(models.TextChoices):
        PIX = "pix", "Pix"
        DINHEIRO = "dinheiro", "Dinheiro"
        CARTAO = "cartao", "Cartão"
        TRANSFERENCIA = "transferencia", "Transferência"
        BOLETO = "boleto", "Boleto"

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments", verbose_name="mensalidade")
    amount = models.DecimalField("valor pago", max_digits=8, decimal_places=2)
    paid_at = models.DateField("data do pagamento")
    method = models.CharField("forma", max_length=16, choices=Method.choices, default=Method.PIX)
    note = models.CharField("observação", max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "pagamento"
        verbose_name_plural = "pagamentos"
        ordering = ["-paid_at"]

    def __str__(self) -> str:
        return f"{self.invoice.student} — R$ {self.amount} em {self.paid_at:%d/%m/%Y}"


class FinancialCategory(models.Model):
    class Kind(models.TextChoices):
        INCOME = "income", "Entrada"
        EXPENSE = "expense", "Saída"

    name = models.CharField("nome", max_length=80)
    kind = models.CharField("tipo", max_length=10, choices=Kind.choices)
    is_active = models.BooleanField("ativa", default=True)

    class Meta:
        verbose_name = "categoria financeira"
        verbose_name_plural = "categorias financeiras"
        ordering = ["kind", "name"]
        constraints = [
            models.UniqueConstraint(Lower("name"), "kind", name="unique_finance_category_kind_name"),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        self.name = self.name.strip()
        if not self.name:
            raise ValidationError({"name": "Informe o nome da categoria."})
        if self.pk and self.entries.exclude(kind=self.kind).exists():
            raise ValidationError({"kind": "Uma categoria com lançamentos não pode mudar de tipo."})


class FinancialEntry(models.Model):
    Kind = FinancialCategory.Kind

    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        SETTLED = "settled", "Realizado"
        CANCELLED = "cancelled", "Cancelado"

    submission_key = models.UUIDField(default=uuid4, unique=True, editable=False)
    kind = models.CharField("tipo", max_length=10, choices=Kind.choices)
    category = models.ForeignKey(FinancialCategory, on_delete=models.PROTECT, related_name="entries", verbose_name="categoria")
    description = models.CharField("descrição", max_length=160)
    counterparty = models.CharField("cliente ou fornecedor", max_length=160, blank=True)
    amount = models.DecimalField("valor", max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    due_date = models.DateField("vencimento")
    status = models.CharField("situação", max_length=12, choices=Status.choices, default=Status.PENDING)
    settled_at = models.DateField("data do recebimento ou pagamento", null=True, blank=True)
    method = models.CharField("forma de pagamento", max_length=16, choices=Payment.Method.choices, blank=True)
    notes = models.TextField("observações", max_length=2000, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="financial_entries_created")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="financial_entries_updated")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "lançamento financeiro"
        verbose_name_plural = "lançamentos financeiros"
        ordering = ["-due_date", "-pk"]
        indexes = [
            models.Index(fields=["status", "due_date"], name="finance_status_due_idx"),
            models.Index(fields=["status", "settled_at"], name="finance_status_settled_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="finance_entry_positive_amount"),
            models.CheckConstraint(
                condition=(
                    models.Q(status="settled", settled_at__isnull=False, method__in=Payment.Method.values)
                    | models.Q(status__in=["pending", "cancelled"], settled_at__isnull=True, method="")
                ),
                name="finance_entry_settlement_consistent",
            ),
            models.CheckConstraint(condition=models.Q(kind__in=FinancialCategory.Kind.values), name="finance_entry_valid_kind"),
        ]

    def __str__(self):
        return self.description

    @property
    def is_overdue(self):
        return self.status == self.Status.PENDING and self.due_date < timezone.localdate()

    @property
    def status_label(self):
        if self.status == self.Status.CANCELLED:
            return "Cancelado"
        if self.status == self.Status.SETTLED:
            return "Recebido" if self.kind == self.Kind.INCOME else "Pago"
        if self.is_overdue:
            return "Vencido"
        return "A receber" if self.kind == self.Kind.INCOME else "A pagar"

    def clean(self):
        super().clean()
        self.description = self.description.strip()
        if not self.description:
            raise ValidationError({"description": "Informe a descrição do lançamento."})
        errors = {}
        if self.category_id and self.category.kind != self.kind:
            errors["category"] = "Escolha uma categoria do mesmo tipo do lançamento."
        if self.status == self.Status.SETTLED:
            if not self.settled_at:
                errors["settled_at"] = "Informe a data do recebimento ou pagamento."
            elif self.settled_at > timezone.localdate():
                errors["settled_at"] = "A data realizada não pode estar no futuro."
            if not self.method:
                errors["method"] = "Informe a forma de pagamento."
        elif self.settled_at or self.method:
            errors["status"] = "Lançamentos pendentes ou cancelados não podem ter dados de baixa."
        if errors:
            raise ValidationError(errors)

    def settle(self, *, user=None, date=None, method=""):
        from .finance import transition_financial_entry
        result = transition_financial_entry(self.pk, "settled", user=user, settled_at=date, method=method)
        self.refresh_from_db()
        return result

    def reopen(self, *, user=None):
        from .finance import transition_financial_entry
        result = transition_financial_entry(self.pk, "reopened", user=user)
        self.refresh_from_db()
        return result

    def cancel(self, *, user=None):
        from .finance import transition_financial_entry
        result = transition_financial_entry(self.pk, "cancelled", user=user)
        self.refresh_from_db()
        return result


class FinancialEvent(models.Model):
    class Action(models.TextChoices):
        CREATED = "created", "Lançamento criado"
        UPDATED = "updated", "Lançamento atualizado"
        SETTLED = "settled", "Baixa registrada"
        REOPENED = "reopened", "Lançamento reaberto"
        CANCELLED = "cancelled", "Lançamento cancelado"

    entry = models.ForeignKey(FinancialEntry, on_delete=models.PROTECT, related_name="events")
    action = models.CharField("ação", max_length=12, choices=Action.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    details = models.JSONField("alterações", default=dict)
    created_at = models.DateTimeField("registrado em", auto_now_add=True)

    class Meta:
        verbose_name = "histórico financeiro"
        verbose_name_plural = "histórico financeiro"
        ordering = ["-created_at", "-pk"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("O histórico financeiro não pode ser alterado.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("O histórico financeiro não pode ser excluído.")


def competence_start(value: date | None = None) -> date:
    value = value or timezone.localdate()
    return value.replace(day=1)


def next_competence(competence: date, months: int = 1) -> date:
    year = competence.year + (competence.month - 1 + months) // 12
    month = (competence.month - 1 + months) % 12 + 1
    return date(year, month, 1)


def due_date_for(competence: date, day: int) -> date:
    last_day = monthrange(competence.year, competence.month)[1]
    return competence.replace(day=min(max(day, 1), last_day))


def suggested_due_date(competence: date, plan: Plan | None = None) -> date:
    return due_date_for(competence, plan.due_day if plan else 10)

