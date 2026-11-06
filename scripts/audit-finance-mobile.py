"""Auditoria visual e funcional do caixa, somente com dados locais descartáveis."""
import csv
import json
import os
import secrets
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
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
from billing.models import FinancialCategory, FinancialEntry, FinancialEvent
from core.testing import make_admin
from playwright.sync_api import sync_playwright, expect

expect.set_options(timeout=30000)
assert settings.DEBUG and settings.DATABASES['default']['HOST'] in ('localhost', '127.0.0.1')
BASE = 'http://127.0.0.1:8017'
OUT = ROOT / '.local/finance-mobile'
OUT.mkdir(parents=True, exist_ok=True)
tag = 'qa-cash-' + secrets.token_hex(4)
password = secrets.token_urlsafe(24)
admin = make_admin(email=tag + '@example.invalid', password=password)
expense_category = FinancialCategory.objects.create(name=tag + ' DespesasComEquipamentosTreinamentoManutencaoDaEscolinha', kind='expense')
income_category = FinancialCategory.objects.create(name=tag + ' Receitas com produtos e eventos da escolinha', kind='income')
today = timezone.localdate()
description = tag + ' EquipamentosParaTreinamentoDeVoleiDeAreiaDaEscolinha' * 2
entry = save_financial_entry(FinancialEntry(
    kind='expense', category=expense_category, description=description,
    counterparty='FornecedorComNomeCompletoMuitoLongoParaConferirQuebraDeLinha' * 2,
    amount=Decimal('9999999999.99'), due_date=today,
    notes='Observação detalhada para conferir alinhamento e quebra de linha nos cartões. ' * 5,
), user=admin)
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


def inspect(page, state, engine, width, root='main'):
    expect(page.locator('.htmx-request,.htmx-swapping,.htmx-settling,html.is-loading')).to_have_count(0)
    expect(page.locator('.app-content')).to_have_css('opacity', '1')
    failures = page.locator(root).evaluate('''root => {
      const rect = root.getBoundingClientRect(), dialog = root.tagName === 'DIALOG';
      const left = dialog ? rect.left : 0, right = dialog ? rect.right : innerWidth;
      return [...root.querySelectorAll('h1,h2,h3,p,strong,span,dt,dd,label,input,select,textarea,button,legend,.card,.field,.form-errors,.selection-caption,.dialog__foot')]
        .filter(el => { const b=el.getBoundingClientRect(),s=getComputedStyle(el);
          if (!b.width || !b.height || el.closest('svg') || s.visibility==='hidden') return false;
          return b.left<left-1 || b.right>right+1 || (!el.matches('input,textarea,select') && s.overflowX==='visible' && el.scrollWidth>el.clientWidth+2);
        }).map(el=>({tag:el.tagName,cls:el.className,text:el.textContent.trim().slice(0,70)}));
    }''')
    assert not failures, (state, engine, width, failures)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    if root.startswith('#'):
        bounds = page.locator(root).bounding_box()
        assert bounds['x'] >= 0 and bounds['y'] >= 0 and bounds['x'] + bounds['width'] <= width + 1, bounds
        assert bounds['y'] + bounds['height'] <= page.viewport_size['height'] + 1, bounds
    report['layouts'].append({'state': state, 'engine': engine, 'width': width})
    if width in (320, 390, 1366):
        page.screenshot(path=str(OUT / f'{engine}-{width}-{state}.png'), full_page=root == 'main')


def goto(page, path):
    assert page.goto(BASE + path, wait_until='networkidle').status == 200, path


def state():
    return db(lambda: FinancialEntry.objects.get(pk=entry.pk).status)


def expect_detail(page):
    expect(page).to_have_url(BASE + f'/painel/caixa/{entry.pk}/')
    expect(page.locator('.finance-detail')).to_be_visible()


def save_form(page, form, engine, width, state_name):
    button = form.get_by_role('button', name='Salvar lançamento')
    try:
        button.click()
    except Exception:
        page.screenshot(path=str(OUT / f'{engine}-{width}-{state_name}-falha.png'))
        print(page.evaluate('''() => { const side=document.querySelector('.app-sidebar'),button=document.querySelector('.finance-entry-form button[type=submit]'),b=button.getBoundingClientRect(),cover=document.elementFromPoint(b.x+b.width/2,b.y+b.height/2); return {sidebar:side.getBoundingClientRect().toJSON(),hover:side.matches(':hover'),focused:side.matches(':focus-within'),active:document.activeElement.tagName,button:b.toJSON(),cover:cover?.className}; }'''), flush=True)
        raise


try:
    with sync_playwright() as p:
        for engine in ('chromium', 'webkit'):
            if os.getenv('FINANCE_ENGINE') and engine != os.environ['FINANCE_ENGINE']:
                continue
            browser = p.chromium.launch(channel='msedge', headless=True) if engine == 'chromium' else p.webkit.launch(headless=True)
            for width, height in ((320, 740), (390, 844), (844, 390), (1366, 768)):
                if os.getenv('FINANCE_WIDTH') and width != int(os.environ['FINANCE_WIDTH']):
                    continue
                context = browser.new_context(viewport={'width': width, 'height': height}, service_workers='block', reduced_motion='no-preference', accept_downloads=True)
                if width <= 844:
                    context.add_init_script("Object.defineProperty(navigator,'standalone',{get:()=>true});document.addEventListener('DOMContentLoaded',()=>{document.documentElement.style.setProperty('--safe-top','47px');document.documentElement.style.setProperty('--safe-bottom','34px')});")
                page = context.new_page()
                page.set_default_timeout(30000)
                page.set_default_navigation_timeout(60000)
                page.on('pageerror', lambda error: report['errors'].append(str(error)))
                goto(page, '/entrar/')
                page.get_by_label('E-mail', exact=True).fill(admin.email)
                page.get_by_label('Senha', exact=True).fill(password)
                page.get_by_role('button', name='Entrar na minha conta').click()
                expect(page).to_have_url(BASE + '/painel/')

                goto(page, '/painel/caixa/')
                if width > 1024:
                    page.locator('.app-sidebar').hover()
                    expect(page.locator('.app-sidebar')).to_have_css('width', '272px')
                    page.mouse.move(width - 40, 100)
                    expect(page.locator('.app-sidebar')).to_have_css('width', '84px')
                    report['flows'].append(engine + ': sidebar desktop abre no hover e recolhe ao sair')
                inspect(page, 'caixa', engine, width)
                page.locator('.finance-filters > summary').click()
                inspect(page, 'filtros-abertos', engine, width)
                page.locator('.finance-filters [name="end"]').fill((today.replace(day=1) - timedelta(days=1)).isoformat())
                page.get_by_role('button', name='Aplicar filtros', exact=True).click()
                expect(page.locator('.finance-filters .field--error')).to_be_visible()
                inspect(page, 'filtros-invalidos', engine, width)

                goto(page, '/painel/caixa/novo/?tipo=expense')
                form = page.locator('.finance-entry-form')
                save_form(page, form, engine, width, 'novo-pendente')
                expect(page.locator('.field--error').first).to_be_visible()
                inspect(page, 'novo-pendente-erros', engine, width)
                if width > 1024:
                    # select_option changes a native select without moving the mouse.
                    # Hover the control first, matching a real desktop interaction.
                    form.locator('[name="category"]').hover()
                form.locator('[name="category"]').select_option(str(expense_category.pk))
                expect(page.locator('#id_category-selection')).to_contain_text(expense_category.name)
                if width > 1024:
                    form.locator('[name="status"]').hover()
                    expect(page.locator('.app-sidebar')).to_have_css('width', '84px')
                form.locator('[name="status"]').select_option('settled')
                save_form(page, form, engine, width, 'novo-realizado')
                expect(form.locator('[name="settled_at"]')).to_be_visible()
                inspect(page, 'novo-realizado-erros', engine, width)

                goto(page, f'/painel/caixa/{entry.pk}/')
                inspect(page, 'detalhes', engine, width)
                page.locator('.finance-changes > summary').first.click()
                inspect(page, 'historico-aberto', engine, width)
                page.get_by_role('button', name='Confirmar pagamento', exact=True).click()
                expect(page.locator('#settle-dialog')).to_be_visible()
                inspect(page, 'baixa-popup', engine, width, '#settle-dialog')
                page.locator('#settle-dialog [name="date"]').fill((today + timedelta(days=1)).isoformat())
                page.locator('#settle-dialog [name="method"]').select_option('pix')
                page.locator('#settle-dialog').get_by_role('button', name='Confirmar baixa').click()
                expect(page.locator('#settle-dialog .field--error')).to_be_visible()
                inspect(page, 'baixa-data-futura', engine, width, '#settle-dialog')
                assert state() == 'pending'

                if width == 390:
                    page.locator('#settle-dialog [name="date"]').focus()
                    page.evaluate("Object.defineProperty(visualViewport,'height',{configurable:true,get:()=>390});Object.defineProperty(visualViewport,'offsetTop',{configurable:true,get:()=>50});visualViewport.dispatchEvent(new Event('resize'))")
                    page.wait_for_timeout(120)
                    bounds = page.locator('#settle-dialog').bounding_box()
                    footer = page.locator('#settle-dialog .dialog__foot').bounding_box()
                    assert bounds['y'] >= 50 and bounds['y'] + bounds['height'] <= 440, bounds
                    assert footer['y'] + footer['height'] <= 440, footer
                    page.locator('#settle-dialog').get_by_role('button', name='Confirmar baixa').focus()
                    page.wait_for_timeout(100)
                    focused = page.locator('#settle-dialog').bounding_box()
                    assert abs(focused['y'] - bounds['y']) < 1 and focused['y'] + focused['height'] <= 440, focused
                    page.screenshot(path=str(OUT / f'{engine}-390-teclado-baixa.png'))
                    report['layouts'].append({'state': 'teclado-popup', 'engine': engine, 'width': width})
                    page.evaluate("delete visualViewport.height;delete visualViewport.offsetTop;document.activeElement.blur();visualViewport.dispatchEvent(new Event('resize'))")
                page.locator('#settle-dialog').get_by_role('button', name='Voltar').click()
                expect(page.locator('#settle-dialog')).not_to_be_visible()
                assert state() == 'pending'

                if width == 390:
                    page.get_by_role('button', name='Confirmar pagamento', exact=True).click()
                    page.locator('#settle-dialog [name="date"]').fill(today.isoformat())
                    page.locator('#settle-dialog [name="method"]').select_option('transferencia')
                    page.locator('#settle-dialog').get_by_role('button', name='Confirmar baixa').click()
                    expect(page.get_by_text('Pagamento confirmado.', exact=True)).to_be_visible()
                    assert state() == 'settled'
                    page.get_by_role('button', name='Reabrir lançamento', exact=True).click()
                    expect(page.locator('#action-confirm')).to_be_visible()
                    inspect(page, 'reabertura-popup', engine, width, '#action-confirm')
                    page.locator('#action-confirm').get_by_role('button', name='Cancelar', exact=True).click()
                    assert state() == 'settled'
                    page.get_by_role('button', name='Reabrir lançamento', exact=True).click()
                    page.get_by_role('button', name='Confirmar reabertura', exact=True).click()
                    expect(page.get_by_text('Lançamento reaberto.', exact=True)).to_be_visible()
                    assert state() == 'pending'
                    page.get_by_role('button', name='Cancelar lançamento', exact=True).click()
                    expect(page.locator('#action-confirm')).to_be_visible()
                    inspect(page, 'cancelamento-popup', engine, width, '#action-confirm')
                    page.locator('#action-confirm [data-confirm-accept]').click()
                    expect(page.get_by_text('Lançamento cancelado. O histórico foi preservado.', exact=True)).to_be_visible()
                    assert state() == 'cancelled'
                    page.get_by_role('button', name='Reabrir lançamento', exact=True).click()
                    page.locator('#action-confirm [data-confirm-accept]').click()
                    expect(page.get_by_role('button', name='Confirmar pagamento', exact=True)).to_be_visible()
                    assert state() == 'pending'
                    report['flows'].append(engine + ': baixa inválida, voltar, confirmar pagamento, cancelar reabertura, reabrir, cancelar lançamento e recuperar')

                goto(page, f'/painel/caixa/{entry.pk}/editar/')
                inspect(page, 'editar-lancamento', engine, width)
                if width == 390:
                    page.locator('[name="notes"]').fill('Observação editada no celular para conferir histórico. ' * 6)
                    page.get_by_role('button', name='Salvar lançamento', exact=True).click()
                    expect_detail(page)
                    assert db(lambda: FinancialEntry.objects.get(pk=entry.pk).notes).startswith('Observação editada')
                    expect(page.locator('.finance-history')).to_contain_text('Lançamento atualizado')

                goto(page, '/painel/caixa/categorias/')
                inspect(page, 'categorias', engine, width)
                if width == 390:
                    category_name = tag + ' ' + engine + ' Taxas e manutenção detalhada da escolinha'
                    page.locator('[name="name"]').fill(category_name)
                    page.locator('[name="kind"]').select_option('expense')
                    page.get_by_role('button', name='Criar categoria', exact=True).click()
                    expect(page.get_by_text('Categoria criada.', exact=True)).to_be_visible()
                    created_category_id = db(lambda: FinancialCategory.objects.get(name=category_name).pk)
                    goto(page, f'/painel/caixa/categorias/{created_category_id}/editar/')
                    inspect(page, 'editar-categoria', engine, width)
                    page.locator('[name="is_active"]').uncheck()
                    page.get_by_role('button', name='Salvar categoria', exact=True).click()
                    expect(page.get_by_text('Categoria atualizada.', exact=True)).to_be_visible()
                    assert db(lambda: FinancialCategory.objects.get(pk=created_category_id).is_active) is False

                    goto(page, '/painel/caixa/novo/?tipo=income')
                    form = page.locator('.finance-entry-form')
                    income_description = tag + ' ' + engine + ' Camisa personalizada'
                    form.locator('[name="description"]').fill(income_description)
                    form.locator('[name="category"]').select_option(str(income_category.pk))
                    form.locator('[name="counterparty"]').fill('Cliente de teste local')
                    form.locator('[name="amount"]').fill('45,50')
                    form.locator('[name="due_date"]').fill(today.isoformat())
                    form.locator('[name="status"]').select_option('settled')
                    form.locator('[name="settled_at"]').fill(today.isoformat())
                    form.locator('[name="method"]').select_option('pix')
                    form.get_by_role('button', name='Salvar lançamento').click()
                    expect(page.get_by_text('Lançamento registrado.', exact=True)).to_be_visible()
                    income_id = db(lambda: FinancialEntry.objects.get(description=income_description).pk)
                    assert db(lambda: FinancialEntry.objects.get(pk=income_id).amount) == Decimal('45.50')
                    assert db(lambda: FinancialEntry.objects.get(pk=income_id).status) == 'settled'
                    inspect(page, 'entrada-criada', engine, width)
                    goto(page, '/painel/caixa/?q=' + tag)
                    with page.expect_download() as download_info:
                        page.get_by_role('link', name='Exportar CSV').click()
                    download = download_info.value
                    target = OUT / f'{engine}-export.csv'
                    download.save_as(target)
                    rows = list(csv.reader(target.read_text(encoding='utf-8-sig').splitlines(), delimiter=';'))
                    assert rows[0] == ['Data', 'Vencimento', 'Tipo', 'Categoria', 'Descrição', 'Cliente / fornecedor', 'Valor (R$)', 'Situação', 'Forma', 'Origem']
                    assert any(row[4] == income_description and row[6] == '45,50' and row[7] == 'Realizado' for row in rows[1:])
                    report['flows'].append(engine + ': edição preservada, categoria criada e desativada, entrada com vírgula decimal e CSV conferido')

                assert not report['errors'], report['errors']
                print(engine, width, 'passed', flush=True)
                context.close()
            browser.close()
finally:
    # Somente as fixtures vinculadas a este administrador exclusivo.
    entry_ids = list(FinancialEntry.objects.filter(created_by=admin).values_list('pk', flat=True))
    FinancialEvent.objects.filter(entry_id__in=entry_ids).delete()
    FinancialEntry.objects.filter(pk__in=entry_ids).delete()
    FinancialCategory.objects.filter(name__startswith=tag).delete()
    User.objects.filter(pk=admin.pk, email=tag + '@example.invalid').delete()
    (OUT / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
print(json.dumps({'layouts': len(report['layouts']), 'flows': report['flows'], 'errors': report['errors']}, ensure_ascii=False))
