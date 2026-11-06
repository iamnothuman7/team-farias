"""Cadastro e exclusão explícita, sem apagar vínculos históricos por cascata."""
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.debug import sensitive_post_parameters

from accounts.models import Student, User
from billing.models import FinancialCategory, FinancialEntry, Invoice, Plan
from core.models import Product
from school.models import Announcement, Attendance, ClassGroup, Enrollment, PointEntry, PointRule, ScheduleSlot, Session, Venue
from .decorators import staff_required
from .forms import InvoiceForm, PointEntryForm, PointRuleForm
from .management_forms import EnrollmentEditForm, ProfessorForm, StudentAccountForm, VenueForm
from .services import first_invoice_for


# Slugs são uma lista fechada: nunca resolvemos modelos a partir de entrada livre.
RECORDS = {
    'class': (ClassGroup, 'turma', 'classes'), 'plan': (Plan, 'plano', 'plans'),
    'student': (Student, 'aluno', 'students'), 'enrollment': (Enrollment, 'matrícula', 'enrollments'),
    'session': (Session, 'treino', 'sessions'), 'point': (PointEntry, 'pontuação', 'points_admin'),
    'rule': (PointRule, 'regra de pontos', 'points_admin'), 'announcement': (Announcement, 'comunicado', 'announcements_admin'),
    'product': (Product, 'produto', 'products'), 'invoice': (Invoice, 'mensalidade', 'billing'),
    'category': (FinancialCategory, 'categoria financeira', 'finance_categories'),
    'entry': (FinancialEntry, 'lançamento', 'finance'), 'venue': (Venue, 'local', 'directory'),
    'professor': (User, 'professor', 'directory'),
}
EDIT_FORMS = {'enrollment': EnrollmentEditForm, 'point': PointEntryForm, 'rule': PointRuleForm, 'invoice': InvoiceForm, 'venue': VenueForm, 'professor': ProfessorForm, 'student': StudentAccountForm}


def _config(kind):
    if kind not in RECORDS:
        raise Http404
    return RECORDS[kind]


def _query(kind):
    model, _, _ = _config(kind)
    qs = model.objects.all()
    if kind == 'professor':
        qs = qs.filter(role=User.Role.PROFESSOR, is_staff=False, is_superuser=False)
    elif kind == 'student':
        qs = qs.filter(user__role=User.Role.ALUNO, user__is_staff=False, user__is_superuser=False)
    return qs


def _history(student):
    return student.invoices.exists() or student.attendance.exists() or student.points.exists()


def deletion_policy(kind, obj):
    """Reavaliada dentro da transação; GET jamais altera dados."""
    blocked, impacts, alternative = [], [], None
    if kind == 'class':
        if obj.enrollments.exists() or obj.sessions.filter(Q(attendance__isnull=False) | Q(points__isnull=False) | Q(status='realizado')).exists():
            blocked.append('Esta turma tem matrículas ou histórico de treinos. Esses registros precisam continuar consultáveis.')
        impacts = [f'{obj.slots.count()} horário(s) fixo(s) e {obj.sessions.count()} treino(s) sem histórico serão removidos junto com a turma.']
        alternative = ('deactivate', 'Desativar turma', 'Impede novas matrículas e a geração de treinos. Não cancela matrículas ou cobranças existentes.')
    elif kind == 'plan':
        if obj.enrollments.exists() or obj.invoices.exists():
            blocked.append('Este plano foi usado em matrículas ou cobranças. Desative-o para preservar os valores e vínculos já registrados.')
        alternative = ('deactivate', 'Desativar plano', 'Deixa de aparecer em novas matrículas; contratos existentes continuam iguais.')
    elif kind == 'student':
        if _history(obj) or obj.enrollments.exists():
            blocked.append('Este aluno tem matrícula, cobrança, presença ou pontuação registrada.')
        impacts = ['A conta de acesso também será excluída.']
        alternative = ('deactivate', 'Desativar aluno', 'Bloqueia o acesso, cancela matrículas ativas/pendentes e interrompe futuras cobranças automáticas. Cobranças existentes permanecem no financeiro.')
    elif kind == 'enrollment':
        if _history(obj.student):
            blocked.append('O aluno já tem histórico financeiro ou de treinos. A matrícula pode ser cancelada, preservando esse histórico.')
        impacts = ['O cadastro do aluno permanece. A exclusão encerra futuras cobranças desta matrícula.']
        alternative = ('cancel', 'Cancelar matrícula', 'Encerra futuras cobranças automáticas; mensalidades já emitidas não serão alteradas.')
    elif kind == 'session':
        if obj.attendance.exists() or obj.points.exists() or obj.status == 'realizado':
            blocked.append('Este treino tem presenças, pontos ou já foi realizado. Preserve seu histórico.')
        impacts = ['Se o horário fixo ainda existir, a geração automática da agenda poderá criar este treino novamente. Para impedir isso, cancele o treino.']
        alternative = ('cancel', 'Cancelar treino', 'Mantém o registro na agenda como cancelado e não apaga presenças ou pontos.')
    elif kind == 'rule':
        if obj.entries.exists():
            blocked.append('Esta regra já foi utilizada em pontuações. Desative-a para preservar a referência.')
        alternative = ('deactivate', 'Desativar regra', 'Impede novos usos sem alterar os pontos concedidos.')
    elif kind == 'invoice':
        if obj.status == 'paga' or obj.payments.exists():
            blocked.append('Esta mensalidade tem pagamento. Reabra a cobrança no Financeiro antes de editar ou excluir.')
        impacts = ['Esta cobrança será removida. Gerar mensalidades para o mesmo mês poderá criá-la novamente. Para preservar a referência, prefira cancelar.']
        if not blocked:
            alternative = ('cancel', 'Cancelar mensalidade', 'Preserva a cobrança como cancelada e impede sua geração repetida no mesmo mês.')
    elif kind == 'category':
        if obj.entries.exists():
            blocked.append('Há lançamentos vinculados a esta categoria. Desative-a para preservar o histórico.')
        alternative = ('deactivate', 'Desativar categoria', 'Não será oferecida para novos lançamentos.')
    elif kind == 'entry':
        if obj.status == 'settled':
            blocked.append('Reabra o lançamento antes de excluir. Isso estorna sua baixa no saldo de caixa.')
        if obj.is_archived:
            blocked.append('Este lançamento já está na lixeira. Você pode restaurá-lo na tela de detalhes.')
        impacts = ['O lançamento será movido para a lixeira, sem apagar o histórico de alterações. Pode ser restaurado pelo filtro Excluídos no Caixa.']
    elif kind == 'venue':
        if obj.groups.exists() or ScheduleSlot.objects.filter(venue=obj).exists() or Session.objects.filter(venue=obj).exists():
            blocked.append('Este local está vinculado a turmas ou treinos. Desative-o para preservar a referência.')
        alternative = ('deactivate', 'Desativar local', 'Não será oferecido para novos cadastros.')
    elif kind == 'professor':
        # Qualquer referência existente deve conservar o nome do responsável.
        if any(relation.related_model.objects.filter(**{relation.field.name: obj}).exists() for relation in User._meta.related_objects if not relation.many_to_many):
            blocked.append('Este professor tem registros vinculados. Desative o acesso para preservar a autoria e os vínculos.')
        alternative = ('deactivate', 'Desativar acesso', 'Bloqueia o login; as turmas e o histórico permanecem registrados.')
    elif kind == 'announcement':
        impacts = ['O comunicado e suas notificações ainda pendentes serão removidos. Notificações já entregues aos celulares não podem ser recolhidas.']
    elif kind == 'point':
        impacts = [f'Os {obj.points} ponto(s) deste registro deixarão de compor o ranking do aluno.']
    elif kind == 'product':
        impacts = ['O produto sairá do catálogo. Conversas e pedidos já enviados pelo WhatsApp permanecem no WhatsApp.']
    return blocked, impacts, alternative


def _sync_student(student):
    student.status = Student.Status.ATIVO if student.enrollments.filter(status='ativa').exists() else Student.Status.INATIVO
    student.save(update_fields=['status', 'updated_at'])


def _alternative(kind, obj, action):
    if action == 'deactivate':
        if kind == 'student':
            obj.user.is_active = False
            obj.user.save(update_fields=['is_active'])
            obj.enrollments.filter(status__in=['ativa', 'pendente']).update(status='cancelada')
            _sync_student(obj)
        else:
            obj.is_active = False
            obj.save(update_fields=['is_active'])
    elif action == 'cancel':
        obj.status = 'cancelado' if kind == 'session' else 'cancelada'
        obj.save(update_fields=['status'])
        if kind == 'enrollment':
            _sync_student(obj.student)


@staff_required
@require_http_methods(['GET', 'POST'])
def record_delete(request, kind, pk):
    _, label, list_route = _config(kind)
    obj = get_object_or_404(_query(kind), pk=pk)
    back_url = reverse('dashboard:' + list_route)
    error = None
    if request.method == 'POST':
        try:
            with transaction.atomic():
                obj = get_object_or_404(_query(kind).select_for_update(), pk=pk)
                if kind == 'enrollment':
                    Student.objects.select_for_update().get(pk=obj.student_id)
                blocked, impacts, alternative = deletion_policy(kind, obj)
                action = request.POST.get('action')
                if action == 'delete' and not blocked:
                    if kind == 'entry':
                        from billing.finance import transition_financial_entry
                        transition_financial_entry(pk, 'archived', user=request.user)
                    elif kind == 'student':
                        obj.user.delete()
                    else:
                        student = obj.student if kind == 'enrollment' else None
                        obj.delete()
                        if student:
                            _sync_student(student)
                elif alternative and action == alternative[0]:
                    _alternative(kind, obj, action)
                else:
                    raise ValidationError(blocked or ['Ação inválida. Confira as opções disponíveis.'])
        except (ValidationError, IntegrityError) as exc:
            error = ' '.join(exc.messages) if isinstance(exc, ValidationError) else 'O registro ganhou novos vínculos. Atualize a página e confira as opções disponíveis.'
        else:
            messages.success(request, 'Registro excluído.' if action == 'delete' else 'Registro atualizado. O histórico foi preservado.')
            return redirect(back_url)
    blocked, impacts, alternative = deletion_policy(kind, obj)
    return render(request, 'painel/record_delete.html', {'record': obj, 'kind': kind, 'label': label, 'back_url': back_url, 'blocked': blocked, 'impacts': impacts, 'alternative': alternative, 'error': error})


def _save_enrollment(form, user):
    enrollment = form.save(commit=False)
    student = Student.objects.select_for_update().get(pk=enrollment.student_id)
    group = ClassGroup.objects.select_for_update().get(pk=enrollment.class_group_id)
    plan = Plan.objects.select_for_update().get(pk=enrollment.plan_id)
    previous = Enrollment.objects.get(pk=enrollment.pk)
    if enrollment.status == 'ativa':
        occupied = group.enrollments.filter(status='ativa').exclude(pk=enrollment.pk).count()
        if occupied >= group.capacity:
            raise ValidationError('Esta turma está lotada. Escolha outra turma ou aumente as vagas.')
        if (not group.is_active and (previous.class_group_id != group.pk or previous.status != 'ativa')) or (not plan.is_active and (previous.plan_id != plan.pk or previous.status != 'ativa')):
            raise ValidationError('Para ativar ou transferir a matrícula, selecione turma e plano ativos.')
        if student.enrollments.filter(status='ativa').exclude(pk=enrollment.pk).exists():
            raise ValidationError('O aluno já tem outra matrícula ativa.')
        if previous.status != 'ativa':
            enrollment.approved_by = user
            enrollment.approved_at = timezone.now()
            enrollment.start_date = enrollment.start_date or timezone.localdate()
    enrollment.save()
    _sync_student(student)
    if enrollment.status == 'ativa' and previous.status != 'ativa':
        first_invoice_for(enrollment, user=user)
    return enrollment


@staff_required
@sensitive_post_parameters('new_password')
@require_http_methods(['GET', 'POST'])
def record_edit(request, kind, pk=None):
    if kind not in EDIT_FORMS or (pk is None and kind not in ('venue', 'professor', 'rule')):
        raise Http404
    _, label, list_route = _config(kind)
    obj = get_object_or_404(_query(kind), pk=pk) if pk else None
    back_url = reverse('dashboard:' + list_route)
    if kind == 'invoice' and (obj.status != 'aberta' or obj.payments.exists()):
        messages.warning(request, 'Reabra a mensalidade antes de editar.')
        return redirect(back_url)
    kwargs = {'user': request.user} if kind == 'point' else {}
    form = EDIT_FORMS[kind](instance=obj, **kwargs)
    if request.method == 'POST':
        try:
            with transaction.atomic():
                if pk:
                    obj = get_object_or_404(_query(kind).select_for_update(), pk=pk)
                form = EDIT_FORMS[kind](request.POST, instance=obj, **kwargs)
                if form.is_valid():
                    if kind == 'enrollment':
                        _save_enrollment(form, request.user)
                    elif kind == 'invoice' and (obj.status != 'aberta' or obj.payments.exists()):
                        raise ValidationError('A mensalidade mudou. Reabra antes de editar.')
                    elif kind == 'point':
                        form.save(user=obj.created_by)
                    else:
                        form.save()
                    messages.success(request, 'Cadastro atualizado.' if pk else 'Cadastro criado.')
                    return redirect(back_url)
        except (ValidationError, IntegrityError) as exc:
            form.add_error(None, exc.messages if isinstance(exc, ValidationError) else 'Já existe um cadastro com esses dados ou o registro mudou. Confira os campos.')
    return render(request, 'painel/record_form.html', {'form': form, 'record': obj, 'kind': kind, 'label': label, 'back_url': back_url})


@staff_required
@require_http_methods(['GET'])
def directory(request):
    return render(request, 'painel/directory.html', {'venues': Venue.objects.all(), 'professors': _query('professor')})
