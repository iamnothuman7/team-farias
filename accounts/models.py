from __future__ import annotations

from datetime import date

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.urls import reverse


class UserManager(BaseUserManager):
    """Autenticação por e-mail (sem campo username)."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("O e-mail é obrigatório.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.ADMIN)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superusuário precisa de is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superusuário precisa de is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        ALUNO = "aluno", "Aluno(a)"
        PROFESSOR = "professor", "Professor(a)"
        ADMIN = "admin", "Administração"

    username = None
    email = models.EmailField("e-mail", unique=True)
    first_name = models.CharField("nome", max_length=80)
    last_name = models.CharField("sobrenome", max_length=80, blank=True)
    phone = models.CharField("telefone", max_length=24, blank=True)
    birth_date = models.DateField("data de nascimento", null=True, blank=True)
    role = models.CharField("perfil", max_length=16, choices=Role.choices, default=Role.ALUNO)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name"]

    objects = UserManager()

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"
        ordering = ["first_name", "last_name"]

    def __str__(self) -> str:
        return self.full_name or self.email

    def save(self, *args, **kwargs):
        self.email = self.email.lower().strip()
        super().save(*args, **kwargs)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def first_name_display(self) -> str:
        return self.first_name or self.email.split("@")[0].title()

    @property
    def initials(self) -> str:
        parts = [p for p in (self.first_name, self.last_name) if p]
        if not parts:
            return self.email[:2].upper()
        return "".join(p[0] for p in parts[:2]).upper()

    @property
    def is_admin_role(self) -> bool:
        return self.is_superuser or self.is_staff or self.role == self.Role.ADMIN

    @property
    def is_professor(self) -> bool:
        return self.role == self.Role.PROFESSOR

    @property
    def is_team_member(self) -> bool:
        """Administração ou professor — acesso ao painel de gestão."""
        return self.is_admin_role or self.role == self.Role.PROFESSOR

    @property
    def is_student(self) -> bool:
        return self.role == self.Role.ALUNO

    @property
    def age(self) -> int | None:
        if not self.birth_date:
            return None
        today = date.today()
        return today.year - self.birth_date.year - ((today.month, today.day) < (self.birth_date.month, self.birth_date.day))

    def get_absolute_url(self) -> str:
        return reverse("dashboard:home")


class Guardian(models.Model):
    """Responsável legal por um ou mais alunos."""

    name = models.CharField("nome completo", max_length=160)
    phone = models.CharField("telefone/WhatsApp", max_length=24)
    email = models.EmailField("e-mail", blank=True)
    document = models.CharField("CPF", max_length=20, blank=True)
    notes = models.TextField("observações", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "responsável"
        verbose_name_plural = "responsáveis"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @property
    def initials(self) -> str:
        parts = [p for p in self.name.split() if p]
        return "".join(p[0] for p in (parts[:2] or ["?"])).upper()


class Student(models.Model):
    class Level(models.TextChoices):
        INICIANTE = "iniciante", "Iniciante"
        INTERMEDIARIO = "intermediario", "Intermediário"
        AVANCADO = "avancado", "Avançado"

    class Status(models.TextChoices):
        PENDENTE = "pendente", "Matrícula pendente"
        ATIVO = "ativo", "Ativo"
        INATIVO = "inativo", "Inativo"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student", verbose_name="usuário")
    nickname = models.CharField("como prefere ser chamado", max_length=40, blank=True)
    guardian = models.ForeignKey(
        Guardian, on_delete=models.SET_NULL, null=True, blank=True, related_name="students", verbose_name="responsável"
    )
    level = models.CharField("nível", max_length=16, choices=Level.choices, default=Level.INICIANTE)
    status = models.CharField("situação", max_length=16, choices=Status.choices, default=Status.PENDENTE)
    position = models.CharField("posição preferida", max_length=40, blank=True, help_text="Ex.: bloqueio, defesa, levantamento")
    health_notes = models.TextField("observações de saúde", blank=True)
    notes = models.TextField("anotações internas", blank=True)
    joined_at = models.DateField("entrou em", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "aluno"
        verbose_name_plural = "alunos"
        ordering = ["user__first_name", "user__last_name"]

    def __str__(self) -> str:
        return self.display_name

    @property
    def display_name(self) -> str:
        return self.nickname or self.user.first_name_display

    @property
    def full_name(self) -> str:
        return self.user.full_name

    @property
    def initials(self) -> str:
        return self.user.initials

    @property
    def active_enrollment(self):
        return self.enrollments.filter(status="ativa").select_related("class_group", "plan").first()

    @property
    def class_group(self):
        enrollment = self.active_enrollment
        return enrollment.class_group if enrollment else None

    @property
    def total_points(self) -> int:
        return self.points.aggregate(total=models.Sum("points"))["total"] or 0

    def get_absolute_url(self) -> str:
        return reverse("dashboard:student_detail", args=[self.pk])
