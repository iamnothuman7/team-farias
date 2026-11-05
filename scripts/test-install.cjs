// Testes do estado da PWA, com eventos simulados; não instala apps no computador.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/js/install.js'), 'utf8');
const KEY = 'tf_pwa_install_v1';
const tick = () => new Promise(resolve => setImmediate(resolve));

function setup({store = new Map(), mode = false, related, blocked = false, auto = false} = {}) {
  const events = {}, docEvents = {}, timers = [];
  function element() {
    return {dataset: {}, childNodes: [], hidden: false, textContent: '', handlers: {},
      setAttribute() {}, appendChild() {}, querySelector() { return this.label ||= element(); },
      addEventListener(type, callback) { (this.handlers[type] ||= []).push(callback); },
      async click() { for (const fn of this.handlers.click || []) await fn({target: this}); }
    };
  }
  const later = element();
  const open = element(), native = element(), remember = element(), reset = element(), bar = element(), title = element(), feedback = element();
  const dialog = {...element(), open: false, showModal() { this.open = true; }, close() { this.open = false; }};
  const selectors = {
    '[data-install-later], [data-install-dialog] [data-dialog-close]': [later],
    '[data-install-open]': [open], '[data-install-open], [data-install-native]': [open, native],
    '[data-install-native]': [native], '[data-install-remember]': [remember], '[data-install-reset]': [reset],
    '[data-install-status]': [bar], '[data-install-status-title]': [title], '[data-install-feedback]': [feedback],
    '[data-install-remember], [data-install-manual-hint]': [remember]
  };
  const document = {readyState: 'complete', visibilityState: 'visible',
    documentElement: {classList: {toggle() {}}}, createElement: element,
    querySelectorAll: s => selectors[s] || [], querySelector: s => s === '[data-install-dialog]' ? dialog : s === '[data-install-auto]' && auto ? element() : null,
    addEventListener: (name, fn) => { docEvents[name] = fn; }
  };
  const storage = {getItem: k => {if(blocked) throw Error('denied'); return store.get(k) ?? null;},
    setItem: (k, v) => {if(blocked) throw Error('denied'); store.set(k,v);},
    removeItem: k => {if(blocked) throw Error('denied'); store.delete(k);}};
  const navigator = {userAgent: 'Chrome', getInstalledRelatedApps: related};
  const window = {isSecureContext: true, location: {origin: 'https://teamfarias.nabio.pro'},
    matchMedia: query => ({matches: mode && query.includes('standalone'), addEventListener() {}}),
    addEventListener: (name, fn) => {events[name] = fn;}};
  vm.runInNewContext(source, {window, document, navigator, localStorage: storage, sessionStorage: storage, URL, Date,
    setTimeout: fn => {timers.push(fn); return timers.length;}, clearTimeout() {}});
  return {setMode: value => {mode=value;}, setAuto: value => {auto=value;}, later, window, events, docEvents, store, open, native, remember, reset, bar, title, feedback, timers, dialog,
    saved: () => store.has(KEY) ? JSON.parse(store.get(KEY)) : null};
}

test('oferece botão sem assumir instalação pela ausência de prompt', () => {
  const c = setup(); assert.equal(c.bar.hidden, false); assert.equal(c.open.label.textContent, 'Adicionar como app'); assert.equal(c.saved(), null);
});
test('aceitar prompt não confirma instalação; appinstalled confirma e persiste', async () => {
  const c = setup(); let prompts = 0;
  c.events.beforeinstallprompt({preventDefault() {}, async prompt(){prompts++;}, userChoice: Promise.resolve({outcome:'accepted'})});
  await c.open.click(); assert.equal(prompts,1); assert.equal(c.saved(),null); assert.notEqual(c.open.label.textContent,'App instalado');
  c.events.appinstalled(); assert.equal(c.saved().status,'confirmed'); assert.equal(c.open.label.textContent,'App instalado');
  const next = setup({store:c.store}); assert.equal(next.open.label.textContent,'App instalado');
});
test('cancelamento não grava sucesso e prompt é consumido uma vez', async () => {
  const c=setup(); let count=0;
  c.events.beforeinstallprompt({preventDefault(){},async prompt(){count++;},userChoice:Promise.resolve({outcome:'dismissed'})});
  await c.open.click(); await c.open.click(); assert.equal(count,1); assert.equal(c.saved(),null); assert.equal(c.dialog.open,true);
});
test('confirmação manual é distinta e respeitada nas próximas visitas', async () => {
  const c=setup(); await c.remember.click(); assert.equal(c.saved().status,'manual'); assert.equal(c.open.label.textContent,'Atalho informado');
  const next=setup({store:c.store}); next.events.beforeinstallprompt({preventDefault(){}});
  assert.equal(next.open.label.textContent,'Atalho informado'); await next.reset.click(); assert.equal(next.saved(),null);
});
test('modo standalone confirma e remove convite redundante', () => {
  const c=setup({mode:true}); assert.equal(c.saved().source,'standalone'); assert.equal(c.bar.hidden,true);
});
test('API só reconhece a identidade do próprio Team Farias', async () => {
  const wrong=setup({related:async()=>[{platform:'webapp',id:'https://other.example/app/'}]}); await tick(); assert.equal(wrong.saved(),null);
  const right=setup({related:async()=>[{platform:'webapp',id:'https://teamfarias.nabio.pro/app/'}]}); await tick(); assert.equal(right.saved().source,'related');
});
test('armazenamento bloqueado e API indisponível não quebram a interface', async () => {
  const c=setup({blocked:true,related:async()=>{throw Error('unsupported');}}); await tick(); await c.remember.click();
  assert.equal(c.open.label.textContent,'Atalho informado'); assert.equal(c.saved(),null);
});
test('novo prompt corrige registro confirmado depois de desinstalação', () => {
  const c=setup(); c.events.appinstalled(); c.events.beforeinstallprompt({preventDefault(){}});
  assert.equal(c.saved(),null); assert.equal(c.open.label.textContent,'Adicionar como app');
});
test('resposta antiga da API não sobrescreve evento mais recente', async () => {
  let resolve; const c=setup({related:()=>new Promise(r=>{resolve=r;})});
  c.events.beforeinstallprompt({preventDefault(){}}); resolve([{platform:'webapp',id:'/app/'}]); await tick(); assert.equal(c.saved(),null);
});
test('HTMX não duplica handlers e sincronização de abas atualiza o rótulo', () => {
  const c=setup(); c.docEvents['htmx:afterSwap'](); c.docEvents['htmx:afterSwap'](); assert.equal(c.open.handlers.click.length,1);
  c.store.set(KEY,JSON.stringify({status:'confirmed',source:'event'})); c.events.storage({key:KEY}); assert.equal(c.open.label.textContent,'App instalado');
});
test('instalação sem confirmação sai de pendente sem inventar sucesso', async () => {
  const c=setup(); c.events.beforeinstallprompt({preventDefault(){},async prompt(){},userChoice:Promise.resolve({outcome:'accepted'})});
  await c.open.click(); c.timers.forEach(fn=>fn()); assert.equal(c.saved(),null); assert.equal(c.open.label.textContent,'Adicionar como app');
});


test('instalação persistida oculta card e não abre convite ao retornar', () => {
  const first=setup();first.events.appinstalled();
  const next=setup({store:first.store,auto:true});next.timers.forEach(fn=>fn());
  assert.equal(next.bar.hidden,true);assert.equal(next.dialog.open,false);
  next.docEvents['htmx:afterSwap']();assert.equal(next.bar.hidden,true);
});

test('atalho manual também remove o card e evita novo convite', async () => {
  const c=setup({auto:true});await c.remember.click();c.timers.forEach(fn=>fn());
  assert.equal(c.bar.hidden,true);assert.equal(c.dialog.open,false);
  const next=setup({store:c.store,auto:true});next.timers.forEach(fn=>fn());assert.equal(next.dialog.open,false);
});

test('detecção lenta não abre convite enquanto verifica instalação', async () => {
  let resolve;const c=setup({auto:true,related:()=>new Promise(r=>resolve=r)});
  c.timers.forEach(fn=>fn());assert.equal(c.dialog.open,false);
  resolve([{platform:'webapp',id:'/app/'}]);await tick();assert.equal(c.bar.hidden,true);
});

test('detecção tardia e outra aba fecham convite já aberto', async () => {
  let resolve;const c=setup({related:()=>new Promise(r=>resolve=r)});
  await c.open.click();assert.equal(c.dialog.open,true);
  resolve([{platform:'webapp',id:'/app/'}]);await tick();assert.equal(c.dialog.open,false);
  const other=setup();await other.open.click();other.store.set(KEY,JSON.stringify({status:'confirmed'}));
  other.events.storage({key:KEY});assert.equal(other.dialog.open,false);assert.equal(other.bar.hidden,true);
});

test('abrir pelo ícone fecha a janela e remove o card mesmo sem armazenamento', async () => {
  const c=setup({blocked:true});await c.open.click();assert.equal(c.dialog.open,true);
  c.setMode(true);await c.events.focus();assert.equal(c.dialog.open,false);assert.equal(c.bar.hidden,true);
  await c.open.click();assert.equal(c.dialog.open,false);
});

test('fechar antes do timer e navegar para outra tela impedem reabertura automática', async () => {
  const c=setup({auto:true});await c.open.click();await c.later.click();c.timers.forEach(fn=>fn());assert.equal(c.dialog.open,false);
  const next=setup({auto:true});next.setAuto(false);next.timers.forEach(fn=>fn());assert.equal(next.dialog.open,false);
});
