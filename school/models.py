from __future__ import annotations

from datetime import date, datetime

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

WEEKDAYS = [
    (0, "Segunda"),
    (1, "Terça"),
    (2, "Quarta"),
    (3, "Quinta"),
    (4, "Sexta"),
    (5, "Sábado"),
    (6, "Domingo"),
]


class Venue(models.Model):
    name = models.CharField("nome", max_length=80)
    address = models.CharField("endereço", max_length=200, blank=True)
    notes = models.CharField("observações", max_length=200, blank=True)
    is_active = models.BooleanField("ativo", default=True)

    class Meta:
        verbose_name = "local"
        verbose_name_plural = "locais"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ClassGroup(models.Model):
    class Category(models.TextChoices):
        SUB13 = "sub13", "Sub-13"
        SUB15 = "sub15", "Sub-15"
        SUB17 = "sub17", "Sub-17"
        ADULTO = "adulto", "Adulto"
        LIVRE = "livre", "Livre"

    name = models.CharField("nome da turma", max_length=80)
    level = models.CharField("nível", max_length=16, choices=[
        ("iniciante", "Iniciante"),
        ("intermediario", "Intermediário"),
        ("avancado", "Avançado"),
        ("misto", "Misto"),
    ], default="iniciante")
    category = models.CharField("categoria", max_length=12, choices=Category.choices, default=Category.LIVRE)
    professor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teaching_groups",
        verbose_name="professor(a)",
        limit_choices_to={"role__in": ["professor", "admin"]},
    )
    venue = models.ForeignKey(Venue, on_delete=models.SET_NULL, null=True, blank=True, related_name="groups", verbose_name="local")
    capacity = models.PositiveSmallIntegerField("vagas", default=16)
    description = models.TextField("descrição", blank=True)
    is_active = models.BooleanField("ativa", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "turma"
        verbose_name_plural = "turmas"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @property
    def occupied(self) -> int:
        return self.enrollments.filter(status="ativa").count()

    @property
    def free_spots(self) -> int:
        return max(self.capacity - self.occupied, 0)

    @property
    def occupancy_pct(self) -> int:
        if not self.capacity:
            return 0
        return min(round(self.occupied * 100 / self.capacity), 100)

    @property
    def schedule_label(self) -> str:
        slots = list(self.slots.all())
        if not slots:
            return "Horário a definir"
        return " • ".join(f"{s.weekday_label} {s.start_time:%Hh%M}" for s in slots)

    def get_absolute_url(self) -> str:
        return reverse("dashboard:class_edit", args=[self.pk])


class ScheduleSlot(models.Model):
    class_group = models.ForeignKey(ClassGroup, on_delete=models.CASCADE, related_name="slots", verbose_name="turma")
    weekday = models.PositiveSmallIntegerField("dia da semana", choices=WEEKDAYS)
    start_time = models.TimeField("início")
    end_time = models.TimeField("fim")
    venue = models.ForeignKey(Venue, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="local")

    class Meta:
        verbose_name = "horário"
        verbose_name_plural = "horários"
        ordering = ["weekday", "start_time"]
        constraints = [
            models.UniqueConstraint(fields=["class_group", "weekday", "start_time"], name="unique_slot_per_group")
        ]

    def __str__(self) -> str:
        return f"{self.class_group} — {self.weekday_label} {self.start_time:%H:%M}"

    @property
    def weekday_label(self) -> str:
        return dict(WEEKDAYS).get(self.weekday, "")


class Enrollment(models.Model):
    class Status(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        ATIVA = "ativa", "Ativa"
        REJEITADA = "rejeitada", "Rejeitada"
        CANCELADA = "cancelada", "Cancelada"

    student = models.ForeignKey("accounts.Student", on_delete=models.CASCADE, related_name="enrollments", verbose_name="aluno")
    class_group = models.ForeignKey(ClassGroup, on_delete=models.PROTECT, related_name="enrollments", verbose_name="turma")
    plan = models.ForeignKey("billing.Plan", on_delete=models.PROTECT, related_name="enrollments", verbose_name="plano")
    status = models.CharField("situação", max_length=12, choices=Status.choices, default=Status.PENDENTE)
    monthly_fee = models.DecimalField("mensalidade acordada", max_digits=8, decimal_places=2)
    enrolled_at = models.DateTimeField("inscrição em", auto_now_add=True)
    start_date = models.DateField("início", null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_enrollments"
    )
    approved_at = models.DateTimeField("aprovada em", null=True, blank=True)
    notes = models.TextField("observações", blank=True)

    class Meta:
        verbose_name = "matrícula"
        verbose_name_plural = "matrículas"
        ordering = ["-enrolled_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["student"],
                condition=Q(status="ativa"),
                name="one_active_enrollment_per_student",
            )
        ]

    def __str__(self) -> str:
        return f"{self.student} — {self.class_group} ({self.get_status_display()})"

    def approve(self, user, start_date: date | None = None):
        self.status = self.Status.ATIVA
        self.approved_by = user
        self.approved_at = timezone.now()
        self.start_date = start_date or date.today()
        self.save()
        student = self.student
        student.status = student.Status.ATIVO
        student.joined_at = student.joined_at or self.start_date
        student.save(update_fields=["status", "joined_at"])


class Session(models.Model):
    """Treino (aula) em uma data específica."""

    class Status(models.TextChoices):
        AGENDADO = "agendado", "Agendado"
        REALIZADO = "realizado", "Realizado"
        CANCELADO = "cancelado", "Cancelado"

    class_group = models.ForeignKey(ClassGroup, on_delete=models.CASCADE, related_name="sessions", verbose_name="turma")
    date = models.DateField("data")
    start_time = models.TimeField("início")
    end_time = models.TimeField("fim")
    venue = models.ForeignKey(Venue, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="local")
    theme = models.CharField("tema do treino", max_length=120, blank=True)
    status = models.CharField("situação", max_length=12, choices=Status.choices, default=Status.AGENDADO)
    notes = models.TextField("observações", blank=True)
    canceled_reason = models.CharField("motivo do cancelamento", max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "treino"
        verbose_name_plural = "treinos"
        ordering = ["date", "start_time"]
        constraints = [
            models.UniqueConstraint(fields=["class_group", "date", "start_time"], name="unique_session_per_group")
        ]

    def __str__(self) -> str:
        return f"{self.class_group} — {self.date:%d/%m/%Y} {self.start_time:%H:%M}"

    @property
    def starts_at(self) -> datetime:
        return timezone.make_aware(datetime.combine(self.date, self.start_time))

    @property
    def ends_at(self) -> datetime:
        return timezone.make_aware(datetime.combine(self.date, self.end_time))

    @property
    def is_past(self) -> bool:
        return self.ends_at < timezone.now()

    @property
    def is_today(self) -> bool:
        return self.date == timezone.localdate()

    @property
    def weekday_label(self) -> str:
        return dict(WEEKDAYS).get(self.date.weekday(), "")

    @property
    def attendance_rate(self) -> int | None:
        total = self.attendance.exclude(status=Attendance.Status.JUSTIFICADA).count()
        if not total:
            return None
        present = self.attendance.filter(status__in=[Attendance.Status.PRESENTE, Attendance.Status.ATRASO]).count()
        return round(present * 100 / total)

    @property
    def confirmed_count(self) -> int:
        return self.attendance.filter(status__in=[Attendance.Status.PRESENTE, Attendance.Status.ATRASO]).count()

    def get_absolute_url(self) -> str:
        return reverse("dashboard:session_attendance", args=[self.pk])


class Attendance(models.Model):
    class Status(models.TextChoices):
        PRESENTE = "presente", "Presente"
        FALTA = "falta", "Falta"
        JUSTIFICADA = "justificada", "Falta justificada"
        ATRASO = "atraso", "Atraso"

    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="attendance", verbose_name="treino")
    student = models.ForeignKey("accounts.Student", on_delete=models.CASCADE, related_name="attendance", verbose_name="aluno")
    status = models.CharField("presença", max_length=12, choices=Status.choices, default=Status.PRESENTE)
    note = models.CharField("observação", max_length=160, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    recorded_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "presença"
        verbose_name_plural = "presenças"
        ordering = ["session__date", "student__user__first_name"]
        constraints = [models.UniqueConstraint(fields=["session", "student"], name="unique_attendance")]

    def __str__(self) -> str:
        return f"{self.student} — {self.session.date:%d/%m} — {self.get_status_display()}"


class PointRule(models.Model):
    name = models.CharField("nome da regra", max_length=80)
    points = models.IntegerField("pontos", validators=[MinValueValidator(-100), MaxValueValidator(100)])
    description = models.CharField("descrição", max_length=200, blank=True)
    is_active = models.BooleanField("ativa", default=True)

    class Meta:
        verbose_name = "regra de pontuação"
        verbose_name_plural = "regras de pontuação"
        ordering = ["-points", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.points:+d})"


class PointEntry(models.Model):
    class Source(models.TextChoices):
        PRESENCA = "presenca", "Presença"
        DESEMPENHO = "desempenho", "Desempenho"
        EVENTO = "evento", "Evento"
        AJUSTE = "ajuste", "Ajuste"

    student = models.ForeignKey("accounts.Student", on_delete=models.CASCADE, related_name="points", verbose_name="aluno")
    points = models.IntegerField("pontos", validators=[MinValueValidator(-500), MaxValueValidator(500)])
    reason = models.CharField("motivo", max_length=160)
    rule = models.ForeignKey(PointRule, on_delete=models.SET_NULL, null=True, blank=True, related_name="entries", verbose_name="regra")
    session = models.ForeignKey(Session, on_delete=models.SET_NULL, null=True, blank=True, related_name="points", verbose_name="treino")
    source = models.CharField("origem", max_length=12, choices=Source.choices, default=Source.DESEMPENHO)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "lançamento de pontos"
        verbose_name_plural = "lançamentos de pontos"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["student", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.student} {self.points:+d} — {self.reason}"


class Announcement(models.Model):
    class Kind(models.TextChoices):
        NOTICIA = "noticia", "Notícia"
        AVISO = "aviso", "Aviso"
        EVENTO = "evento", "Evento"

    class Audience(models.TextChoices):
        ALUNOS = "alunos", "Somente alunos"
        INTERNO = "interno", "Somente equipe"

    title = models.CharField("título", max_length=160)
    slug = models.SlugField("slug", max_length=180, unique=True, blank=True)
    summary = models.CharField("resumo", max_length=240, blank=True)
    body = models.TextField("conteúdo")
    kind = models.CharField("tipo", max_length=12, choices=Kind.choices, default=Kind.AVISO)
    audience = models.CharField("público", max_length=12, choices=Audience.choices, default=Audience.ALUNOS)
    push_queued_at = models.DateTimeField(null=True, blank=True, editable=False)
    is_pinned = models.BooleanField("fixar no topo", default=False)
    is_published = models.BooleanField("publicado", default=True)
    published_at = models.DateTimeField("publicado em", default=timezone.now)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="announcements")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "comunicado"
        verbose_name_plural = "comunicados"
        ordering = ["-is_pinned", "-published_at"]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify_pt(self.title)[:160] or "comunicado"
            slug = base
            i = 2
            while Announcement.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{i}"
                i += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("dashboard:announcement_detail", args=[self.pk])

    @property
    def readable_date(self) -> str:
        return timezone.localtime(self.published_at).strftime("%d/%m/%Y")


def slugify_pt(value: str) -> str:
    from django.utils.text import slugify

    return slugify(value, allow_unicode=False)


class PushSubscription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_subscriptions")
    endpoint = models.URLField(max_length=2048, unique=True)
    p256dh = models.CharField(max_length=128)
    auth = models.CharField(max_length=64)
    updated_at = models.DateTimeField(auto_now=True)


class PushDelivery(models.Model):
    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE, related_name="deliveries")
    subscription = models.ForeignKey(PushSubscription, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    status = models.CharField(max_length=12, default="pending")
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)
    last_code = models.CharField(max_length=24, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["announcement", "subscription"], name="unique_announcement_device")]
        indexes = [models.Index(fields=["status", "next_attempt"])]
