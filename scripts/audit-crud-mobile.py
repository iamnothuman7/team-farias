"""CRUD e formulários em navegadores isolados, somente com dados locais sintéticos."""
import json
import os
import secrets
import sys
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / '.local/testdeps')]
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'teamfarias.settings')
import django
django.setup()
from django.conf import settings
from django.utils import timezone
from accounts.models import User
from billing.finance import save_financial_entry
from billing.models import FinancialCategory, FinancialEntry, FinancialEvent, Plan
from core.models import Product
from core.testing import make_admin, make_group, make_invoice, make_plan, make_professor, make_session, make_student
from school.models import Announcement, ClassGroup, PointEntry, PointRule, Venue
from playwright.sync_api import sync_playwright, expect

assert settings.DEBUG and settings.DATABASES['default']['HOST'] in ('localhost', '127.0.0.1')
expect.set_options(timeout=30000)
BASE = 'http://127.0.0.1:8017'
OUT = ROOT / '.local/crud-mobile'
OUT.mkdir(parents=True, exist_ok=True)
tag = 'qa-crud-' + secrets.token_hex(4)
password = secrets.token_urlsafe(24)
admin = make_admin(email=tag + '-admin@example.invalid', password=password)
professor = make_professor(email=tag + '-prof@example.invalid')
venue = Venue.objects.create(name=tag + ' ArenaDeTreinamentoVoleiDePraiaComNomeMuitoLongo', address='Rua com endereço extenso para verificar alinhamento e quebra de linha')
plan = make_plan(name=tag + ' PlanoDeTreinamentoCompletoComAcompanhamentoIndividual')
group = make_group(name=tag + ' TurmaDeVoleiDePraiaBasicoIntermediarioParaTestes', professor=professor)
group.venue = venue
group.description = 'Descrição para conferir campos com várias linhas, legibilidade e alinhamento no celular. ' * 4
group.save()
group.slots.update(venue=venue)
student = make_student(email=tag + '-student@example.invalid', group=group, plan=plan)
student.nickname = 'MariaEduardaAlbuquerqueFariasSilvaSantos'
student.save()
enrollment = student.enrollments.get()
session = make_session(group)
invoice = make_invoice(student)
rule = PointRule.objects.create(name=tag + ' RegraDePontuacaoPorDedicaçãoAoTreinamento', points=5)
point = PointEntry.objects.create(student=student, points=5, reason='Dedicação ao treino', rule=rule)
category = FinancialCategory.objects.create(name=tag + ' DespesasDaEscolinha', kind='expense')
entry = save_financial_entry(FinancialEntry(kind='expense', category=category, description=tag + ' MateriaisEsportivosParaTreinamentoDaEscolinha', amount=Decimal('80.00'), due_date=timezone.localdate()), user=admin)
product = Product.objects.create(name=tag + ' CamisaDeTreinamentoDaEscolinhaTeamFarias')
announcement = Announcement.objects.create(title=tag + ' Orientações de treino', body='Rascunho de teste.', is_published=False)
report = {'layouts': [], 'flows': [], 'errors': []}


def db(fn):
    def run():
        from django.db import connections
        try:
            return fn()
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(run).result()


def inspect(page, state, engine, width):
    expect(page.locator('.htmx-request,.htmx-swapping,.htmx-settling,html.is-loading')).to_have_count(0)
    if width > 1024 and page.locator('.app-sidebar').count():
        page.mouse.move(width - 16, 100)
        expect(page.locator('.app-sidebar')).to_have_css('width', '84px')
    failures = page.locator('main').evaluate('''root => [...root.querySelectorAll('h1,h2,h3,p,strong,span,label,input,select,textarea,button,legend,.card,.field,.form-errors')].filter(el => {
      const b=el.getBoundingClientRect(),s=getComputedStyle(el);
      if(!b.width||!b.height||el.closest('svg')||s.visibility==='hidden')return false;
      return b.left < -1 || b.right > innerWidth+1 || (!el.matches('input,textarea,select')&&s.overflowX==='visible'&&el.scrollWidth>el.clientWidth+2);
    }).map(el=>({tag:el.tagName,cls:el.className,text:el.textContent.trim().slice(0,65)}))''')
    assert not failures, (state, engine, width, failures)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    report['layouts'].append({'state': state, 'engine': engine, 'width': width})
    if width in (390, 1366) and state in ('login', 'turma-editar', 'matricula-editar', 'excluir-turma', 'caixa-lixeira', 'turma-erros'):
        page.screenshot(path=str(OUT / f'{engine}-{width}-{state}.png'), full_page=True)


def goto(page, path):
    response = page.goto(BASE + path, wait_until='networkidle')
    assert response.status == 200, (path, response.status)


def record(kind, pk, action='editar'):
    return f'/painel/cadastros/{kind}/{pk}/{action}/'


try:
    with sync_playwright() as p:
        for engine in ('chromium', 'webkit'):
            if os.getenv('CRUD_ENGINE') and engine != os.environ['CRUD_ENGINE']:
                continue
            for width, height in ((320, 740), (390, 844), (844, 390), (1366, 768)):
                if os.getenv('CRUD_WIDTH') and width != int(os.environ['CRUD_WIDTH']):
                    continue
                browser = p.chromium.launch(channel='msedge', headless=True, args=['--disable-gpu', '--renderer-process-limit=1']) if engine == 'chromium' else p.webkit.launch(headless=True)
                context = browser.new_context(viewport={'width': width, 'height': height}, service_workers='block')
                if width < 1000:
                    context.add_init_script("Object.defineProperty(navigator,'standalone',{get:()=>true});document.addEventListener('DOMContentLoaded',()=>{document.documentElement.style.setProperty('--safe-top','47px');document.documentElement.style.setProperty('--safe-bottom','34px')});")
                page = context.new_page()
                page.set_default_timeout(30000)
                page.set_default_navigation_timeout(60000)
                page.on('pageerror', lambda e: report['errors'].append(str(e)))
                goto(page, '/entrar/')
                inspect(page, 'login', engine, width)
                assert page.locator('.login-intro img').get_attribute('src').endswith('logo.webp')
                page.get_by_label('E-mail', exact=True).fill(admin.email)
                page.get_by_label('Senha', exact=True).fill(password)
                page.get_by_role('button', name='Entrar na minha conta').click()
                expect(page).to_have_url(BASE + '/painel/')
                paths = [
                    ('turmas', '/painel/turmas/'), ('turma-editar', f'/painel/turmas/{group.pk}/editar/'),
                    ('plano-editar', f'/painel/planos/{plan.pk}/editar/'),
                    ('matricula-editar', record('enrollment', enrollment.pk)), ('aluno-editar', record('student', student.pk)),
                    ('treino-editar', f'/painel/agenda/{session.pk}/editar/'), ('pontos', '/painel/pontos/'),
                    ('ponto-editar', record('point', point.pk)), ('regra-editar', record('rule', rule.pk)),
                    ('mensalidade-editar', record('invoice', invoice.pk)),
                    ('comunicado-editar', f'/painel/comunicados/{announcement.pk}/editar/'),
                    ('produto-editar', f'/painel/produtos/{product.pk}/editar/'),
                    ('locais-equipe', '/painel/cadastros/'), ('local-editar', record('venue', venue.pk)),
                    ('professor-editar', record('professor', professor.pk)),
                    ('excluir-turma', record('class', group.pk, 'excluir')),
                    ('excluir-plano', record('plan', plan.pk, 'excluir')),
                    ('excluir-aluno', record('student', student.pk, 'excluir')),
                    ('excluir-mensalidade', record('invoice', invoice.pk, 'excluir')),
                    ('excluir-lancamento', record('entry', entry.pk, 'excluir')),
                ]
                for state, path in paths:
                    goto(page, path)
                    inspect(page, state, engine, width)
                goto(page, f'/painel/turmas/{group.pk}/editar/')
                page.locator('[name="slots-0-end_time"]').fill('06:00')
                page.get_by_role('button', name='Salvar turma').click()
                expect(page.get_by_text('O fim deve ser depois do início.', exact=True)).to_be_visible()
                inspect(page, 'turma-erros', engine, width)
                if width == 390:
                    # Cria, lê, corrige, edita horários e exclui uma turma descartável pela UI.
                    goto(page, '/painel/turmas/nova/')
                    page.locator('[name="name"]').fill(tag + '-' + engine + ' TurmaDescartavel')
                    page.locator('[name="slots-0-weekday"]').select_option('1')
                    page.locator('[name="slots-0-start_time"]').fill('07:00')
                    page.locator('[name="slots-0-end_time"]').fill('08:00')
                    page.get_by_role('button', name='Adicionar horário').click()
                    page.locator('[name="slots-1-weekday"]').select_option('3')
                    page.locator('[name="slots-1-start_time"]').fill('17:00')
                    page.locator('[name="slots-1-end_time"]').fill('18:00')
                    inspect(page, 'turma-adicionar-horario', engine, width)
                    page.get_by_role('button', name='Salvar turma').click()
                    expect(page).to_have_url(BASE + '/painel/turmas/')
                    created_id = db(lambda: ClassGroup.objects.get(name=tag + '-' + engine + ' TurmaDescartavel').pk)
                    assert db(lambda: ClassGroup.objects.get(pk=created_id).slots.count()) == 2
                    goto(page, f'/painel/turmas/{created_id}/editar/')
                    page.locator('[name="slots-0-DELETE"]').check()
                    page.get_by_role('button', name='Salvar turma').click()
                    expect(page).to_have_url(BASE + '/painel/turmas/')
                    assert db(lambda: ClassGroup.objects.get(pk=created_id).slots.count()) == 1
                    goto(page, record('class', created_id, 'excluir'))
                    page.get_by_role('button', name='Confirmar exclusão', exact=True).click()
                    expect(page).to_have_url(BASE + '/painel/turmas/')
                    assert not db(lambda: ClassGroup.objects.filter(pk=created_id).exists())
                    goto(page, record('entry', entry.pk, 'excluir'))
                    page.get_by_role('button', name='Confirmar exclusão', exact=True).click()
                    expect(page).to_have_url(BASE + '/painel/caixa/')
                    assert db(lambda: FinancialEntry.objects.get(pk=entry.pk).is_archived)
                    goto(page, '/painel/caixa/?status=archived')
                    inspect(page, 'caixa-lixeira', engine, width)
                    goto(page, f'/painel/caixa/{entry.pk}/')
                    page.get_by_role('button', name='Restaurar lançamento', exact=True).click()
                    expect(page.locator('#action-confirm')).to_be_visible()
                    page.locator('#action-confirm [data-confirm-accept]').click()
                    expect(page.get_by_text('Lançamento restaurado como pendente.', exact=True)).to_be_visible()
                    assert not db(lambda: FinancialEntry.objects.get(pk=entry.pk).is_archived)
                    report['flows'].append(engine + ': criar/editar/remover horários/excluir turma; excluir/restaurar caixa')
                assert not report['errors'], report['errors']
                print(engine, width, 'passed', flush=True)
                context.close()
                browser.close()
finally:
    FinancialEvent.objects.filter(entry__description__startswith=tag).delete()
    FinancialEntry.objects.filter(description__startswith=tag).delete()
    FinancialCategory.objects.filter(name__startswith=tag).delete()
    User.objects.filter(email__startswith=tag).delete()
    ClassGroup.objects.filter(name__startswith=tag).delete()
    Plan.objects.filter(name__startswith=tag).delete()
    Venue.objects.filter(name__startswith=tag).delete()
    PointRule.objects.filter(name__startswith=tag).delete()
    Product.objects.filter(name__startswith=tag).delete()
    Announcement.objects.filter(title__startswith=tag).delete()
    (OUT / ('report-' + os.getenv('CRUD_ENGINE', 'all') + '.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'layouts': len(report['layouts']), 'flows': report['flows'], 'errors': report['errors']}, ensure_ascii=False))
