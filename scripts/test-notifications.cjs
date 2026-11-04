const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const code = fs.readFileSync('static/js/notifications.js','utf8');

function setup(options={}) {
  const handlers={},calls=[];
  const button={textContent:'',disabled:false,hidden:false,addEventListener:(event,fn)=>{handlers[event]=fn;}};
  const status={textContent:''};
  const root={dataset:{enabled:options.enabled?'true':'false',configUrl:'/config',subscriptionUrl:'/subscription'},isConnected:true,
    querySelector:selector=>selector==='[data-push-toggle]'?button:selector==='[data-push-status]'?status:{value:'test-csrf'}};
  const events={};
  let subscription=options.subscribed?makeSubscription():null;
  function makeSubscription(){return {endpoint:'https://fcm.googleapis.com/device',toJSON(){return {endpoint:this.endpoint,keys:{p256dh:'test',auth:'test'}};},async unsubscribe(){calls.push('unsubscribe');subscription=null;return true;}};}
  const registration={pushManager:{async getSubscription(){return subscription;},async subscribe(){calls.push('subscribe');subscription=makeSubscription();return subscription;}}};
  const notification={permission:options.permission||'granted',async requestPermission(){calls.push('permission');return options.grant||'denied';}};
  const document={readyState:'complete',querySelector:()=>root,addEventListener:(name,fn)=>events[name]=fn};
  const navigator={serviceWorker:{async getRegistration(){return registration;},async register(){return registration;},ready:Promise.resolve(registration)}};
  const window={isSecureContext:true,Notification:notification,PushManager:{}};
  if(options.unsupported) delete window.PushManager;
  const fetch=async(url,config)=>{
    calls.push({url,config});
    if(url==='/config') return {ok:true,json:async()=>({configured:options.configured!==false,publicKey:'AQID'})};
    return {ok:!options.failSave,json:async()=>options.failSave?{error:'Falha ao salvar'}:{enabled:true}};
  };
  vm.runInNewContext(code,{window,navigator,document,Notification:notification,fetch,Uint8Array,atob:x=>Buffer.from(x,'base64').toString('binary'),setTimeout:()=>0});
  return {button,status,root,events,calls,async ready(){await Promise.resolve();await Promise.resolve();},async click(){await handlers.click();}};
}
test('unsupported browser explains fallback without prompting',async()=>{
  const env=setup({unsupported:true});await env.ready();assert.equal(env.button.hidden,true);assert.match(env.status.textContent,/Tela de Início/);assert.equal(env.calls.length,0);
});
test('denied permission does not request repeatedly',async()=>{
  const env=setup({permission:'denied'});await env.ready();assert.equal(env.button.disabled,true);assert.match(env.status.textContent,/bloqueadas/);
});
test('activation requires server acknowledgement and sends CSRF',async()=>{
  const env=setup();await env.ready();await env.click();await env.ready();assert.equal(env.root.dataset.enabled,'true');assert.equal(env.button.textContent,'Desativar notificações');
  const post=env.calls.find(c=>c.url==='/subscription');assert.equal(post.config.headers['X-CSRFToken'],'test-csrf');assert.equal(post.config.credentials,'same-origin');
});
test('manual permission refusal never subscribes',async()=>{
  const env=setup({permission:'default'});await env.ready();await env.click();assert.ok(!env.calls.includes('subscribe'));assert.equal(env.root.dataset.enabled,'false');
});
test('failed server save unsubscribes and never reports active',async()=>{
  const env=setup({failSave:true});await env.ready();await env.click();assert.ok(env.calls.includes('unsubscribe'));assert.equal(env.root.dataset.enabled,'false');assert.match(env.status.textContent,/Falha ao salvar/);
});
test('disable removes server binding and browser subscription',async()=>{
  const env=setup({subscribed:true,enabled:true});await env.ready();await env.click();assert.equal(env.root.dataset.enabled,'false');const post=env.calls.find(c=>c.url==='/subscription');assert.equal(JSON.parse(post.config.body).action,'remove');assert.ok(env.calls.includes('unsubscribe'));
});
test('missing server configuration leaves a useful message',async()=>{
  const env=setup({configured:false});await env.ready();await env.click();assert.equal(env.root.dataset.enabled,'false');assert.match(env.status.textContent,/preparando/);assert.ok(!env.calls.includes('subscribe'));
});
test('HTMX refresh preserves enabled state and action',async()=>{
  const env=setup({subscribed:true,enabled:true});await env.ready();await env.events['htmx:afterSwap']();assert.equal(env.button.textContent,'Desativar notificações');
});
