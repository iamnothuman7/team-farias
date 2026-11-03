from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
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
        constraints = [models.UniqueConstraint(fields=["is_active"], condition=models.Q(is_active=True), name="one_active_plan")]

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

    def mark_paid(self, *, user=None, method: str = "", paid_at: date | None = None, note: str = ""):
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
            note=note,
            created_by=user,
        )
        return self

    def reopen(self):
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

