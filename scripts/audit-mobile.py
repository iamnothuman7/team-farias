"""Focused mobile/PWA regression audit; local synthetic student only."""
import json,os,secrets,sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'.local/testdeps')]
os.environ.setdefault('DJANGO_SETTINGS_MODULE','teamfarias.settings')
import django
django.setup()
from django.conf import settings
from accounts.models import User
from core.testing import make_student
from playwright.sync_api import sync_playwright,expect
expect.set_options(timeout=30000)
assert settings.DEBUG and settings.DATABASES['default']['HOST'] in ['localhost','127.0.0.1']
BASE='http://127.0.0.1:8017'
ENGINE=os.getenv('PWA_ENGINE','chromium')
OUT=ROOT/('.local/pwa-mobile-'+ENGINE);OUT.mkdir(exist_ok=True)
student=make_student(email='qa-pwa-'+secrets.token_hex(5)+'@example.invalid')
password=secrets.token_urlsafe(24)
student.user.set_password(password);student.user.first_name='Ana Carolina';student.user.last_name='Albuquerque de Farias e Silva';student.user.save()
uid=student.user.pk
report=[]

def login(page):
 page.goto(BASE+'/entrar/',wait_until='networkidle')
 page.get_by_label('E-mail',exact=True).fill(student.user.email)
 page.get_by_label('Senha',exact=True).fill(password)
 page.get_by_role('button',name='Entrar na minha conta',exact=True).click()
 expect(page).to_have_url(BASE+'/app/')

def contained(page):
 result=page.evaluate('''()=>{let main=document.querySelector('main');return [...main.querySelectorAll('h1,h2,h3,p,label,input,select,textarea,button,.card,.stat-card,.kv__row,dd,dt,.badge')].filter(el=>{let r=el.getBoundingClientRect();return r.width>0&&r.height>0&&(r.left< -1||r.right>innerWidth+1||el.scrollWidth>el.clientWidth+2&&getComputedStyle(el).overflowX==='visible')}).map(el=>({tag:el.tagName,cls:el.className,text:el.textContent.slice(0,70)}))}''')
 assert not result,result
 assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')

try:
 with sync_playwright() as p:
  browser=p.webkit.launch(headless=True) if ENGINE=='webkit' else p.chromium.launch(channel='msedge',headless=True)
  for width,height in [(320,740),(390,844),(430,932),(844,390),(1366,850)]:
   if os.getenv('PWA_WIDTH') and width!=int(os.environ['PWA_WIDTH']):continue
   ctx=browser.new_context(viewport={'width':width,'height':height},is_mobile=width<900,has_touch=width<900,service_workers='block',reduced_motion='no-preference')
   ctx.add_init_script("Object.defineProperty(navigator,'standalone',{get:()=>true});document.addEventListener('DOMContentLoaded',()=>{document.documentElement.style.setProperty('--safe-top','47px');document.documentElement.style.setProperty('--safe-bottom','34px')});")
   page=ctx.new_page();page.set_default_timeout(30000);page.set_default_navigation_timeout(60000)
   errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto(BASE+'/',wait_until='networkidle')
   page.evaluate("document.documentElement.style.setProperty('--safe-top','47px');document.documentElement.style.setProperty('--safe-bottom','34px')")
   assert page.evaluate('window.htmx.config.globalViewTransitions') is False
   expect(page.locator('[data-install-status]')).not_to_be_visible()
   for y in [0,400,1800]:
    page.evaluate('(y)=>scrollTo({top:y,behavior:"instant"})',y)
    # Wait for scroll event and finite CSS geometry transition.
    page.wait_for_timeout(350)
    state=page.locator('[data-header]').evaluate('''el=>{const r=el.getBoundingClientRect();const child=el.querySelector('.site-header__inner');return {top:r.top,left:r.left,right:r.right,front:el.contains(document.elementFromPoint(r.left+r.width/2,r.top+20)),children:[...child.children].every(x=>{let b=x.getBoundingClientRect();return !b.width || b.left>=r.left&&b.right<=r.right&&b.bottom<=r.bottom})}}''')
    assert state['front'] and state['children'] and state['top']>=47 and state['right']<=width+1,state
   page.screenshot(path=str(OUT/f'capsule-{width}.png'))
   if width<1181:
    page.get_by_role('button',name='Abrir menu',exact=True).click()
    page.locator('.mobile-nav__links').get_by_role('link',name='Produtos',exact=True).click()
    expect(page).to_have_url(BASE+'/produtos/')
    page.evaluate('scrollTo({top:600,behavior:"instant"})');page.wait_for_timeout(350)
    assert page.locator('[data-header]').evaluate('el=>el.getBoundingClientRect().top>=47')
   page.goto(BASE+'/entrar/',wait_until='networkidle');contained(page)
   page.screenshot(path=str(OUT/f'login-{width}.png'),full_page=True)
   if width==390:
    page.get_by_role('button',name='Entrar na minha conta').click()
    expect(page.locator('.error').first).to_be_visible();contained(page)
    page.get_by_label('Senha',exact=True).fill('teste')
    page.get_by_role('button',name='Mostrar senha').click();expect(page.get_by_label('Senha',exact=True)).to_have_attribute('type','text')
    page.get_by_role('button',name='Ocultar senha').click()
   login(page)
   expect(page.locator('[data-install-status]')).not_to_be_visible()
   expect(page.locator('[data-install-dialog]')).not_to_be_visible()
   for route in ['/app/','/app/perfil/','/app/agenda/','/app/mensalidades/']:
    page.goto(BASE+route,wait_until='networkidle');contained(page)
    assert page.evaluate('localStorage.getItem("tf_pwa_install_v1")!==null')
    expect(page.locator('[data-install-status]')).not_to_be_visible()
    if width in [390,1366]:page.screenshot(path=str(OUT/f'{route.strip("/").replace("/","-")}-{width}.png'),full_page=True)
   if width<1025:
    page.locator('.app-tabbar').get_by_role('link',name='Perfil',exact=True).click()
    expect(page).to_have_url(BASE+'/app/perfil/');contained(page)
    if width==390:
     field=page.locator('input[name="nickname"]');field.focus()
     page.evaluate("Object.defineProperty(visualViewport,'height',{configurable:true,get:()=>350});visualViewport.dispatchEvent(new Event('resize'))")
     expect(page.locator('.app-tabbar')).not_to_be_visible()
     page.evaluate("delete visualViewport.height;document.activeElement.blur();visualViewport.dispatchEvent(new Event('resize'))")
     expect(page.locator('.app-tabbar')).to_be_visible()
    page.get_by_role('button',name='Abrir menu',exact=True).click()
    expect(page.locator('[data-sidebar]')).to_have_class(__import__('re').compile('is-open'))
    expect(page.locator('[data-sidebar]')).to_have_css('transform','none')
    page.screenshot(path=str(OUT/f'menu-{width}.png'))
    page.get_by_role('button',name='Sair da conta',exact=True).click();expect(page).to_have_url(BASE+'/')
    login(page);expect(page.locator('[data-install-status]')).not_to_be_visible()
   assert not errors,errors
   report.append({'width':width,'height':height,'standalone_and_safe_area_simulated':True,'capsule':True,'login_student_navigation_logout':True})
   ctx.close()
  # Normal browser: installation event and manual shortcut survive navigation/reload.
  for mechanism in ['event','manual']:
   ctx=browser.new_context(viewport={'width':390,'height':844},service_workers='block')
   page=ctx.new_page();page.set_default_timeout(30000);page.set_default_navigation_timeout(60000)
   login(page)
   page.locator('[data-install-status] [data-install-open]').click()
   expect(page.locator('[data-install-dialog]')).to_be_visible()
   if mechanism=='event':page.evaluate("dispatchEvent(new Event('appinstalled'))")
   else:page.locator('[data-install-remember]').click()
   expect(page.locator('[data-install-dialog]')).not_to_be_visible();expect(page.locator('[data-install-status]')).not_to_be_visible()
   page.locator('.app-tabbar').get_by_role('link',name='Agenda',exact=True).click();expect(page).to_have_url(BASE+'/app/agenda/')
   page.reload(wait_until='networkidle');expect(page.locator('[data-install-status]')).not_to_be_visible()
   expect(page.locator('[data-install-dialog]')).not_to_be_visible()
   report.append({'installed':mechanism,'reload_and_htmx':True});ctx.close()
  ctx=browser.new_context(service_workers='block');page=ctx.new_page();page.set_default_timeout(30000)
  page.goto(BASE+'/',wait_until='networkidle')
  def changed_styles(route):
   response=route.fetch()
   route.fulfill(response=response,body=response.text().replace('css/refinements.css','css/refinements-qa.css'))
  page.route(BASE+'/produtos/',changed_styles)
  page.route('**/static/css/refinements-qa.css',lambda route:route.fulfill(status=200,content_type='text/css',body=(ROOT/'static/css/refinements.css').read_text(encoding='utf-8')))
  page.locator('.site-nav').get_by_role('link',name='Produtos',exact=True).click()
  expect(page).to_have_url(BASE+'/produtos/')
  expect(page.locator('head link[href$="refinements-qa.css"]')).to_have_count(1)
  expect(page.locator('head link[href$="/refinements.css"]')).to_have_count(0)
  report.append({'htmx_updates_styles_after_deploy':True});ctx.close()
  browser.close()
finally:
 User.objects.filter(pk=uid).delete()
 (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
