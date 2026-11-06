from datetime import time
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Student, User
from billing.finance import finance_movements, finance_summary, save_financial_entry, transition_financial_entry
from billing.models import FinancialCategory, FinancialEntry, FinancialEvent, Invoice, Plan
from core.models import Product
from core.testing import make_admin, make_group, make_invoice, make_plan, make_professor, make_session, make_student
from school.models import Announcement, Attendance, ClassGroup, Enrollment, PointEntry, PointRule, Session, Venue
from .management_views import RECORDS


class ManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = make_admin()
        cls.professor = make_professor()
        cls.plan = make_plan()
        cls.group = make_group(professor=cls.professor)
        cls.student = make_student(group=cls.group, plan=cls.plan)
        cls.enrollment = cls.student.enrollments.get()
        cls.session = make_session(cls.group)
        cls.rule = PointRule.objects.create(name='Dedicação', points=5)
        cls.point = PointEntry.objects.create(student=cls.student, points=5, reason='Bom treino', rule=cls.rule, created_by=cls.professor)
        cls.invoice = make_invoice(cls.student)
        cls.category = FinancialCategory.objects.create(name='QA despesas', kind='expense')
        cls.entry = save_financial_entry(FinancialEntry(kind='expense', category=cls.category, description='Material', amount=20, due_date=timezone.localdate()), user=cls.admin)
        cls.product = Product.objects.create(name='Camisa de treino')
        cls.announcement = Announcement.objects.create(title='Rascunho', body='Orientação', is_published=False)
        cls.records = {'class': cls.group, 'plan': cls.plan, 'student': cls.student, 'enrollment': cls.enrollment, 'session': cls.session, 'point': cls.point, 'rule': cls.rule, 'invoice': cls.invoice, 'category': cls.category, 'entry': cls.entry, 'product': cls.product, 'announcement': cls.announcement, 'venue': cls.group.venue, 'professor': cls.professor}

    def setUp(self):
        self.client.force_login(self.admin)

    def url(self, kind, obj, action='delete'):
        return reverse('dashboard:record_' + action, args=[kind, obj.pk])

    def test_all_delete_previews_are_read_only_and_render(self):
        for kind, obj in self.records.items():
            with self.subTest(kind=kind):
                response = self.client.get(self.url(kind, obj))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Voltar sem alterar')
                self.assertTrue(type(obj).objects.filter(pk=obj.pk).exists())

    def test_edit_screens_and_directory_render(self):
        for kind in ('enrollment', 'student', 'point', 'rule', 'invoice', 'professor', 'venue'):
            with self.subTest(kind=kind):
                self.assertEqual(self.client.get(self.url(kind, self.records[kind], 'edit')).status_code, 200)
        self.assertContains(self.client.get(reverse('dashboard:directory')), 'Locais de treino')
        for kind in ('venue', 'professor', 'rule'):
            self.assertEqual(self.client.get(reverse('dashboard:record_create', args=[kind])).status_code, 200)

    def test_crud_requires_admin_for_every_entity(self):
        for user in (self.professor, self.student.user):
            self.client.force_login(user)
            for kind, obj in self.records.items():
                with self.subTest(user=user.role, kind=kind):
                    self.assertEqual(self.client.post(self.url(kind, obj), {'action': 'delete'}).status_code, 403)
                    self.assertEqual(self.client.get(self.url(kind, obj)).status_code, 403)
            self.assertEqual(self.client.post(reverse('dashboard:record_create', args=['professor']), {}).status_code, 403)

    def test_csrf_and_http_method_protection(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post(self.url('point', self.point), {'action': 'delete'}).status_code, 403)
        self.assertEqual(self.client.put(self.url('point', self.point)).status_code, 405)
        self.assertEqual(self.client.get(reverse('dashboard:record_delete', args=['user', self.admin.pk])).status_code, 404)
        self.assertEqual(self.client.get(self.url('professor', self.admin, 'edit')).status_code, 404)
        promoted_student = Student.objects.create(user=self.admin)
        self.assertEqual(self.client.post(self.url('student', promoted_student), {'action': 'deactivate'}).status_code, 404)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_empty_class_deletes_slots_and_unrecorded_sessions(self):
        group = make_group(name='Descartável')
        session = make_session(group)
        self.assertEqual(self.client.post(self.url('class', group), {'action': 'delete'}).status_code, 302)
        self.assertFalse(ClassGroup.objects.filter(pk=group.pk).exists())
        self.assertFalse(Session.objects.filter(pk=session.pk).exists())

    def test_class_with_enrollment_is_protected_but_can_deactivate(self):
        response = self.client.post(self.url('class', self.group), {'action': 'delete'})
        self.assertContains(response, 'matrículas ou histórico')
        self.assertEqual(self.client.post(self.url('class', self.group), {'action': 'deactivate'}).status_code, 302)
        self.group.refresh_from_db()
        self.assertFalse(self.group.is_active)
        self.assertTrue(self.student.enrollments.filter(status='ativa').exists())

    def test_unused_plan_deletes_and_used_plan_is_protected(self):
        plan = make_plan(name='Sem uso')
        self.assertEqual(self.client.post(self.url('plan', plan), {'action': 'delete'}).status_code, 302)
        self.assertFalse(Plan.objects.filter(pk=plan.pk).exists())
        self.assertEqual(self.client.post(self.url('plan', self.plan), {'action': 'delete'}).status_code, 200)
        self.assertTrue(Plan.objects.filter(pk=self.plan.pk).exists())

    def test_unlinked_student_deletes_account(self):
        student = make_student(email='empty@example.invalid')
        user_id = student.user_id
        self.assertEqual(self.client.post(self.url('student', student), {'action': 'delete'}).status_code, 302)
        self.assertFalse(User.objects.filter(pk=user_id).exists())

    def test_student_deactivation_preserves_money_and_stops_enrollment(self):
        self.client.post(self.url('student', self.student), {'action': 'deactivate'})
        self.student.refresh_from_db()
        self.student.user.refresh_from_db()
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, 'cancelada')
        self.assertFalse(self.student.user.is_active)
        self.assertEqual(self.student.status, 'inativo')
        self.assertTrue(Invoice.objects.filter(pk=self.invoice.pk).exists())

    def enrollment_payload(self, **changes):
        result = {'class_group': self.group.pk, 'plan': self.plan.pk, 'monthly_fee': '200.00', 'start_date': timezone.localdate().isoformat(), 'status': 'ativa', 'notes': 'Condição combinada'}
        result.update(changes)
        return result

    def test_enrollment_edit_does_not_reprice_existing_invoice(self):
        response = self.client.post(self.url('enrollment', self.enrollment, 'edit'), self.enrollment_payload())
        self.assertEqual(response.status_code, 302)
        self.enrollment.refresh_from_db()
        self.invoice.refresh_from_db()
        self.assertEqual(self.enrollment.monthly_fee, Decimal('200.00'))
        self.assertEqual(self.invoice.amount, Decimal('180.00'))

    def test_enrollment_transfer_refuses_full_group(self):
        other = make_group(name='Lotada', capacity=1)
        make_student(email='full@example.invalid', group=other, plan=self.plan)
        response = self.client.post(self.url('enrollment', self.enrollment, 'edit'), self.enrollment_payload(class_group=other.pk))
        self.assertContains(response, 'lotada')
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.class_group_id, self.group.pk)

    def test_cancel_and_reactivate_enrollment_without_duplicate_invoice(self):
        self.client.post(self.url('enrollment', self.enrollment), {'action': 'cancel'})
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, 'inativo')
        response = self.client.post(self.url('enrollment', self.enrollment, 'edit'), self.enrollment_payload())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.student.invoices.count(), 1)
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, 'ativo')

    def test_enrollment_refuses_negative_fee(self):
        response = self.client.post(self.url('enrollment', self.enrollment, 'edit'), self.enrollment_payload(monthly_fee='-1'))
        self.assertContains(response, 'maior ou igual a zero')

    def test_point_edit_and_delete_update_ranking(self):
        response = self.client.post(self.url('point', self.point, 'edit'), {'student': self.student.pk, 'points': '8', 'reason': 'Ajuste', 'source': 'ajuste', 'rule': self.rule.pk})
        self.assertEqual(response.status_code, 302)
        self.point.refresh_from_db()
        self.assertEqual(self.point.created_by_id, self.professor.pk)
        self.assertEqual(self.student.total_points, 8)
        self.client.post(self.url('point', self.point), {'action': 'delete'})
        self.assertEqual(self.student.total_points, 0)

    def test_used_rule_is_protected_and_can_be_deactivated(self):
        self.assertEqual(self.client.post(self.url('rule', self.rule), {'action': 'delete'}).status_code, 200)
        self.client.post(self.url('rule', self.rule), {'action': 'deactivate'})
        self.rule.refresh_from_db()
        self.assertFalse(self.rule.is_active)
        self.assertEqual(self.student.total_points, 5)

    def test_recorded_session_cannot_delete(self):
        Attendance.objects.create(session=self.session, student=self.student, status='presente')
        self.assertEqual(self.client.post(self.url('session', self.session), {'action': 'delete'}).status_code, 200)
        self.client.post(self.url('session', self.session), {'action': 'cancel'})
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, 'cancelado')
        self.assertEqual(self.session.attendance.count(), 1)

    def test_invoice_edit_delete_and_paid_protection(self):
        data = {'student': self.student.pk, 'plan': self.plan.pk, 'competence': self.invoice.competence.isoformat(), 'amount': '210', 'discount': '10', 'due_date': self.invoice.due_date.isoformat(), 'notes': 'Correção'}
        self.assertEqual(self.client.post(self.url('invoice', self.invoice, 'edit'), data).status_code, 302)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.total, 200)
        self.invoice.mark_paid(user=self.admin, method='pix')
        self.assertEqual(self.client.post(self.url('invoice', self.invoice), {'action': 'delete'}).status_code, 200)
        self.assertEqual(self.invoice.payments.count(), 1)
        self.invoice.reopen()
        self.assertEqual(self.client.post(self.url('invoice', self.invoice), {'action': 'delete'}).status_code, 302)
        self.assertFalse(Invoice.objects.filter(pk=self.invoice.pk).exists())

    def test_cancel_invoice_preserves_reference(self):
        self.client.post(self.url('invoice', self.invoice), {'action': 'cancel'})
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, 'cancelada')

    def test_archive_restore_cash_preserves_audit_and_totals(self):
        today = timezone.localdate()
        self.client.post(self.url('entry', self.entry), {'action': 'delete'})
        self.entry.refresh_from_db()
        self.assertTrue(self.entry.is_archived)
        self.assertEqual(finance_summary(today, today)['pending_expenses'], 0)
        self.assertFalse(any(row['source'] == 'entry' for row in finance_movements(today, today)))
        self.assertEqual(finance_movements(today, today, status='archived')[0]['status_label'], 'Excluído')
        response = self.client.get(reverse('dashboard:finance_detail', args=[self.entry.pk]))
        self.assertContains(response, 'Restaurar lançamento')
        self.client.post(reverse('dashboard:finance_detail', args=[self.entry.pk]), {'action': 'restore'})
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, 'pending')
        self.assertFalse(self.entry.is_archived)
        self.assertEqual(self.entry.events.count(), 3)

    def test_paid_cash_cannot_archive_and_archived_cannot_reopen(self):
        self.entry.settle(user=self.admin, method='pix')
        self.assertEqual(self.client.post(self.url('entry', self.entry), {'action': 'delete'}).status_code, 200)
        self.entry.reopen(user=self.admin)
        transition_financial_entry(self.entry.pk, 'archived', user=self.admin)
        response = self.client.post(reverse('dashboard:finance_detail', args=[self.entry.pk]), {'action': 'reopen'})
        self.entry.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.entry.is_archived)

    def test_category_and_venue_used_are_protected(self):
        for kind in ('category', 'venue'):
            self.assertEqual(self.client.post(self.url(kind, self.records[kind]), {'action': 'delete'}).status_code, 200)
            self.client.post(self.url(kind, self.records[kind]), {'action': 'deactivate'})
            self.records[kind].refresh_from_db()
            self.assertFalse(self.records[kind].is_active)

    def test_product_and_draft_announcement_delete(self):
        for kind in ('product', 'announcement'):
            obj = self.records[kind]
            self.assertEqual(self.client.post(self.url(kind, obj), {'action': 'delete'}).status_code, 302)
            self.assertFalse(type(obj).objects.filter(pk=obj.pk).exists())

    def test_professor_create_edit_delete_and_no_privilege_escalation(self):
        data = {'first_name': 'Teste', 'last_name': 'Equipe', 'email': 'new-prof@example.invalid', 'phone': '', 'is_active': 'on', 'new_password': 'RandomExample!243991', 'is_superuser': 'on', 'role': 'admin'}
        response = self.client.post(reverse('dashboard:record_create', args=['professor']), data)
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email=data['email'])
        self.assertFalse(user.is_admin_role)
        self.assertTrue(user.check_password(data['new_password']))
        data.update(first_name='Atualizado', new_password='')
        self.assertEqual(self.client.post(self.url('professor', user, 'edit'), data).status_code, 302)
        self.client.post(self.url('professor', user), {'action': 'delete'})
        self.assertFalse(User.objects.filter(pk=user.pk).exists())

    def test_professor_used_can_only_deactivate(self):
        self.assertEqual(self.client.post(self.url('professor', self.professor), {'action': 'delete'}).status_code, 200)
        self.assertEqual(self.client.post(self.url('professor', self.professor), {'action': 'deactivate'}).status_code, 302)
        self.professor.refresh_from_db()
        self.assertFalse(self.professor.is_active)
        self.group.refresh_from_db()
        self.assertEqual(self.group.professor_id, self.professor.pk)

    def test_student_account_edit_and_duplicate_email_validation(self):
        data = {'first_name': 'Nome atualizado', 'last_name': 'Aluno', 'email': 'updated@example.invalid', 'phone': '88990000000', 'level': 'iniciante', 'status': 'ativo', 'access_enabled': 'on'}
        self.assertEqual(self.client.post(self.url('student', self.student, 'edit'), data).status_code, 302)
        self.student.user.refresh_from_db()
        self.assertEqual(self.student.user.email, data['email'])
        data['email'] = self.admin.email.upper()
        self.assertContains(self.client.post(self.url('student', self.student, 'edit'), data), 'Já existe uma conta')

    def test_class_schedule_validation_keeps_changes_atomic(self):
        slot = self.group.slots.get()
        data = {'name': 'Novo nome', 'category': 'livre', 'level': 'iniciante', 'capacity': '16', 'is_active': 'on', 'slots-TOTAL_FORMS': '1', 'slots-INITIAL_FORMS': '1', 'slots-0-id': slot.pk, 'slots-0-weekday': '1', 'slots-0-start_time': '10:00', 'slots-0-end_time': '09:00'}
        response = self.client.post(reverse('dashboard:class_edit', args=[self.group.pk]), data)
        self.assertContains(response, 'O fim deve ser depois do início.')
        self.group.refresh_from_db()
        self.assertNotEqual(self.group.name, 'Novo nome')
        data['slots-0-end_time'] = '11:00'
        self.assertEqual(self.client.post(reverse('dashboard:class_edit', args=[self.group.pk]), data).status_code, 302)
        slot.refresh_from_db()
        self.assertEqual(slot.start_time, time(10))

    def test_schedule_overlap_and_capacity_validation(self):
        slot = self.group.slots.get()
        data = {'name': self.group.name, 'category': 'livre', 'level': 'iniciante', 'capacity': '16', 'is_active': 'on', 'slots-TOTAL_FORMS': '2', 'slots-INITIAL_FORMS': '1', 'slots-0-id': slot.pk, 'slots-0-weekday': '1', 'slots-0-start_time': '07:00', 'slots-0-end_time': '08:00', 'slots-1-weekday': '1', 'slots-1-start_time': '07:30', 'slots-1-end_time': '09:00'}
        self.assertContains(self.client.post(reverse('dashboard:class_edit', args=[self.group.pk]), data), 'horários sobrepostos')
        data['slots-1-DELETE'] = 'on'
        data['capacity'] = '0'
        self.assertContains(self.client.post(reverse('dashboard:class_edit', args=[self.group.pk]), data), 'pelo menos uma vaga')

    def test_login_uses_transparent_brand_and_cadastros_assets(self):
        self.client.logout()
        response = self.client.get('/entrar/')
        self.assertContains(response, 'img/logo.webp')
        self.assertContains(response, 'css/management.css')
        self.assertContains(response, 'js/management.js')

    def test_class_add_remove_and_blank_schedule(self):
        slot = self.group.slots.get()
        data = {'name': self.group.name, 'category': 'livre', 'level': 'iniciante', 'capacity': '16', 'is_active': 'on', 'slots-TOTAL_FORMS': '3', 'slots-INITIAL_FORMS': '1', 'slots-0-id': slot.pk, 'slots-0-weekday': '1', 'slots-0-start_time': '07:00', 'slots-0-end_time': '08:00', 'slots-0-DELETE': 'on', 'slots-1-weekday': '3', 'slots-1-start_time': '17:00', 'slots-1-end_time': '18:00'}
        self.assertEqual(self.client.post(reverse('dashboard:class_edit', args=[self.group.pk]), data).status_code, 302)
        self.assertEqual(self.group.slots.count(), 1)
        self.assertEqual(self.group.slots.get().weekday, 3)
        self.assertFalse(self.group.slots.filter(pk=slot.pk).exists())

    def test_session_edit_preserves_inactive_venue_and_iso_date(self):
        self.group.venue.is_active = False
        self.group.venue.save()
        response = self.client.get(reverse('dashboard:session_edit', args=[self.session.pk]))
        self.assertContains(response, f'value="{self.session.date.isoformat()}"')
        self.assertContains(response, 'value="07:00"')
        data = {'class_group': self.group.pk, 'date': self.session.date.isoformat(), 'start_time': '08:00', 'end_time': '09:00', 'venue': self.group.venue_id, 'theme': 'Atualizado', 'status': 'agendado'}
        self.assertEqual(self.client.post(reverse('dashboard:session_edit', args=[self.session.pk]), data).status_code, 302)

    def test_history_remains_editable_after_student_plan_and_rule_deactivation(self):
        self.invoice.plan = self.plan
        self.invoice.save(update_fields=['plan'])
        self.student.status = 'inativo'
        self.student.save()
        self.plan.is_active = False
        self.plan.save()
        self.rule.is_active = False
        self.rule.save()
        response = self.client.post(self.url('point', self.point, 'edit'), {'student': self.student.pk, 'points': '7', 'reason': 'Correção', 'source': 'ajuste', 'rule': self.rule.pk})
        self.assertEqual(response.status_code, 302)
        response = self.client.post(self.url('invoice', self.invoice, 'edit'), {'student': self.student.pk, 'plan': self.plan.pk, 'competence': self.invoice.competence.isoformat(), 'amount': '180', 'discount': '0', 'due_date': self.invoice.due_date.isoformat()})
        self.assertEqual(response.status_code, 302)

    def test_rule_creation_is_admin_only(self):
        self.client.force_login(self.professor)
        response = self.client.post(reverse('dashboard:points_admin'), {'action': 'rule', 'name': 'Não autorizada', 'points': 5, 'is_active': 'on'})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(PointRule.objects.filter(name='Não autorizada').exists())
