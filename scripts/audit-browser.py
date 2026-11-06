"""Local end-to-end audit. Uses isolated browser and synthetic local records only."""
import io
import json
import os
from pathlib import Path
import secrets
from concurrent.futures import ThreadPoolExecutor
import sys
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / '.local/testdeps'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'teamfarias.settings')
import django
django.setup()
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from PIL import Image
from playwright.sync_api import sync_playwright, expect
expect.set_options(timeout=30000)
from accounts.models import User
from billing.models import Invoice
from core.models import Product
from core.testing import make_admin, make_professor, make_student, make_plan, make_group, make_session, make_invoice

assert settings.DEBUG and settings.DATABASES['default']['HOST'] in ('127.0.0.1', 'localhost'), 'Only local development databases are allowed.'
BASE = 'http://127.0.0.1:8017'
OUT = ROOT / '.local/browser-audit'
OUT.mkdir(exist_ok=True)
tag = 'qa-shop-' + secrets.token_hex(4)
password = secrets.token_urlsafe(24)
report = {'layouts': [], 'flows': [], 'errors': []}
user_ids = []
product = group = plan = None
image_path = None
uploaded_photo = None

def database(operation):
    # Playwright runs an event loop even through its sync API; keep Django ORM in a worker.
    def work():
        from django.db import connections
        try:return operation()
        finally:connections.close_all()
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(work).result()


def layout(page, route, width, role):
    page.set_viewport_size({'width': width, 'height': 850})
    response=page.goto(BASE + route, wait_until='networkidle')
    assert response.status == 200, (route,response.status)
    assert page.evaluate('window.htmx.config.globalViewTransitions') is False
    page.add_style_tag(content='*,*::before,*::after{animation:none!important;transition:none!important}')
    page.evaluate('document.fonts.ready')
    issues=page.evaluate('''() => {
      const width=innerWidth, root=document.querySelector('main');
      if(!root) return ['missing main'];
      return [...root.querySelectorAll('.card,.group-card,.product-card,.install-status,.panel,input,select,textarea,.btn,h1,h2,h3,p,pre,label,summary')].filter(el=>{
        const s=getComputedStyle(el),r=el.getBoundingClientRect();
        return r.width>0 && r.height>0 && s.visibility!=='hidden' && s.display!=='none' && (r.right>width+1 || r.left < -1);
      }).map(el=>({tag:el.tagName,class:el.className,text:el.textContent.trim().slice(0,70),right:Math.round(el.getBoundingClientRect().right)})).slice(0,15);
    }''')
    document_overflow=page.evaluate('document.documentElement.scrollWidth > innerWidth + 1')
    report['layouts'].append({'role':role,'route':route,'width':width,'overflow':issues,'document_overflow':document_overflow})
    (OUT/'progress.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if width in (390,1366) and route in ('/','/produtos/','/app/','/painel/produtos/'):
        slug = route.strip('/').replace('/', '-') or 'home'
        page.screenshot(path=str(OUT/f'preview-{role}-{width}-{slug}.png'))
    if issues or document_overflow:
        page.screenshot(path=str(OUT/f'overflow-{role}-{width}-{len(report["layouts"])}.png'),full_page=True)

def login(page,user):
    page.goto(BASE+'/entrar/',wait_until='networkidle')
    page.locator('input[name="username"]').fill(user.email)
    page.locator('input[name="password"]').fill(password)
    page.get_by_role('button',name='Entrar na minha conta',exact=True).click()
    page.wait_for_url('**/painel/' if user.role != 'aluno' else '**/app/')

try:
    with transaction.atomic():
        admin=make_admin(email=tag+'-admin@example.invalid',password=password);user_ids.append(admin.pk)
        professor=make_professor(email=tag+'-prof@example.invalid',password=password);user_ids.append(professor.pk)
        plan=make_plan(name=tag+' Plano de treinamento com acompanhamento completo')
        group=make_group(name=tag+' Turma de vôlei de praia para iniciantes',professor=professor)
        student=make_student(email=tag+'-student@example.invalid',group=group,plan=plan)
        student.user.first_name='Ana Carolina';student.user.last_name='Albuquerque de Farias e Silva';student.user.save();student.user.set_password(password);student.user.save(update_fields=['password']);user_ids.append(student.user.pk)
        session=make_session(group)
        invoice=make_invoice(student);invoice.mark_paid(user=admin)
        product=Product.objects.create(name='Camisa Team Farias personalizada — teste de apresentação',description='Produto sintético usado somente na auditoria local. Teste com texto longo, tamanhos e personalização.',category='Camisas',is_active=True,sizes='PP, P, M, G, GG',colors='Roxa, Preta',customize_name=True,customize_number=True)
        stream=io.BytesIO();Image.new('RGB',(700,700),'#684098').save(stream,'WEBP')
        product.image.save(tag+'.webp',ContentFile(stream.getvalue()));image_path=Path(product.image.path)
    print('Fixtures ready; launching isolated browser.',flush=True)
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(channel='msedge',headless=True)
        context=browser.new_context(viewport={'width':390,'height':850},reduced_motion='no-preference')
        page=context.new_page()
        page.set_default_navigation_timeout(60000)
        page.on('pageerror',lambda error:report['errors'].append(str(error)))
        for width in ([] if os.getenv('AUDIT_SKIP_PUBLIC') else [320,390,768,1366]):
            for route in ['/', '/produtos/', product.get_absolute_url(),'/entrar/']:
                layout(page,route,width,'public')
        page.set_viewport_size({'width':390,'height':850});page.goto(BASE+'/',wait_until='networkidle')
        page.evaluate('scrollTo(0,260)');expect(page.locator('[data-header]')).to_have_class(__import__('re').compile('is-scrolled'))
        page.get_by_role('button',name='Abrir menu',exact=True).click()
        expect(page.locator('[data-mobile-nav]')).to_be_visible()
        page.locator('.mobile-nav__links').get_by_role('link',name='Produtos',exact=True).click()
        expect(page).to_have_url(BASE+'/produtos/')
        print('Browser flow completed.',flush=True)
        report['flows'].append('mobile capsule and menu navigate with HTMX')
        page.goto(BASE+product.get_absolute_url(),wait_until='networkidle')
        page.get_by_label('Seu nome').fill('QA Cliente')
        page.locator('select[name="size"]').select_option('M')
        page.locator('select[name="color"]').select_option('Roxa')
        page.get_by_label('Nome na camisa').fill('TESTE')
        page.get_by_label('Número na camisa').fill('07')
        page.get_by_label('Quantidade').fill('2')
        page.get_by_role('button',name='Revisar pedido').click()
        expect(page.get_by_role('heading',name='Confira seu pedido.')).to_be_visible()
        link=page.get_by_role('link',name='Continuar no WhatsApp').get_attribute('href')
        message=parse_qs(urlparse(link).query)['text'][0]
        assert all(t in message for t in ['Quantidade: 2','Nome na estampa: TESTE','Número na estampa: 07','Tamanho: M'])
        page.screenshot(path=str(OUT/'pedido-mobile.png'),full_page=True)
        page.get_by_role('button',name='Editar detalhes').click()
        expect(page.get_by_label('Nome na camisa')).to_have_value('TESTE')
        print('Browser flow completed.',flush=True)
        report['flows'].append('custom product order, review, encoded WhatsApp message and editing; no message sent')
        login(page,admin)
        page.goto(BASE+f'/painel/produtos/{product.pk}/editar/',wait_until='networkidle')
        page.get_by_label('valor de referência (R$)',exact=False).fill('89.90')
        page.locator('input[type=file]').set_input_files(str(image_path))
        page.get_by_role('button',name='Salvar produto',exact=True).click()
        expect(page).to_have_url(BASE+'/painel/produtos/')
        database(product.refresh_from_db);assert str(product.price)=='89.90'
        uploaded_photo=Path(product.image.path)
        print('Browser flow completed.',flush=True)
        report['flows'].append('admin photo upload and product editing through HTMX multipart form')
        admin_routes=['/painel/','/painel/turmas/','/painel/planos/','/painel/matriculas/','/painel/matriculas/nova/','/painel/alunos/','/painel/agenda/','/painel/pontos/','/painel/financeiro/','/painel/comunicados/','/painel/configuracoes/','/painel/relatorios/','/painel/produtos/','/painel/produtos/novo/','/ajuda/',f'/painel/turmas/{group.pk}/editar/',f'/painel/agenda/{session.pk}/presenca/',f'/painel/alunos/{student.pk}/',f'/painel/produtos/{product.pk}/editar/']
        for width in [320,390,768,1366]:
            for route in admin_routes:layout(page,route,width,'admin')
        for width in [390,1366]:
            database(invoice.refresh_from_db)
            if invoice.status!='paga':database(lambda: invoice.mark_paid(user=admin))
            page.set_viewport_size({'width':width,'height':850});page.goto(BASE+'/painel/financeiro/',wait_until='networkidle')
            button=page.locator('form[data-confirm]').filter(has=page.locator('input[name="invoice"][value="'+str(invoice.pk)+'"]')).filter(visible=True).get_by_role('button',name='Reabrir',exact=True)
            button.click();expect(page.locator('#action-confirm')).to_be_visible()
            page.locator('#action-confirm').get_by_role('button',name='Cancelar',exact=True).click()
            database(invoice.refresh_from_db);assert invoice.status=='paga'
            button.click();page.screenshot(path=str(OUT/f'confirmacao-{width}.png'))
            page.get_by_role('button',name='Confirmar reabertura',exact=True).click()
            expect(page.locator('#action-confirm')).not_to_be_visible()
            expect(page.get_by_text('Mensalidade reaberta.',exact=True)).to_be_visible()
            database(invoice.refresh_from_db);assert invoice.status=='aberta' and not database(invoice.payments.exists)
        print('Browser flow completed.',flush=True)
        report['flows'].append('cancel then reopen paid charge on mobile and desktop, verified in PostgreSQL')
        page.set_viewport_size({'width':390,'height':850});page.goto(BASE+'/painel/turmas/',wait_until='networkidle')
        page.get_by_role('button',name='Abrir menu',exact=True).click()
        page.get_by_role('button',name='Sair da conta',exact=True).click();expect(page).to_have_url(BASE+'/')
        login(page,student.user)
        for width in [320,390,768,1366]:
            for route in ['/app/','/app/perfil/','/app/agenda/','/app/pontos/','/app/mensalidades/','/app/comunicados/','/app/produtos/',f'/app/produtos/{product.pk}/','/ajuda/']:
                layout(page,route,width,'student')
        print('Browser flow completed.',flush=True)
        report['flows'].append('admin and student login, mobile sidebar and logout')
        browser.close()
finally:
    report['passed_layouts']=sum(not row['overflow'] and not row['document_overflow'] for row in report['layouts'])
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    with transaction.atomic():
        User.objects.filter(pk__in=user_ids,email__startswith=tag).delete()
        if group:group.delete()
        if plan:plan.delete()
        if product:product.delete()
    if uploaded_photo and uploaded_photo.resolve().is_relative_to(Path(settings.MEDIA_ROOT).resolve()):
        uploaded_photo.unlink(missing_ok=True)
    if image_path and image_path.resolve().is_relative_to(Path(settings.MEDIA_ROOT).resolve()) and image_path.name.startswith(tag):
        image_path.unlink(missing_ok=True)
print(json.dumps({'layouts':len(report['layouts']),'passed':report['passed_layouts'],'flows':report['flows'],'errors':report['errors']},ensure_ascii=False))
assert report['passed_layouts']==len(report['layouts']), 'Responsive overflow detected; see report.'
assert not report['errors'], 'Browser errors detected.'
