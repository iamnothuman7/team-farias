from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db.models import DecimalField, IntegerField, Sum, Value, F
from django.db import transaction
from django.core.exceptions import ValidationError
from django.db.models.functions import Coalesce
from django.utils import timezone

from accounts.models import Student
from billing.models import Invoice, Plan, suggested_due_date
from school.models import (
    Attendance,
    ClassGroup,
    Enrollment,
    PointEntry,
    ScheduleSlot,
    Session,
)

ZERO_MONEY = Value(Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2))

MONTHS_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]
MONTHS_PT_SHORT = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


# --------------------------------------------------------------- pontuação
def ranking(
    class_group: ClassGroup | None = None,
    *,
    groups=None,
    only_active: bool = True,
) -> list[dict]:
    qs = (
        Student.objects.select_related("user")
        .prefetch_related("enrollments__class_group")
        .annotate(points_total=Coalesce(Sum("points__points"), Value(0), output_field=IntegerField()))
    )
    if only_active:
        qs = qs.filter(status=Student.Status.ATIVO)
    if class_group is not None:
        qs = qs.filter(enrollments__status=Enrollment.Status.ATIVA, enrollments__class_group=class_group)
    elif groups is not None:
        qs = qs.filter(enrollments__status=Enrollment.Status.ATIVA, enrollments__class_group__in=groups)
    qs = qs.distinct().order_by("-points_total", "user__first_name", "user__last_name")

    return [{"position": index, "student": s, "points": s.points_total or 0} for index, s in enumerate(qs, start=1)]


def student_position(student: Student) -> tuple[int | None, int]:
    rows = ranking()
    for row in rows:
        if row["student"].pk == student.pk:
            return row["position"], len(rows)
    return None, len(rows)


# --------------------------------------------------------------- treinos
def generate_sessions(*, weeks: int = 4, start: date | None = None, only_missing: bool = True, groups=None) -> int:
    """Materializa os treinos a partir dos horários fixos das turmas."""
    start = start or timezone.localdate()
    end = start + timedelta(days=weeks * 7)
    created = 0
    slots = ScheduleSlot.objects.filter(class_group__is_active=True).select_related("class_group", "venue")
    if groups is not None:
        slots = slots.filter(class_group__in=groups)
    for slot in slots:
        cursor = start
        while cursor <= end:
            if cursor.weekday() == slot.weekday:
                if only_missing:
                    _, was_created = Session.objects.get_or_create(
                        class_group=slot.class_group,
                        date=cursor,
                        start_time=slot.start_time,
                        defaults={"end_time": slot.end_time, "venue": slot.venue or slot.class_group.venue},
                    )
                    created += int(was_created)
            cursor += timedelta(days=1)
    return created


def week_bounds(reference: date | None = None) -> tuple[date, date]:
    reference = reference or timezone.localdate()
    monday = reference - timedelta(days=reference.weekday())
    return monday, monday + timedelta(days=6)


def sessions_between(start: date, end: date, groups=None, professor=None):
    qs = (
        Session.objects.filter(date__gte=start, date__lte=end)
        .select_related("class_group", "venue", "class_group__professor")
        .prefetch_related("attendance")
        .order_by("date", "start_time")
    )
    if groups is not None:
        qs = qs.filter(class_group__in=groups)
    if professor is not None:
        qs = qs.filter(class_group__professor=professor)
    return qs


def accessible_groups(user):
    """Turmas que o usuário pode administrar."""
    if user.is_admin_role:
        return ClassGroup.objects.all()
    return ClassGroup.objects.filter(professor=user)


def attendance_summary(student: Student, *, days: int = 90) -> dict:
    since = timezone.localdate() - timedelta(days=days)
    records = student.attendance.filter(session__date__gte=since).exclude(
        status=Attendance.Status.JUSTIFICADA
    )
    total = records.count()
    present = records.filter(status__in=[Attendance.Status.PRESENTE, Attendance.Status.ATRASO]).count()
    rate = round(present * 100 / total) if total else 0
    return {"total": total, "present": present, "rate": rate, "since": since}


def group_attendance_rate(group: ClassGroup, *, days: int = 30) -> int:
    since = timezone.localdate() - timedelta(days=days)
    records = Attendance.objects.filter(session__class_group=group, session__date__gte=since).exclude(
        status=Attendance.Status.JUSTIFICADA
    )
    total = records.count()
    if not total:
        return 0
    present = records.filter(status__in=[Attendance.Status.PRESENTE, Attendance.Status.ATRASO]).count()
    return round(present * 100 / total)


# --------------------------------------------------------------- financeiro
def generate_invoices(competence: date, *, user=None) -> int:
    """Cria as mensalidades do mês para todas as matrículas ativas."""
    competence = competence.replace(day=1)
    created = 0
    enrollments = Enrollment.objects.filter(status=Enrollment.Status.ATIVA).select_related("student", "plan")
    for enrollment in enrollments:
        exists = Invoice.objects.filter(student=enrollment.student, competence=competence).exists()
        if exists:
            continue
        plan = enrollment.plan
        due = suggested_due_date(competence, plan)
        _, was_created = Invoice.objects.get_or_create(
            student=enrollment.student,
            competence=competence,
            defaults={"plan": plan, "amount": enrollment.monthly_fee, "due_date": due},
        )
        created += int(was_created)
    return created


def first_invoice_for(enrollment: Enrollment, *, user=None) -> Invoice | None:
    competence = timezone.localdate().replace(day=1)
    invoice, _ = Invoice.objects.get_or_create(
        student=enrollment.student,
        competence=competence,
        defaults={
            "plan": enrollment.plan,
            "amount": enrollment.monthly_fee,
            "due_date": max(suggested_due_date(competence, enrollment.plan), timezone.localdate()),
        },
    )
    return invoice


@transaction.atomic
def approve_enrollment(enrollment: Enrollment, user, *, group: ClassGroup | None = None, plan: Plan | None = None):
    enrollment = Enrollment.objects.select_for_update().get(pk=enrollment.pk)
    Student.objects.select_for_update().get(pk=enrollment.student_id)
    if enrollment.status == Enrollment.Status.ATIVA:
        return enrollment
    if enrollment.status != Enrollment.Status.PENDENTE:
        raise ValidationError("Somente matrículas pendentes podem ser aprovadas.")
    group = ClassGroup.objects.select_for_update().get(pk=(group or enrollment.class_group).pk)
    plan = Plan.objects.select_for_update().get(pk=(plan or enrollment.plan).pk)
    if not group.is_active or group.free_spots <= 0:
        raise ValidationError("A turma está inativa ou sem vagas.")
    if not plan.is_active:
        raise ValidationError("Selecione um plano ativo.")
    if Enrollment.objects.filter(student=enrollment.student, status="ativa").exists():
        raise ValidationError("Este aluno já tem uma matrícula ativa.")
    if group:
        enrollment.class_group = group
    if plan:
        enrollment.plan = plan
        enrollment.monthly_fee = plan.monthly_fee
    enrollment.save()
    enrollment.approve(user)
    first_invoice_for(enrollment, user=user)
    return enrollment


def finance_overview(competence: date | None = None) -> dict:
    competence = (competence or timezone.localdate()).replace(day=1)
    invoices = Invoice.objects.filter(competence=competence)
    totals = invoices.aggregate(
        billed=Coalesce(Sum(F("amount") - F("discount")), ZERO_MONEY),
        discount=Coalesce(Sum("discount"), ZERO_MONEY),
    )
    paid = invoices.filter(status=Invoice.Status.PAGA).aggregate(v=Coalesce(Sum(F("amount") - F("discount")), ZERO_MONEY))["v"]
    open_ = invoices.filter(status=Invoice.Status.ABERTA).aggregate(v=Coalesce(Sum(F("amount") - F("discount")), ZERO_MONEY))["v"]
    overdue_qs = Invoice.objects.filter(status=Invoice.Status.ABERTA).filter(due_date__lt=timezone.localdate())
    return {
        "competence": competence,
        "count": invoices.count(),
        "billed": totals["billed"],
        "paid": paid,
        "open": open_,
        "overdue_count": overdue_qs.count(),
        "overdue_total": overdue_qs.aggregate(v=Coalesce(Sum(F("amount") - F("discount")), ZERO_MONEY))["v"],
        "paid_rate": round(float(paid) * 100 / float(totals["billed"] or 1)) if totals["billed"] else 0,
    }


# --------------------------------------------------------------- calendário
def month_calendar(group: ClassGroup | None, year: int, month: int) -> dict:
    today = timezone.localdate()
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    grid_start = first - timedelta(days=first.weekday())
    grid_end = last + timedelta(days=6 - last.weekday())

    qs = Session.objects.filter(date__gte=grid_start, date__lte=grid_end).select_related("class_group", "venue")
    qs = qs.filter(class_group=group) if group is not None else qs.none()
    by_day: dict[date, list[Session]] = {}
    for session in qs:
        by_day.setdefault(session.date, []).append(session)

    weeks, cursor = [], grid_start
    while cursor <= grid_end:
        week = []
        for i in range(7):
            day = cursor + timedelta(days=i)
            week.append(
                {
                    "date": day,
                    "in_month": day.month == month,
                    "is_today": day == today,
                    "sessions": by_day.get(day, []),
                }
            )
        weeks.append(week)
        cursor += timedelta(days=7)

    return {
        "weeks": weeks,
        "label": f"{MONTHS_PT[month - 1].capitalize()} de {year}",
        "first": first,
        "prev": (first - timedelta(days=1)).replace(day=1),
        "next": (last + timedelta(days=1)).replace(day=1),
        "weekday_names": ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"],
    }


# --------------------------------------------------------------- painel
def panel_metrics(user) -> dict:
    """Indicadores do painel, limitados às turmas do usuário (professor) ou a todas (admin)."""
    today = timezone.localdate()
    monday, sunday = week_bounds(today)
    groups = accessible_groups(user)
    month_start = today.replace(day=1)

    students = Student.objects.filter(
        status=Student.Status.ATIVO,
        enrollments__status=Enrollment.Status.ATIVA,
        enrollments__class_group__in=groups,
    ).distinct()
    week_sessions = Session.objects.filter(
        class_group__in=groups, date__gte=monday, date__lte=sunday
    ).exclude(status=Session.Status.CANCELADO)
    recent_attendance = Attendance.objects.filter(
        session__class_group__in=groups, session__date__gte=today - timedelta(days=30)
    ).exclude(status=Attendance.Status.JUSTIFICADA)
    total_att = recent_attendance.count()
    present_att = recent_attendance.filter(
        status__in=[Attendance.Status.PRESENTE, Attendance.Status.ATRASO]
    ).count()

    invoices = Invoice.objects.filter(competence=month_start, student__in=students)
    overdue = Invoice.objects.filter(status=Invoice.Status.ABERTA, due_date__lt=today, student__in=students)

    return {
        "active_students": students.count(),
        "pending_enrollments": Enrollment.objects.filter(
            status=Enrollment.Status.PENDENTE, class_group__in=groups
        ).count(),
        "new_enrollments": Enrollment.objects.filter(
            class_group__in=groups, enrolled_at__date__gte=month_start
        ).count(),
        "groups": groups.filter(is_active=True).count(),
        "week_sessions": week_sessions.count(),
        "attendance_rate": round(present_att * 100 / total_att) if total_att else 0,
        "month_billed": invoices.aggregate(v=Coalesce(Sum(F("amount") - F("discount")), ZERO_MONEY))["v"],
        "month_paid": invoices.filter(status=Invoice.Status.PAGA).aggregate(v=Coalesce(Sum(F("amount") - F("discount")), ZERO_MONEY))["v"],
        "overdue_count": overdue.count(),
        "overdue_total": overdue.aggregate(v=Coalesce(Sum(F("amount") - F("discount")), ZERO_MONEY))["v"],
        "new_students": students.filter(created_at__date__gte=month_start).count(),
        "points_month": PointEntry.objects.filter(
            student__in=students, created_at__date__gte=month_start
        ).aggregate(v=Coalesce(Sum("points"), Value(0)))["v"],
    }


def dashboard_metrics() -> dict:
    today = timezone.localdate()
    monday, sunday = week_bounds(today)
    active = Student.objects.filter(status=Student.Status.ATIVO)
    month_start = today.replace(day=1)

    week_sessions = Session.objects.filter(date__gte=monday, date__lte=sunday).exclude(
        status=Session.Status.CANCELADO
    )
    recent_attendance = Attendance.objects.filter(session__date__gte=today - timedelta(days=30)).exclude(
        status=Attendance.Status.JUSTIFICADA
    )
    total_att = recent_attendance.count()
    present_att = recent_attendance.filter(status__in=[Attendance.Status.PRESENTE, Attendance.Status.ATRASO]).count()

    invoices = Invoice.objects.filter(competence=month_start)
    overdue = Invoice.objects.filter(status=Invoice.Status.ABERTA, due_date__lt=today)

    return {
        "active_students": active.count(),
        "pending_enrollments": Enrollment.objects.filter(status=Enrollment.Status.PENDENTE).count(),
        "groups": ClassGroup.objects.filter(is_active=True).count(),
        "week_sessions": week_sessions.count(),
        "attendance_rate": round(present_att * 100 / total_att) if total_att else 0,
        "month_billed": invoices.aggregate(v=Coalesce(Sum(F("amount") - F("discount")), ZERO_MONEY))["v"],
        "month_paid": invoices.filter(status=Invoice.Status.PAGA).aggregate(v=Coalesce(Sum(F("amount") - F("discount")), ZERO_MONEY))["v"],
        "overdue_count": overdue.count(),
        "overdue_total": overdue.aggregate(v=Coalesce(Sum(F("amount") - F("discount")), ZERO_MONEY))["v"],
        "new_students": active.filter(created_at__date__gte=month_start).count(),
        "points_month": PointEntry.objects.filter(created_at__date__gte=month_start).aggregate(
            v=Coalesce(Sum("points"), Value(0))
        )["v"],
    }


def recent_activity(limit: int = 8) -> list[dict]:
    items: list[dict] = []
    for entry in PointEntry.objects.select_related("student__user")[:limit]:
        items.append(
            {
                "when": entry.created_at,
                "icon": "star",
                "title": f"{entry.student.display_name} recebeu {entry.points:+d} pontos",
                "detail": entry.reason,
                "tone": "violet",
            }
        )
    for enrollment in Enrollment.objects.select_related("student__user", "class_group")[:limit]:
        items.append(
            {
                "when": enrollment.enrolled_at,
                "icon": "user",
                "title": f"Nova inscrição: {enrollment.student.full_name}",
                "detail": f"{enrollment.class_group.name} · {enrollment.get_status_display()}",
                "tone": "blue",
            }
        )
    for invoice in Invoice.objects.filter(status=Invoice.Status.PAGA).select_related("student__user")[:limit]:
        items.append(
            {
                "when": timezone.make_aware(datetime.combine(invoice.paid_at, datetime.min.time()))
                if invoice.paid_at
                else invoice.updated_at,
                "icon": "cash",
                "title": f"Mensalidade paga — {invoice.student.display_name}",
                "detail": f"{invoice.competence_label} · R$ {invoice.total}",
                "tone": "green",
            }
        )
    items.sort(key=lambda i: i["when"], reverse=True)
    return items[:limit]
