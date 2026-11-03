from __future__ import annotations

from datetime import date

from django import forms
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from django.utils import timezone
from django.utils.crypto import get_random_string

from accounts.models import Guardian, Student, User
from billing.models import Invoice, Plan
from school.models import Announcement, ClassGroup, Enrollment, PointEntry, PointRule, ScheduleSlot, Session, Venue


class StyledFormMixin:
    """Aplica classes utilitárias do design system em todos os campos."""

    def _style(self):
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "checkbox")
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault("class", "select")
            elif isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("class", "input textarea")
            else:
                widget.attrs.setdefault("class", "input")
            if field.required:
                widget.attrs.setdefault("data-required", "true")


# ------------------------------------------------------------------ alunos
class StyledPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "input")


class AdminEnrollmentForm(StyledFormMixin, forms.Form):
    """Matrícula feita exclusivamente pela administração."""

    # atleta
    first_name = forms.CharField(label="Nome", max_length=80)
    last_name = forms.CharField(label="Sobrenome", max_length=80, required=False)
    email = forms.EmailField(label="E-mail de acesso")
    phone = forms.CharField(label="WhatsApp", max_length=24)
    birth_date = forms.DateField(label="Data de nascimento", widget=forms.DateInput(attrs={"type": "date"}))
    level = forms.ChoiceField(label="Nível", choices=Student.Level.choices, initial=Student.Level.INICIANTE)
    position = forms.CharField(label="Posição preferida", max_length=40, required=False)
    health_notes = forms.CharField(
        label="Observações de saúde",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Lesões, alergias, asma… (opcional)"}),
    )
    # turma e plano
    class_group = forms.ModelChoiceField(label="Turma", queryset=ClassGroup.objects.none(), empty_label="Escolha a turma")
    plan = forms.ModelChoiceField(label="Plano", queryset=Plan.objects.none(), empty_label="Escolha o plano")
    # responsável
    guardian_name = forms.CharField(label="Nome do responsável", max_length=160, required=False)
    guardian_phone = forms.CharField(label="WhatsApp do responsável", max_length=24, required=False)
    guardian_email = forms.EmailField(label="E-mail do responsável", required=False)
    # acesso
    password = forms.CharField(
        label="Senha inicial",
        required=False,
        min_length=8,
        widget=forms.PasswordInput,
        help_text="Deixe em branco para gerar uma senha temporária automaticamente.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["class_group"].queryset = (
            ClassGroup.objects.filter(is_active=True).prefetch_related("slots").order_by("name")
        )
        self.fields["plan"].queryset = Plan.objects.filter(is_active=True).order_by("monthly_fee")
        self.fields["class_group"].label_from_instance = lambda group: (
            f"{group.name} · {group.free_spots} vaga(s)"
        )
        self.fields["plan"].label_from_instance = lambda plan: (
            f"{plan.name} · R$ {plan.monthly_fee:.2f}".replace(".", ",")
        )
        self._style()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("Já existe uma conta com este e-mail.")
        return email

    def clean(self):
        cleaned = super().clean()
        birth_date = cleaned.get("birth_date")
        if birth_date:
            today = timezone.localdate()
            age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
            if birth_date > today:
                self.add_error("birth_date", "A data de nascimento não pode estar no futuro.")
            elif age < 10:
                self.add_error("birth_date", "A escolinha atende a partir de 10 anos.")
            elif age < 18 and not (cleaned.get("guardian_name") and cleaned.get("guardian_phone")):
                self.add_error("guardian_name", "Para menores de 18 anos, informe nome e WhatsApp do responsável.")

        group = cleaned.get("class_group")
        if group and group.free_spots <= 0:
            self.add_error("class_group", "Esta turma está lotada. Aumente as vagas ou escolha outra turma.")

        password = cleaned.get("password")
        if password:
            try:
                validate_password(password, User(email=cleaned.get("email") or ""))
            except ValidationError as exc:
                self.add_error("password", exc)
        return cleaned

    def clean_password(self):
        return self.cleaned_data.get("password") or f"TF{get_random_string(8)}"

    def build_credentials(self) -> tuple[str, bool]:
        """Retorna a senha e se ela foi gerada automaticamente."""
        generated = not self.data.get("password")
        return self.cleaned_data["password"], generated

    def save(self, admin: User) -> tuple[User, Student, Enrollment, str, bool]:
        from django.db import transaction

        from dashboard.services import first_invoice_for

        data = self.cleaned_data
        password, generated = self.build_credentials()

        with transaction.atomic():
            user = User.objects.create_user(
                email=data["email"],
                password=password,
                first_name=data["first_name"],
                last_name=data.get("last_name", ""),
                phone=data["phone"],
                birth_date=data["birth_date"],
                role=User.Role.ALUNO,
            )

            guardian = None
            if data.get("guardian_name"):
                guardian = Guardian.objects.filter(
                    name__iexact=data["guardian_name"].strip(), phone=data["guardian_phone"].strip()
                ).first() or Guardian.objects.create(
                    name=data["guardian_name"].strip(),
                    phone=data.get("guardian_phone", "").strip(),
                    email=data.get("guardian_email", ""),
                )

            student = Student.objects.create(
                user=user,
                guardian=guardian,
                level=data["level"],
                status=Student.Status.ATIVO,
                position=data.get("position", ""),
                health_notes=data.get("health_notes", ""),
                joined_at=timezone.localdate(),
            )

            plan = data["plan"]
            enrollment = Enrollment.objects.create(
                student=student,
                class_group=data["class_group"],
                plan=plan,
                status=Enrollment.Status.ATIVA,
                monthly_fee=plan.monthly_fee,
                start_date=timezone.localdate(),
                approved_by=admin,
                approved_at=timezone.now(),
            )
            first_invoice_for(enrollment, user=admin)

        return user, student, enrollment, password, generated


class StudentProfileForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Student
        fields = ["nickname", "position", "health_notes"]
        widgets = {"health_notes": forms.Textarea(attrs={"rows": 3})}

    phone = forms.CharField(label="WhatsApp", max_length=24, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["phone"].initial = self.instance.user.phone
        self._style()

    def save(self, commit=True):
        student = super().save(commit=False)
        student.user.phone = self.cleaned_data["phone"]
        if commit:
            student.user.save(update_fields=["phone"])
            student.save()
        return student


class StudentEditForm(StyledFormMixin, forms.ModelForm):
    guardian_name = forms.CharField(label="Responsável", max_length=160, required=False)
    guardian_phone = forms.CharField(label="WhatsApp do responsável", max_length=24, required=False)
    guardian_email = forms.EmailField(label="E-mail do responsável", required=False)

    class Meta:
        model = Student
        fields = ["nickname", "level", "status", "position", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.guardian:
            self.fields["guardian_name"].initial = self.instance.guardian.name
            self.fields["guardian_phone"].initial = self.instance.guardian.phone
            self.fields["guardian_email"].initial = self.instance.guardian.email
        self._style()

    def save(self, commit=True):
        student = super().save(commit=False)
        name = self.cleaned_data.get("guardian_name", "").strip()
        if name:
            guardian = student.guardian
            if guardian is None:
                guardian = Guardian.objects.create(
                    name=name,
                    phone=self.cleaned_data.get("guardian_phone", ""),
                    email=self.cleaned_data.get("guardian_email", ""),
                )
            else:
                guardian.name = name
                guardian.phone = self.cleaned_data.get("guardian_phone", "") or guardian.phone
                guardian.email = self.cleaned_data.get("guardian_email", "")
                guardian.save()
            student.guardian = guardian
        if commit:
            student.save()
        return student


# ------------------------------------------------------------------ turmas
class ClassGroupForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ClassGroup
        fields = ["name", "category", "level", "professor", "venue", "capacity", "description", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["professor"].queryset = User.objects.filter(
            role__in=[User.Role.PROFESSOR, User.Role.ADMIN], is_active=True
        )
        self.fields["venue"].queryset = Venue.objects.filter(is_active=True)
        self._style()


class ScheduleSlotForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ScheduleSlot
        fields = ["weekday", "start_time", "end_time", "venue"]
        widgets = {
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["venue"].queryset = Venue.objects.filter(is_active=True)
        self._style()


ScheduleSlotFormSet = inlineformset_factory(
    ClassGroup,
    ScheduleSlot,
    form=ScheduleSlotForm,
    extra=2,
    can_delete=True,
)


# ------------------------------------------------------------------ agenda
class SessionForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Session
        fields = ["class_group", "date", "start_time", "end_time", "venue", "theme", "status", "notes"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from dashboard.services import accessible_groups

        groups = accessible_groups(user) if user else ClassGroup.objects.all()
        self.fields["class_group"].queryset = groups
        self.fields["venue"].queryset = Venue.objects.filter(is_active=True)
        self._style()


# ------------------------------------------------------------------ pontos
class PointEntryForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = PointEntry
        fields = ["student", "points", "reason", "rule", "source"]
        labels = {"rule": "Regra (opcional)", "source": "Origem"}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from dashboard.services import accessible_groups

        groups = accessible_groups(user) if user else ClassGroup.objects.all()
        self.fields["student"].queryset = Student.objects.filter(
            status=Student.Status.ATIVO, enrollments__status=Enrollment.Status.ATIVA, enrollments__class_group__in=groups
        ).distinct().select_related("user")
        self.fields["student"].empty_label = "Selecione o atleta"
        self.fields["rule"].queryset = PointRule.objects.filter(is_active=True)
        self.fields["rule"].empty_label = "Sem regra específica"
        self._style()

    def save(self, commit=True, user=None):
        entry = super().save(commit=False)
        entry.created_by = user
        if commit:
            entry.save()
        return entry


class BulkPointsForm(StyledFormMixin, forms.Form):
    class_group = forms.ModelChoiceField(label="Turma", queryset=ClassGroup.objects.all())
    points = forms.IntegerField(label="Pontos", initial=10, help_text="Use valores negativos para descontar.")
    reason = forms.CharField(label="Motivo", max_length=160, initial="Presença no treino")
    rule = forms.ModelChoiceField(label="Regra", queryset=PointRule.objects.filter(is_active=True), required=False)
    source = forms.ChoiceField(label="Origem", choices=PointEntry.Source.choices, initial=PointEntry.Source.PRESENCA)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from dashboard.services import accessible_groups

        groups = accessible_groups(user) if user else ClassGroup.objects.all()
        self.fields["class_group"].queryset = groups.filter(is_active=True)
        self.fields["rule"].empty_label = "Sem regra específica"
        self._style()


class PointRuleForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = PointRule
        fields = ["name", "points", "description", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()


# ------------------------------------------------------------------ financeiro
class GenerateInvoicesForm(StyledFormMixin, forms.Form):
    competence = forms.DateField(
        label="Competência",
        widget=forms.DateInput(attrs={"type": "month"}, format="%Y-%m"),
        input_formats=["%Y-%m"],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["competence"].initial = timezone.localdate().replace(day=1)
        self._style()


class InvoiceForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ["student", "plan", "competence", "amount", "discount", "due_date", "status", "notes"]
        widgets = {
            "competence": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "due_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = Student.objects.filter(status=Student.Status.ATIVO).select_related("user")
        self.fields["plan"].queryset = Plan.objects.filter(is_active=True)
        self._style()


# ------------------------------------------------------------------ comunicados
class AnnouncementForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Announcement
        fields = ["title", "summary", "body", "kind", "audience", "is_pinned", "is_published", "published_at"]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 8}),
            "published_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "summary": forms.TextInput(attrs={"placeholder": "Uma frase que resume o comunicado"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["published_at"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"]
        if not self.instance.pk:
            self.fields["published_at"].initial = timezone.localtime().strftime("%Y-%m-%dT%H:%M")
        self._style()


# ------------------------------------------------------------------ matrícula
class EnrollmentReviewForm(StyledFormMixin, forms.Form):
    class_group = forms.ModelChoiceField(label="Turma", queryset=ClassGroup.objects.filter(is_active=True))
    plan = forms.ModelChoiceField(label="Plano", queryset=Plan.objects.filter(is_active=True))

    def __init__(self, *args, enrollment=None, **kwargs):
        super().__init__(*args, **kwargs)
        if enrollment:
            self.fields["class_group"].initial = enrollment.class_group
            self.fields["plan"].initial = enrollment.plan
        self._style()
