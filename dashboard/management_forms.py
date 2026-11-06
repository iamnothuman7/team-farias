from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from accounts.models import Student, User
from billing.models import Plan
from school.models import ClassGroup, Enrollment, Venue
from .forms import StyledFormMixin, StudentEditForm


class EnrollmentEditForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Enrollment
        fields = ['class_group', 'plan', 'monthly_fee', 'start_date', 'status', 'notes']
        widgets = {'start_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'), 'notes': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['class_group'].queryset = ClassGroup.objects.filter(Q(is_active=True) | Q(pk=self.instance.class_group_id))
        self.fields['plan'].queryset = Plan.objects.filter(Q(is_active=True) | Q(pk=self.instance.plan_id))
        self.fields['monthly_fee'].help_text = 'Valor combinado para as próximas mensalidades. Cobranças já emitidas permanecem iguais.'
        self.fields['status'].help_text = 'Cancelar encerra as próximas cobranças automáticas; cobranças já emitidas permanecem no financeiro.'
        self._style()

    def clean_monthly_fee(self):
        value = self.cleaned_data['monthly_fee']
        if value < 0:
            raise ValidationError('Informe um valor maior ou igual a zero.')
        return value


class VenueForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Venue
        fields = ['name', 'address', 'notes', 'is_active']
        widgets = {'notes': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()


class ProfessorForm(StyledFormMixin, forms.ModelForm):
    new_password = forms.CharField(label='Nova senha', required=False, widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}), help_text='Obrigatória ao criar. Na edição, deixe em branco para manter a senha atual.')

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone', 'is_active']
        labels = {'is_active': 'Acesso ao sistema liberado'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['new_password'].required = not self.instance.pk
        self._style()

    def clean_email(self):
        value = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=value).exclude(pk=self.instance.pk).exists():
            raise ValidationError('Já existe uma conta com este e-mail.')
        return value

    def clean(self):
        data = super().clean()
        if data.get('new_password'):
            candidate = User(email=data.get('email', ''), first_name=data.get('first_name', ''), last_name=data.get('last_name', ''))
            try:
                validate_password(data['new_password'], candidate)
            except ValidationError as exc:
                self.add_error('new_password', exc)
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.PROFESSOR
        if self.cleaned_data.get('new_password'):
            user.set_password(self.cleaned_data['new_password'])
        if commit:
            user.save()
        return user


class StudentAccountForm(StudentEditForm):
    first_name = forms.CharField(label='Nome', max_length=80)
    last_name = forms.CharField(label='Sobrenome', max_length=80, required=False)
    email = forms.EmailField(label='E-mail de acesso')
    phone = forms.CharField(label='WhatsApp', max_length=24, required=False)
    birth_date = forms.DateField(label='Data de nascimento', required=False, widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    access_enabled = forms.BooleanField(label='Acesso ao sistema liberado', required=False)

    class Meta(StudentEditForm.Meta):
        fields = ['nickname', 'level', 'status', 'position', 'health_notes', 'notes']
        widgets = {'notes': forms.Textarea(attrs={'rows': 3}), 'health_notes': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('first_name', 'last_name', 'email', 'phone', 'birth_date'):
            self.fields[name].initial = getattr(self.instance.user, name)
        self.fields['access_enabled'].initial = self.instance.user.is_active
        self.fields['status'].help_text = 'A situação do aluno não cancela matrículas. Para encerrar futuras cobranças, cancele a matrícula.'
        self.order_fields(['first_name', 'last_name', 'email', 'phone', 'birth_date', 'nickname', 'level', 'status', 'position', 'health_notes', 'guardian_name', 'guardian_phone', 'guardian_email', 'notes', 'access_enabled'])

    def clean_email(self):
        value = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=value).exclude(pk=self.instance.user_id).exists():
            raise ValidationError('Já existe uma conta com este e-mail.')
        return value

    def clean_birth_date(self):
        value = self.cleaned_data.get('birth_date')
        if value and value > timezone.localdate():
            raise ValidationError('A data não pode estar no futuro.')
        return value

    def clean(self):
        data = super().clean()
        birth = data.get('birth_date')
        today = timezone.localdate()
        if birth and today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day)) < 18:
            if not data.get('guardian_name') or not data.get('guardian_phone'):
                self.add_error('guardian_name', 'Para menores, informe nome e WhatsApp do responsável.')
        return data

    def save(self, commit=True):
        student = super().save(commit=False)
        for name in ('first_name', 'last_name', 'email', 'phone', 'birth_date'):
            setattr(student.user, name, self.cleaned_data[name])
        student.user.is_active = self.cleaned_data['access_enabled']
        if not self.cleaned_data.get('guardian_name'):
            student.guardian = None
        if commit:
            student.user.save(update_fields=['first_name', 'last_name', 'email', 'phone', 'birth_date', 'is_active'])
            student.save()
        return student
