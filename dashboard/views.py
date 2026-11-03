from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordChangeView
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST

from accounts.models import Student
from billing.models import Invoice, Plan, Payment
from school.models import (
    Announcement,
    Attendance,
    ClassGroup,
    Enrollment,
    PointEntry,
    PointRule,
    Session,
)

from .decorators import staff_required, student_required, team_required
from .forms import (
    AdminEnrollmentForm,
    AnnouncementForm,
    BulkPointsForm,
    ClassGroupForm,
    GenerateInvoicesForm,
    InvoiceForm,
    PointEntryForm,
    PointRuleForm,
    ScheduleSlotFormSet,
    SessionForm,
    StyledPasswordChangeForm,
    StudentEditForm,
    StudentProfileForm,
)
from .services import (
    MONTHS_PT_SHORT,
    accessible_groups,
    approve_enrollment,
    attendance_summary,
    dashboard_metrics,
    finance_overview,
    generate_invoices,
    generate_sessions,
    group_attendance_rate,
    month_calendar,
    panel_metrics,
    ranking,
    recent_activity,
    sessions_between,
    student_position,
    week_bounds,
)


def _month_param(request) -> date:
    raw = request.GET.get("competencia") or request.GET.get("mes")
    if raw:
        try:
            return date.fromisoformat(f"{raw}-01" if len(raw) == 7 else raw).replace(day=1)
        except ValueError:
            pass
    return timezone.localdate().replace(day=1)


def _shift_month(reference: date, months: int) -> date:
    year = reference.year + (reference.month - 1 + months) // 12
    month = (reference.month - 1 + months) % 12 + 1
    return date(year, month, 1)


# =================================================================== roteador
@login_required
def role_redirect(request):
    if request.user.is_admin_role or request.user.is_professor:
        return redirect("dashboard:painel")
    if hasattr(request.user, "student"):
        return redirect("dashboard:home")
    messages.info(request, "Sua conta ainda não está vinculada a um aluno.")
    return redirect("core:home")


# =================================================================== ALUNO
@student_required
def app_home(request):
    student = request.user.student
    enrollment = student.active_enrollment
    group = enrollment.class_group if enrollment else None
    today = timezone.localdate()

    upcoming = []
    if group:
        upcoming = list(
            Session.objects.filter(class_group=group, date__gte=today)
            .exclude(status=Session.Status.CANCELADO)
            .select_related("venue")
            .order_by("date", "start_time")[:4]
        )
    next_session = upcoming[0] if upcoming else None
    invoice = (
        student.invoices.filter(status=Invoice.Status.ABERTA).order_by("due_date").first()
        or student.invoices.order_by("-competence").first()
    )
    position, total_students = student_position(student)
    context = {
        "student": student,
        "enrollment": enrollment,
        "group": group,
        "upcoming": upcoming,
        "next_session": next_session,
        "invoice": invoice,
        "position": position,
        "total_students": total_students,
        "total_points": student.total_points,
        "attendance": attendance_summary(student),
        "announcements": Announcement.objects.filter(
            is_published=True,
            audience__in=[Announcement.Audience.PUBLICO, Announcement.Audience.ALUNOS],
        )[:3],
        "recent_points": student.points.all()[:4],
        "history": student.attendance.select_related("session", "session__class_group").order_by("-session__date")[:5],
    }
    return render(request, "app/home.html", context)


@student_required
def app_profile(request):
    student = request.user.student
    if request.method == "POST":
        form = StudentProfileForm(request.POST, instance=student)
        if form.is_valid():
            form.save()
            messages.success(request, "Perfil atualizado.")
            return redirect("dashboard:profile")
    else:
        form = StudentProfileForm(instance=student)
    return render(
        request,
        "app/profile.html",
        {
            "student": student,
            "form": form,
            "enrollment": student.active_enrollment,
            "invoices": student.invoices.all()[:6],
            "attendance": attendance_summary(student),
        },
    )


@student_required
def app_points(request):
    student = request.user.student
    entries = student.points.select_related("rule", "created_by").order_by("-created_at")
    by_source = list(
        entries.values("source").annotate(total=Sum("points"), count=Count("id")).order_by("-total")
    )
    source_labels = dict(PointEntry.Source.choices)
    for row in by_source:
        row["label"] = source_labels.get(row["source"], row["source"])

    monthly = (
        entries.annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(total=Sum("points"))
        .order_by("month")
    )
    months = list(monthly)[-6:]
    max_month = max([m["total"] or 0 for m in months], default=0) or 1

    position, total_students = student_position(student)
    rows = ranking()
    top = rows[:10]
    mine = next((r for r in rows if r["student"].pk == student.pk), None)
    class_rows = ranking(student.class_group) if student.class_group else []

    context = {
        "student": student,
        "attendance": attendance_summary(student),
        "entries": entries[:24],
        "by_source": by_source,
        "months": [
            {
                "label": MONTHS_PT_SHORT[m["month"].month - 1],
                "total": m["total"] or 0,
                "height": round(abs(m["total"] or 0) * 100 / max_month),
            }
            for m in months
        ],
        "position": position,
        "total_students": total_students,
        "top": top,
        "mine": mine,
        "class_rows": class_rows[:10],
        "total_points": student.total_points,
    }
    return render(request, "app/points.html", context)


@student_required
def app_agenda(request):
    student = request.user.student
    group = student.class_group
    today = timezone.localdate()
    try:
        year = int(request.GET.get("ano", today.year))
        month = int(request.GET.get("mes", today.month))
        if not 1 <= month <= 12:
            raise ValueError
    except ValueError:
        year, month = today.year, today.month

    calendar_ctx = month_calendar(group, year, month)
    upcoming = []
    if group:
        upcoming = (
            Session.objects.filter(class_group=group, date__gte=today)
            .exclude(status=Session.Status.CANCELADO)
            .select_related("venue")
            .order_by("date", "start_time")[:8]
        )
    context = {
        "student": student,
        "group": group,
        "calendar": calendar_ctx,
        "year": year,
        "month": month,
        "upcoming": upcoming,
        "history": student.attendance.select_related("session", "session__class_group").order_by("-session__date")[:12],
        "attendance": attendance_summary(student),
        "status_styles": {"presente": "green", "atraso": "amber", "falta": "red", "justificada": "blue"},
    }
    return render(request, "app/agenda.html", context)


@student_required
def app_invoices(request):
    student = request.user.student
    invoices = student.invoices.select_related("plan").order_by("-competence")
    open_invoices = [i for i in invoices if i.status == Invoice.Status.ABERTA]
    paid = [i for i in invoices if i.status == Invoice.Status.PAGA]
    current = min(open_invoices, key=lambda i: i.due_date) if open_invoices else (invoices[0] if invoices else None)
    context = {
        "student": student,
        "invoices": invoices,
        "open_total": sum((i.total for i in open_invoices), Decimal("0")),
        "paid_total": sum((i.total for i in paid), Decimal("0")),
        "open_count": len(open_invoices),
        "paid_count": len(paid),
        "current": current,
        "payments": Payment.objects.filter(invoice__student=student).order_by("-paid_at")[:8],
    }
    return render(request, "app/invoices.html", context)


@student_required
def app_announcements(request):
    announcements = Announcement.objects.filter(
        is_published=True,
        audience__in=[Announcement.Audience.PUBLICO, Announcement.Audience.ALUNOS],
    )
    return render(request, "app/announcements.html", {"announcements": announcements, "student": request.user.student})


@student_required
def app_announcement_detail(request, pk):
    announcement = get_object_or_404(
        Announcement.objects.filter(
            is_published=True,
            audience__in=[Announcement.Audience.PUBLICO, Announcement.Audience.ALUNOS],
        ),
        pk=pk,
    )
    return render(
        request,
        "app/announcement_detail.html",
        {"announcement": announcement, "student": request.user.student},
    )


@method_decorator(student_required, name="dispatch")
class StudentPasswordChangeView(PasswordChangeView):
    template_name = "app/password_change.html"
    form_class = StyledPasswordChangeForm

    def get_success_url(self):
        messages.success(self.request, "Senha atualizada. Use a nova senha no próximo acesso.")
        return reverse("dashboard:profile")


# =================================================================== PAINEL
@team_required
def painel_home(request):
    user = request.user
    groups = accessible_groups(user)
    metrics = panel_metrics(user)
    monday, sunday = week_bounds()
    pending = (
        Enrollment.objects.filter(status=Enrollment.Status.PENDENTE, class_group__in=groups)
        .select_related("student__user", "student__guardian", "class_group", "plan")
        .order_by("enrolled_at")
    )
    recent_enrollments = (
        Enrollment.objects.filter(class_group__in=groups, status=Enrollment.Status.ATIVA)
        .select_related("student__user", "class_group", "plan")
        .order_by("-enrolled_at")[:5]
    )
    overdue = (
        Invoice.objects.filter(
            status=Invoice.Status.ABERTA, due_date__lt=timezone.localdate(), student__enrollments__class_group__in=groups
        )
        .select_related("student__user")
        .distinct()
        .order_by("due_date")[:6]
    )
    context = {
        "metrics": metrics,
        "pending": pending[:5],
        "pending_total": pending.count(),
        "recent_enrollments": recent_enrollments,
        "week_sessions": sessions_between(monday, sunday, groups=groups)[:8],
        "overdue": overdue,
        "ranking": ranking(groups=groups)[:8],
        "activity": recent_activity(7) if user.is_admin_role else [],
        "groups": ClassGroup.objects.filter(is_active=True, pk__in=groups.values("pk")).annotate(
            active_count=Count("enrollments", filter=Q(enrollments__status="ativa"))
        ),
        "today": timezone.localdate(),
    }
    return render(request, "painel/home.html", context)


@staff_required
def painel_enrollments(request):
    status = request.GET.get("status", Enrollment.Status.ATIVA)
    if status not in dict(Enrollment.Status.choices):
        status = Enrollment.Status.ATIVA

    if request.method == "POST":
        enrollment = get_object_or_404(Enrollment, pk=request.POST.get("enrollment"))
        action = request.POST.get("action")
        if action == "approve":
            group = None
            plan = None
            if request.POST.get("class_group"):
                group = get_object_or_404(ClassGroup, pk=request.POST["class_group"])
            if request.POST.get("plan"):
                plan = get_object_or_404(Plan, pk=request.POST["plan"])
            approve_enrollment(enrollment, request.user, group=group, plan=plan)
            messages.success(
                request,
                f"Matrícula de {enrollment.student.full_name} aprovada. Mensalidade inicial gerada.",
            )
        elif action == "reject":
            enrollment.status = Enrollment.Status.REJEITADA
            enrollment.save(update_fields=["status"])
            student = enrollment.student
            student.status = Student.Status.INATIVO
            student.save(update_fields=["status"])
            messages.warning(request, f"Matrícula de {enrollment.student.full_name} recusada.")
        return redirect(f"{reverse('dashboard:enrollments')}?status={status}")

    enrollments = (
        Enrollment.objects.filter(status=status)
        .select_related("student__user", "student__guardian", "class_group", "plan", "approved_by")
        .order_by("-enrolled_at")
    )
    counts = {row["status"]: row["n"] for row in Enrollment.objects.values("status").annotate(n=Count("id"))}
    tab_order = [
        Enrollment.Status.ATIVA,
        Enrollment.Status.PENDENTE,
        Enrollment.Status.REJEITADA,
        Enrollment.Status.CANCELADA,
    ]
    labels = dict(Enrollment.Status.choices)
    context = {
        "enrollments": enrollments,
        "status": status,
        "tabs": [{"key": key, "label": labels[key], "count": counts.get(key, 0)} for key in tab_order],
        "groups": ClassGroup.objects.filter(is_active=True),
        "plans": Plan.objects.filter(is_active=True),
    }
    return render(request, "painel/enrollments.html", context)


@staff_required
def painel_enrollment_create(request):
    if request.method == "POST":
        form = AdminEnrollmentForm(request.POST)
        if form.is_valid():
            user, student, enrollment, password, generated = form.save(request.user)
            request.session["created_enrollment"] = {
                "student_id": student.pk,
                "name": user.full_name,
                "email": user.email,
                "password": password,
                "generated": generated,
                "group": enrollment.class_group.name,
                "plan": enrollment.plan.name,
                "fee": str(enrollment.monthly_fee),
            }
            messages.success(request, "Matrícula criada e acesso liberado.")
            return redirect("dashboard:enrollment_created", pk=student.pk)
        messages.error(request, "Confira os dados da matrícula.")
    else:
        form = AdminEnrollmentForm()

    return render(
        request,
        "painel/enrollment_form.html",
        {"form": form, "groups": ClassGroup.objects.filter(is_active=True), "plans": Plan.objects.filter(is_active=True)},
    )


@staff_required
def painel_enrollment_created(request, pk):
    student = get_object_or_404(Student.objects.select_related("user"), pk=pk)
    created = request.session.pop("created_enrollment", None) or {}
    if created.get("student_id") != student.pk:
        messages.info(request, "Os dados de acesso só aparecem uma vez, logo após a matrícula.")
        return redirect("dashboard:student_detail", pk=student.pk)

    enrollment = student.active_enrollment
    whatsapp_message = (
        f"Olá, {student.display_name}! Sua matrícula no Team Farias está ativa. "
        f"Acesse {request.build_absolute_uri(reverse('accounts:login'))} com o e-mail {created.get('email')} "
        f"e a senha {created.get('password')}. Turma: {enrollment.class_group.name if enrollment else '-'}."
    )
    context = {
        "student": student,
        "enrollment": enrollment,
        "credentials": created,
        "whatsapp_text": quote(whatsapp_message),
    }
    return render(request, "painel/enrollment_created.html", context)


@team_required
def painel_students(request):
    groups = accessible_groups(request.user)
    qs = (
        Student.objects.filter(enrollments__class_group__in=groups)
        .select_related("user", "guardian")
        .prefetch_related("enrollments__class_group")
        .annotate(points_total=Sum("points__points"))
        .distinct()
        .order_by("user__first_name")
    )
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(user__first_name__icontains=q)
            | Q(user__last_name__icontains=q)
            | Q(user__email__icontains=q)
            | Q(nickname__icontains=q)
        )
    group_id = request.GET.get("turma")
    if group_id:
        qs = qs.filter(enrollments__status=Enrollment.Status.ATIVA, enrollments__class_group_id=group_id)
    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)

    page = Paginator(qs, 15).get_page(request.GET.get("page"))
    context = {
        "page": page,
        "students": page.object_list,
        "q": q,
        "groups": groups.filter(is_active=True),
        "selected_group": group_id or "",
        "selected_status": status or "",
        "statuses": Student.Status.choices,
        "total": qs.count(),
    }
    return render(request, "painel/students.html", context)


@team_required
def painel_student_detail(request, pk):
    student = get_object_or_404(Student.objects.select_related("user", "guardian"), pk=pk)
    if not request.user.is_admin_role and not student.enrollments.filter(
        status=Enrollment.Status.ATIVA, class_group__professor=request.user
    ).exists():
        raise PermissionDenied("Este aluno não está em uma das suas turmas.")
    edit_form = StudentEditForm(instance=student)
    point_form = PointEntryForm(
        user=request.user, initial={"student": student, "source": PointEntry.Source.DESEMPENHO}
    )

    if request.method == "POST":
        action = request.POST.get("action", "edit")
        if action == "points":
            point_form = PointEntryForm(request.POST, user=request.user)
            if point_form.is_valid():
                point_form.save(user=request.user)
                messages.success(request, "Pontos lançados.")
                return redirect("dashboard:student_detail", pk=student.pk)
            messages.error(request, "Não foi possível lançar os pontos. Confira o formulário.")
        else:
            edit_form = StudentEditForm(request.POST, instance=student)
            if edit_form.is_valid():
                edit_form.save()
                messages.success(request, "Cadastro atualizado.")
                return redirect("dashboard:student_detail", pk=student.pk)
            messages.error(request, "Confira os dados do cadastro.")

    enrollment = student.active_enrollment
    context = {
        "student": student,
        "enrollment": enrollment,
        "edit_form": edit_form,
        "point_form": point_form,
        "attendance": attendance_summary(student),
        "attendance_rows": student.attendance.select_related("session", "session__class_group").order_by(
            "-session__date"
        )[:10],
        "points": student.points.select_related("rule", "created_by")[:10],
        "invoices": student.invoices.all()[:8],
        "position": student_position(student)[0],
        "class_rows": ranking(enrollment.class_group)[:8] if enrollment else [],
    }
    return render(request, "painel/student_detail.html", context)


@team_required
def painel_classes(request):
    groups = (
        accessible_groups(request.user)
        .select_related("professor", "venue")
        .prefetch_related("slots", "enrollments")
        .annotate(active_count=Count("enrollments", filter=Q(enrollments__status="ativa")))
        .order_by("name")
    )
    context = {
        "groups": groups,
        "total_students": Student.objects.filter(status=Student.Status.ATIVO, enrollments__class_group__in=groups)
        .distinct()
        .count(),
        "total_seats": sum(g.capacity for g in groups),
    }
    return render(request, "painel/classes.html", context)


@staff_required
def painel_class_form(request, pk=None):
    group = get_object_or_404(ClassGroup, pk=pk) if pk else None
    if request.method == "POST":
        form = ClassGroupForm(request.POST, instance=group)
        formset = ScheduleSlotFormSet(request.POST, instance=group)
        if form.is_valid() and formset.is_valid():
            group = form.save()
            formset.instance = group
            formset.save()
            messages.success(request, "Turma salva com sucesso.")
            return redirect("dashboard:classes")
        messages.error(request, "Confira os dados da turma e dos horários.")
    else:
        form = ClassGroupForm(instance=group)
        formset = ScheduleSlotFormSet(instance=group)
    return render(request, "painel/class_form.html", {"form": form, "formset": formset, "group": group})


@staff_required
def painel_billing(request):
    competence = _month_param(request)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "generate":
            form = GenerateInvoicesForm(request.POST)
            if form.is_valid():
                created = generate_invoices(form.cleaned_data["competence"], user=request.user)
                messages.success(request, f"{created} mensalidade(s) gerada(s).")
                return redirect(f"{reverse('dashboard:billing')}?competencia={form.cleaned_data['competence']:%Y-%m}")
            messages.error(request, "Informe a competência no formato mês/ano.")
        elif action == "pay":
            invoice = get_object_or_404(Invoice, pk=request.POST.get("invoice"))
            method = request.POST.get("method", Invoice.Method.PIX)
            invoice.mark_paid(user=request.user, method=method, note=request.POST.get("note", ""))
            messages.success(request, f"Mensalidade de {invoice.student.display_name} confirmada.")
        elif action == "reopen":
            invoice = get_object_or_404(Invoice, pk=request.POST.get("invoice"))
            invoice.reopen()
            messages.warning(request, "Mensalidade reaberta.")
        elif action == "create":
            form = InvoiceForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, "Mensalidade criada.")
            else:
                messages.error(request, "Não foi possível criar a mensalidade.")
        return redirect(f"{reverse('dashboard:billing')}?competencia={competence:%Y-%m}")

    invoices = (
        Invoice.objects.filter(competence=competence)
        .select_related("student__user", "plan")
        .order_by("status", "due_date")
    )
    status_filter = request.GET.get("status")
    if status_filter == "aberta":
        invoices = invoices.filter(status=Invoice.Status.ABERTA)
    elif status_filter == "paga":
        invoices = invoices.filter(status=Invoice.Status.PAGA)
    q = request.GET.get("q", "").strip()
    if q:
        invoices = invoices.filter(student__user__first_name__icontains=q)

    context = {
        "invoices": invoices[:200],
        "overview": finance_overview(competence),
        "competence": competence,
        "prev_month": _shift_month(competence, -1),
        "next_month": _shift_month(competence, 1),
        "generate_form": GenerateInvoicesForm(initial={"competence": competence}),
        "invoice_form": InvoiceForm(initial={"competence": competence}),
        "status_filter": status_filter or "",
        "q": q,
        "recent_payments": Payment.objects.select_related("invoice__student__user").order_by(
            "-paid_at", "-created_at"
        )[:6],
        "overdue_total": Invoice.objects.overdue().aggregate(v=Sum("amount"))["v"] or 0,
        "current": timezone.localdate().replace(day=1),
    }
    return render(request, "painel/billing.html", context)


@team_required
def painel_agenda(request):
    if request.method == "POST" and request.POST.get("action") == "generate":
        created = generate_sessions(weeks=4)
        messages.success(request, f"{created} treino(s) gerado(s) a partir dos horários das turmas.")
        return redirect("dashboard:sessions")

    try:
        start = date.fromisoformat(request.GET.get("inicio", ""))
    except ValueError:
        start = week_bounds()[0]
    start = start - timedelta(days=start.weekday())
    end = start + timedelta(days=6)
    groups = accessible_groups(request.user)
    group_filter = request.GET.get("turma")
    sessions = list(sessions_between(start, end, groups=groups))
    if group_filter:
        sessions = [s for s in sessions if str(s.class_group_id) == group_filter]

    days = []
    for i in range(7):
        day = start + timedelta(days=i)
        days.append({"date": day, "sessions": [s for s in sessions if s.date == day]})

    context = {
        "days": days,
        "start": start,
        "end": end,
        "prev": start - timedelta(days=7),
        "next": start + timedelta(days=7),
        "groups": groups.filter(is_active=True),
        "group_filter": group_filter or "",
        "week_total": len(sessions),
    }
    return render(request, "painel/agenda.html", context)


@team_required
def painel_session_form(request, pk=None):
    session = get_object_or_404(Session, pk=pk) if pk else None
    if request.method == "POST":
        form = SessionForm(request.POST, instance=session, user=request.user)
        if form.is_valid():
            saved = form.save()
            messages.success(request, "Treino salvo na agenda.")
            return redirect(f"{reverse('dashboard:sessions')}?inicio={saved.date.isoformat()}")
    else:
        form = SessionForm(instance=session, user=request.user)
    return render(request, "painel/session_form.html", {"form": form, "session": session})


@team_required
def painel_attendance(request, pk):
    session = get_object_or_404(Session.objects.select_related("class_group", "venue"), pk=pk)
    if not request.user.is_admin_role and session.class_group.professor_id != request.user.pk:
        messages.error(request, "Você só pode registrar presença nas suas turmas.")
        return redirect("dashboard:sessions")

    roster = (
        Student.objects.filter(
            enrollments__status=Enrollment.Status.ATIVA,
            enrollments__class_group=session.class_group,
            status=Student.Status.ATIVO,
        )
        .select_related("user")
        .order_by("user__first_name")
    )

    if request.method == "POST":
        if request.POST.get("action") == "cancel":
            session.status = Session.Status.CANCELADO
            session.canceled_reason = request.POST.get("reason", "")[:160]
            session.save(update_fields=["status", "canceled_reason"])
            messages.warning(request, "Treino cancelado.")
            return redirect("dashboard:sessions")

        saved = 0
        for student in roster:
            status = request.POST.get(f"status_{student.pk}")
            note = request.POST.get(f"note_{student.pk}", "")
            if not status:
                Attendance.objects.filter(session=session, student=student).delete()
                continue
            if status not in dict(Attendance.Status.choices):
                continue
            Attendance.objects.update_or_create(
                session=session,
                student=student,
                defaults={"status": status, "note": note, "recorded_by": request.user},
            )
            saved += 1
        if request.POST.get("mark_done"):
            session.status = Session.Status.REALIZADO
            session.save(update_fields=["status"])
        messages.success(request, f"Presença de {saved} atleta(s) registrada.")
        return redirect(f"{reverse('dashboard:sessions')}?inicio={session.date.isoformat()}")

    existing = {a.student_id: a for a in session.attendance.all()}
    rows = [{"student": s, "attendance": existing.get(s.pk)} for s in roster]
    context = {
        "session": session,
        "rows": rows,
        "present_count": session.confirmed_count,
        "rate": session.attendance_rate,
        "statuses": Attendance.Status.choices,
    }
    return render(request, "painel/attendance.html", context)


@team_required
def painel_points(request):
    if request.method == "POST":
        action = request.POST.get("action", "single")
        if action == "single":
            form = PointEntryForm(request.POST, user=request.user)
            if form.is_valid():
                form.save(user=request.user)
                messages.success(request, "Pontos lançados para o atleta.")
                return redirect("dashboard:points_admin")
            messages.error(request, "Confira os dados do lançamento.")
        elif action == "bulk":
            bulk_form = BulkPointsForm(request.POST, user=request.user)
            if bulk_form.is_valid():
                group = bulk_form.cleaned_data["class_group"]
                targets = Student.objects.filter(
                    enrollments__status=Enrollment.Status.ATIVA,
                    enrollments__class_group=group,
                    status=Student.Status.ATIVO,
                ).distinct()
                entries = [
                    PointEntry(
                        student=student,
                        points=bulk_form.cleaned_data["points"],
                        reason=bulk_form.cleaned_data["reason"],
                        rule=bulk_form.cleaned_data["rule"],
                        source=bulk_form.cleaned_data["source"],
                        created_by=request.user,
                    )
                    for student in targets
                ]
                PointEntry.objects.bulk_create(entries)
                messages.success(request, f"{len(entries)} lançamento(s) criado(s) para a turma {group}.")
                return redirect("dashboard:points_admin")
            messages.error(request, "Confira os dados do lançamento coletivo.")
        elif action == "rule":
            rule_form = PointRuleForm(request.POST)
            if rule_form.is_valid():
                rule_form.save()
                messages.success(request, "Regra de pontuação salva.")
                return redirect("dashboard:points_admin")

    group_filter = request.GET.get("turma")
    entries = PointEntry.objects.select_related("student__user", "rule", "created_by")
    if group_filter:
        entries = entries.filter(
            student__enrollments__status=Enrollment.Status.ATIVA,
            student__enrollments__class_group_id=group_filter,
        )
    selected_group = ClassGroup.objects.filter(pk=group_filter).first() if group_filter else None
    rows = ranking(selected_group)
    context = {
        "point_form": PointEntryForm(user=request.user),
        "bulk_form": BulkPointsForm(user=request.user),
        "rule_form": PointRuleForm(),
        "rules": PointRule.objects.all(),
        "entries": entries[:18],
        "ranking": rows,
        "groups": accessible_groups(request.user).filter(is_active=True),
        "group_filter": group_filter or "",
        "total_points_month": PointEntry.objects.filter(
            created_at__year=timezone.localdate().year, created_at__month=timezone.localdate().month
        ).aggregate(v=Sum("points"))["v"]
        or 0,
    }
    return render(request, "painel/points.html", context)


@staff_required
def painel_announcements(request):
    return render(
        request,
        "painel/announcements.html",
        {
            "announcements": Announcement.objects.select_related("author").order_by("-created_at"),
            "counts": {
                "publico": Announcement.objects.filter(audience="publico").count(),
                "alunos": Announcement.objects.filter(audience="alunos").count(),
            },
        },
    )


@staff_required
def painel_announcement_form(request, pk=None):
    announcement = get_object_or_404(Announcement, pk=pk) if pk else None
    if request.method == "POST":
        form = AnnouncementForm(request.POST, instance=announcement)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.author = obj.author or request.user
            obj.save()
            messages.success(request, "Comunicado salvo.")
            return redirect("dashboard:announcements_admin")
        messages.error(request, "Confira os dados do comunicado.")
    else:
        form = AnnouncementForm(instance=announcement)
    return render(request, "painel/announcement_form.html", {"form": form, "announcement": announcement})


@staff_required
@require_POST
def painel_announcement_toggle(request, pk):
    announcement = get_object_or_404(Announcement, pk=pk)
    announcement.is_published = not announcement.is_published
    announcement.save(update_fields=["is_published"])
    messages.success(request, "Comunicado atualizado.")
    return redirect("dashboard:announcements_admin")


@staff_required
def painel_reports(request):
    groups = ClassGroup.objects.filter(is_active=True).annotate(
        active_count=Count("enrollments", filter=Q(enrollments__status="ativa"))
    )
    group_rows = [
        {
            "group": group,
            "students": group.active_count,
            "occupancy": round(group.active_count * 100 / group.capacity) if group.capacity else 0,
            "attendance": group_attendance_rate(group),
        }
        for group in groups
    ]

    base = timezone.localdate().replace(day=1)
    months = []
    for offset in range(5, -1, -1):
        ref = _shift_month(base, -offset)
        invoices = Invoice.objects.filter(competence=ref)
        months.append(
            {
                "label": ref.strftime("%m/%y"),
                "billed": invoices.aggregate(v=Sum("amount"))["v"] or 0,
                "paid": invoices.filter(status=Invoice.Status.PAGA).aggregate(v=Sum("amount"))["v"] or 0,
                "count": invoices.count(),
            }
        )
    max_billed = max([float(m["billed"]) for m in months], default=0) or 1

    context = {
        "group_rows": group_rows,
        "months": [
            {
                **m,
                "height": round(float(m["billed"]) * 100 / max_billed),
                "paid_height": round(float(m["paid"]) * 100 / max_billed),
            }
            for m in months
        ],
        "ranking": ranking()[:8],
        "metrics": dashboard_metrics(),
        "top_attendance": [
            {"student": row["student"], "rate": attendance_summary(row["student"], days=60)}
            for row in ranking()[:6]
        ],
    }
    return render(request, "painel/reports.html", context)


@staff_required
def painel_settings(request):
    from core.models import SiteConfiguration
    from .forms import SiteConfigurationForm, SinglePlanForm
    config = SiteConfiguration.current()
    plan = Plan.objects.filter(is_active=True).first()
    action = request.POST.get("action") if request.method == "POST" else None
    form = SiteConfigurationForm(request.POST if action == "site" else None, instance=config)
    plan_form = SinglePlanForm(request.POST if action == "plan" else None, instance=plan, initial={"name": "Plano único"}, auto_id="id_billing_%s")
    if action == "site" and form.is_valid():
        form.save()
        messages.success(request, "Configurações atualizadas.")
        return redirect("dashboard:settings")
    if action == "plan" and plan_form.is_valid():
        plan_form.save()
        messages.success(request, "Plano único atualizado. Matrículas anteriores mantêm seus valores.")
        return redirect("dashboard:settings")
    return render(request, "painel/settings.html", {"form": form, "plan_form": plan_form})
