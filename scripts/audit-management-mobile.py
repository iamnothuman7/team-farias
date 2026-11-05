"""Mobile management regression checks. Synthetic local data only; never sends messages."""
import json,os,secrets,sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'.local/testdeps')]
os.environ.setdefault('DJANGO_SETTINGS_MODULE','teamfarias.settings')
import django
django.setup()
from django.conf import settings
from django.utils import timezone
from accounts.models import User,Student
from billing.models import Plan,Invoice,next_competence
from school.models import Enrollment
from core.testing import make_admin,make_plan,make_group,make_student,make_invoice
from playwright.sync_api import sync_playwright,expect
expect.set_options(timeout=30000)
assert settings.DEBUG and settings.DATABASES['default']['HOST'] in ['localhost','127.0.0.1']
BASE='http://127.0.0.1:8017';OUT=ROOT/'.local/management-mobile';OUT.mkdir(exist_ok=True)
tag='qa-manage-'+secrets.token_hex(4);password=secrets.token_urlsafe(24)
admin=make_admin(email=tag+'-admin@example.invalid',password=password)
plan=make_plan(name=tag+' Plano completo de treinamento e acompanhamento individual',fee='999999.99')
group=make_group(name=tag+' Turma de aperfeiçoamento técnico de vôlei de praia')
student=make_student(email=tag+'-student@example.invalid',group=group,plan=plan)
student.nickname='MariaEduardaAlbuquerqueFariasSilvaSantos';student.save()
pending=make_student(email=tag+'-pending@example.invalid',group=group,plan=plan,status='pendente')
Enrollment.objects.filter(student=pending).update(status='pendente')
pending_id=pending.enrollments.get().pk
invoice=make_invoice(student);invoice.amount=Decimal('999999.99');invoice.plan=plan;invoice.save()
report={'layouts':[],'flows':[],'errors':[]}

def db(fn):
 def run():
  from django.db import connections
  try:return fn()
  finally:connections.close_all()
 with ThreadPoolExecutor(max_workers=1) as pool:return pool.submit(run).result()

def inspect(page,state,engine,width,root='main'):
 result=page.locator(root).evaluate('''root=>{const r=root.getBoundingClientRect(),dialog=root.tagName==='DIALOG';const left=dialog?r.left:0,right=dialog?r.right:innerWidth;return [...root.querySelectorAll('h1,h2,h3,p,strong,span,label,input,select,textarea,button,legend,.card,.field,.form-errors,.selection-caption,.dialog__foot')].filter(el=>{const b=el.getBoundingClientRect(),s=getComputedStyle(el);if(!b.width||!b.height||el.closest('svg')||s.visibility==='hidden')return false;return b.left<left-1||b.right>right+1||(!el.matches('input,textarea,select')&&s.overflowX==='visible'&&el.scrollWidth>el.clientWidth+2)}).map(el=>({tag:el.tagName,cls:el.className,text:el.textContent.trim().slice(0,65)}))}''')
 assert not result,(state,width,result)
 assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
 if root.startswith('#'):
  rect=page.locator(root).bounding_box();assert rect['x']>=0 and rect['y']>=0 and rect['x']+rect['width']<=width+1
  assert rect['y']+rect['height']<=page.viewport_size['height']+1
 report['layouts'].append({'state':state,'engine':engine,'width':width})
 if width in [320,390]:page.screenshot(path=str(OUT/f'{engine}-{width}-{state}.png'),full_page=root=='main',mask=[page.locator('.credential-box__password')])

def goto(page,path):
 assert page.goto(BASE+path,wait_until='networkidle').status==200

try:
 with sync_playwright() as p:
  for engine in ['chromium','webkit']:
   browser=p.chromium.launch(channel='msedge',headless=True) if engine=='chromium' else p.webkit.launch(headless=True)
   for width,height in [(320,740),(390,844),(844,390)]:
    if os.getenv('MANAGEMENT_WIDTH') and width!=int(os.environ['MANAGEMENT_WIDTH']):continue
    context=browser.new_context(viewport={'width':width,'height':height},service_workers='block',reduced_motion='no-preference')
    context.add_init_script("Object.defineProperty(navigator,'standalone',{get:()=>true});document.addEventListener('DOMContentLoaded',()=>{document.documentElement.style.setProperty('--safe-top','47px');document.documentElement.style.setProperty('--safe-bottom','34px')});")
    page=context.new_page();page.set_default_timeout(30000);page.set_default_navigation_timeout(60000)
    page.on('pageerror',lambda e:report['errors'].append(str(e)))
    goto(page,'/entrar/');page.get_by_label('E-mail',exact=True).fill(admin.email);page.get_by_label('Senha',exact=True).fill(password);page.get_by_role('button',name='Entrar na minha conta').click();expect(page).to_have_url(BASE+'/painel/')
    goto(page,'/painel/planos/novo/');page.get_by_role('button',name='Salvar plano').click();expect(page.locator('.field--error').first).to_be_visible();inspect(page,'plano-erros',engine,width)
    goto(page,f'/painel/planos/{plan.pk}/editar/');inspect(page,'plano-editar',engine,width)
    if width==390:
     page.locator('.management-form [name="description"]').fill('Plano de testes com descrição longa para conferir leitura, alinhamento e preservação dos dados.')
     page.get_by_role('button',name='Salvar plano').click();expect(page).to_have_url(BASE+'/painel/planos/')
     assert db(lambda: Plan.objects.get(pk=plan.pk).description).startswith('Plano de testes')
    goto(page,'/painel/planos/');inspect(page,'planos',engine,width)
    goto(page,'/painel/matriculas/nova/');page.get_by_role('button',name='Criar matrícula e liberar acesso').click();expect(page.locator('.field--error').first).to_be_visible();inspect(page,'matricula-erros',engine,width)
    page.locator('[name="class_group"]').select_option(str(group.pk));page.locator('[name="plan"]').select_option(str(plan.pk))
    expect(page.locator('#id_plan-selection')).to_contain_text(plan.name)
    page.locator('#id_plan').scroll_into_view_if_needed();inspect(page,'matricula-selecoes',engine,width)
    if width==390:
     email=tag+'-'+engine+'-created@example.invalid'
     fields={'first_name':'Ana Carolina','last_name':'Albuquerque de Farias e Silva','email':email,'phone':'88999999999','birth_date':'2000-04-02','password':password}
     for key,value in fields.items():page.locator('[name="'+key+'"]').fill(value)
     page.get_by_role('button',name='Criar matrícula e liberar acesso').click();expect(page.get_by_text('Matrícula concluída',exact=True)).to_be_visible();inspect(page,'matricula-criada',engine,width)
     created_id=db(lambda: Student.objects.get(user__email=email).pk)
     assert db(lambda: Enrollment.objects.filter(student_id=created_id,plan=plan,status='ativa').exists())
     assert db(lambda: Invoice.objects.filter(student_id=created_id).count())==1
     report['flows'].append(engine+': matrícula cria aluno, plano e primeira cobrança')
    goto(page,'/painel/matriculas/?status=pendente')
    page.locator('form[data-confirm]').filter(has=page.locator('input[name="enrollment"][value="'+str(pending_id)+'"]')).get_by_role('button',name='Recusar inscrição',exact=True).click();expect(page.locator('#action-confirm')).to_be_visible();inspect(page,'matricula-confirmacao',engine,width,'#action-confirm');page.locator('#action-confirm [data-confirm-cancel]').first.click()
    goto(page,'/painel/financeiro/')
    form=page.locator('form').filter(has=page.locator('input[name="action"][value="create"]'))
    form.locator('[name="student"]').select_option(str(student.pk));form.locator('[name="plan"]').select_option(str(plan.pk))
    ref=next_competence(timezone.localdate().replace(day=1),2 if engine=='chromium' else 3)
    form.locator('[name="competence"]').fill(ref.isoformat());form.locator('[name="due_date"]').fill(ref.replace(day=10).isoformat());form.locator('[name="amount"]').fill('100');form.locator('[name="discount"]').fill('101')
    form.get_by_role('button',name='Criar mensalidade').click();expect(page.locator('.field--error').first).to_be_visible();inspect(page,'financeiro-erros',engine,width)
    if width==390:
     page.locator('[name="discount"]').fill('10');page.get_by_role('button',name='Criar mensalidade').click();expect(page.get_by_text('Mensalidade criada.',exact=True)).to_be_visible()
     assert db(lambda: Invoice.objects.filter(student=student,competence=ref,discount=10).exists())
    goto(page,'/painel/financeiro/')
    pay=page.locator('[data-dialog-open="pay-dialog"][data-invoice="'+str(invoice.pk)+'"]').filter(visible=True)
    pay.click();expect(page.locator('#pay-dialog')).to_be_visible();inspect(page,'pagamento',engine,width,'#pay-dialog')
    page.locator('#pay-method').select_option('transferencia');page.locator('#pay-note').fill('Observação de teste com texto longo para conferir a quebra de linha no pagamento, sem ultrapassar o limite do campo.')
    if width==390:
     page.evaluate("Object.defineProperty(visualViewport,'height',{configurable:true,get:()=>390});Object.defineProperty(visualViewport,'offsetTop',{configurable:true,get:()=>50});visualViewport.dispatchEvent(new Event('resize'))")
     page.wait_for_timeout(100)
     r=page.locator('#pay-dialog').bounding_box();assert r['y']>=50 and r['y']+r['height']<=440,r
     foot=page.locator('#pay-dialog .dialog__foot').bounding_box();assert foot['y']+foot['height']<=440,foot
     note=page.locator('#pay-note').bounding_box();body=page.locator('#pay-dialog .dialog__body').bounding_box()
     assert note['y']>=body['y']-1 and note['y']+note['height']<=body['y']+body['height']+1,(note,body)
     page.locator('#pay-dialog').get_by_role('button',name='Confirmar baixa',exact=True).focus()
     page.wait_for_timeout(100)
     focused=page.locator('#pay-dialog').bounding_box();assert abs(focused['y']-r['y'])<1 and focused['y']+focused['height']<=440,focused
     page.screenshot(path=str(OUT/f'{engine}-teclado-pagamento.png'))
     page.evaluate("delete visualViewport.height;delete visualViewport.offsetTop;document.activeElement.blur();visualViewport.dispatchEvent(new Event('resize'))")
    page.locator('#pay-dialog').get_by_role('button',name='Cancelar',exact=True).click();pay.click()
    expect(page.locator('#pay-note')).to_have_value('');expect(page.locator('#pay-method')).to_have_value('pix')
    if width==390:
     page.locator('#pay-dialog').get_by_role('button',name='Confirmar baixa',exact=True).click();expect(page.locator('#pay-dialog')).not_to_be_visible()
     assert db(lambda: Invoice.objects.get(pk=invoice.pk).status)=='paga'
     reopen=page.locator('form[data-confirm]').filter(has=page.locator('input[name="invoice"][value="'+str(invoice.pk)+'"]')).filter(visible=True)
     reopen.get_by_role('button',name='Reabrir',exact=True).click();expect(page.locator('#action-confirm')).to_be_visible();inspect(page,'reabrir-confirmacao',engine,width,'#action-confirm')
     page.locator('#action-confirm').get_by_role('button',name='Cancelar',exact=True).click();assert db(lambda: Invoice.objects.get(pk=invoice.pk).status)=='paga'
     reopen.get_by_role('button',name='Reabrir',exact=True).click();page.get_by_role('button',name='Confirmar reabertura',exact=True).click();expect(page.get_by_text('Mensalidade reaberta.',exact=True)).to_be_visible()
     assert db(lambda: Invoice.objects.get(pk=invoice.pk).status)=='aberta'
     assert db(lambda: invoice.payments.count())==0
     report['flows'].append(engine+': erro/desconto válido, cancelar pagamento, pagar, cancelar reabertura e reabrir')
    else:page.keyboard.press('Escape');expect(page.locator('#pay-dialog')).not_to_be_visible()
    assert not report['errors'],report['errors']
    print(engine,width,'passed',flush=True);context.close()
   browser.close()
finally:
 User.objects.filter(email__startswith=tag).delete()
 group.delete()
 Plan.objects.filter(name__startswith=tag).delete()
 (OUT/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps({'layouts':len(report['layouts']),'flows':report['flows'],'errors':report['errors']},ensure_ascii=False))
