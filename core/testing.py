"""Fábricas de objetos usadas nos testes automatizados."""

from __future__ import annotations

from datetime import date, time, timedelta
from decimal import Decimal

from django.utils import timezone

from accounts.models import Student, User
from billing.models import Invoice, Plan
from school.models import ClassGroup, Enrollment, ScheduleSlot, Session, Venue


def make_user(email: str, first_name: str = "Ana", last_name: str = "Souza", **kwargs) -> User:
    password = kwargs.pop("password", "senha-segura-123")
    return User.objects.create_user(email=email, password=password, first_name=first_name, last_name=last_name, **kwargs)


def make_admin(email: str = "admin@teamfarias.com.br", **kwargs) -> User:
    return make_user(email, first_name="Rafa", role=User.Role.ADMIN, is_staff=True, is_superuser=True, **kwargs)


def make_professor(email: str = "prof@teamfarias.com.br", **kwargs) -> User:
    return make_user(email, first_name="Marina", role=User.Role.PROFESSOR, **kwargs)


def make_plan(name: str = "Plano 2x", fee: str = "180.00", due_day: int = 10) -> Plan:
    return Plan.objects.create(name=name, monthly_fee=Decimal(fee), due_day=due_day, sessions_per_week=2)


def make_group(
    name: str = "Iniciante Manhã",
    professor: User | None = None,
    slot_weekday: int | None = 1,
    capacity: int = 16,
) -> ClassGroup:
    venue = Venue.objects.get_or_create(name="Arena Teste")[0]
    group = ClassGroup.objects.create(
        name=name,
        category=ClassGroup.Category.SUB15,
        level="iniciante",
        professor=professor,
        venue=venue,
        capacity=capacity,
    )
    if slot_weekday is not None:
        ScheduleSlot.objects.create(
            class_group=group, weekday=slot_weekday, start_time=time(7), end_time=time(8), venue=venue
        )
    return group


def make_student(
    email: str = "aluno@teamfarias.com.br",
    group: ClassGroup | None = None,
    plan: Plan | None = None,
    status: str = Student.Status.ATIVO,
    monthly_fee: str = "180.00",
) -> Student:
    user = make_user(email, first_name="Ana", last_name="Lima", role=User.Role.ALUNO)
    student = Student.objects.create(user=user, status=status, level="iniciante")
    if group and plan:
        Enrollment.objects.create(
            student=student,
            class_group=group,
            plan=plan,
            status=Enrollment.Status.ATIVA,
            monthly_fee=Decimal(monthly_fee),
            start_date=date.today(),
        )
    return student


def make_session(group: ClassGroup, *, days_ago: int = 2, status: str = Session.Status.AGENDADO) -> Session:
    day = timezone.localdate() - timedelta(days=days_ago)
    return Session.objects.create(
        class_group=group,
        date=day,
        start_time=time(7),
        end_time=time(8),
        venue=group.venue,
        theme="Saque e recepção",
        status=status,
    )


def make_invoice(student: Student, *, days_overdue: int = 0, status: str = Invoice.Status.ABERTA, fee: str = "180.00"):
    competence = timezone.localdate().replace(day=1)
    return Invoice.objects.create(
        student=student,
        competence=competence,
        amount=Decimal(fee),
        due_date=timezone.localdate() - timedelta(days=days_overdue),
        status=status,
    )
