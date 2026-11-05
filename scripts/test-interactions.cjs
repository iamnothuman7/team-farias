const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function setup() {
  const documentEvents={}, windowEvents={}, bodyEvents={};
  class Control extends EventTarget { textContent=''; focus(){this.focused=true;} click(){this.dispatchEvent(new Event('click'));} }
  const accept=new Control(), cancel=new Control(), message=new Control();
  const dialog=new Control();dialog.open=false;
  dialog.querySelector=s=>s==='[data-confirm-accept]'?accept:message;
  dialog.querySelectorAll=()=>[cancel];
  dialog.showModal=()=>{dialog.open=true;};
  dialog.close=()=>{dialog.open=false;dialog.dispatchEvent(new Event('close'));};
  const newHeader=()=>({classList:{active:false,toggle(name,on){this.active=on;}}});
  let header=newHeader();
  const document={readyState:'complete',querySelector:s=>s==='[data-header]'?header:null,querySelectorAll:()=>[],getElementById:()=>dialog,addEventListener:(name,fn)=>{documentEvents[name]=fn;},body:{addEventListener:(name,fn)=>{bodyEvents[name]=fn;}}};
  const window={scrollY:0,addEventListener:(name,fn)=>{windowEvents[name]=fn;}};
  vm.runInNewContext(fs.readFileSync('static/js/app.js','utf8'),{document,window,navigator:{},WeakSet,setTimeout,console});
  const forms=[];
  function form(){
    const target={isConnected:true,submitted:0,getAttribute:()=>'<Aluno> — Reabrir?',closest(){return this;},querySelector:()=>({value:'reopen'})};
    const submitter={form:target};
    target.requestSubmit=button=>{assert.equal(button,submitter);const e=submit(target,submitter);if(!e.prevented)target.submitted++;};
    forms.push(target);return {target,submitter};
  }
  function submit(target,submitter){const e={target,submitter,prevented:false,preventDefault(){this.prevented=true;},stopImmediatePropagation(){this.stopped=true;}};documentEvents.submit(e);return e;}
  return {dialog,accept,cancel,message,window,windowEvents,bodyEvents,form,submit,get header(){return header;},replaceHeader(){header=newHeader();}};
}

test('reopening waits for explicit confirmation and submits once',()=>{
  const env=setup(), f=env.form();const event=env.submit(f.target,f.submitter);
  assert.equal(event.prevented,true);assert.equal(event.stopped,true);assert.equal(f.target.submitted,0);
  assert.equal(env.dialog.open,true);assert.equal(env.accept.textContent,'Confirmar reabertura');
  assert.equal(env.message.textContent,'<Aluno> — Reabrir?');
  env.accept.click();assert.equal(f.target.submitted,1);assert.equal(env.dialog.open,false);
  env.accept.click();assert.equal(f.target.submitted,1);
});
test('cancel and Escape do not reopen a charge',()=>{
  const env=setup(), f=env.form();env.submit(f.target,f.submitter);env.cancel.click();assert.equal(f.target.submitted,0);
  env.submit(f.target,f.submitter);env.dialog.close();assert.equal(f.target.submitted,0);
});
test('new page and another invoice do not reuse the previous confirmation',()=>{
  const env=setup(), a=env.form(), b=env.form();env.submit(a.target,a.submitter);env.cancel.click();
  env.submit(b.target,b.submitter);env.accept.click();assert.equal(a.target.submitted,0);assert.equal(b.target.submitted,1);
});
test('a form removed by navigation cannot submit from an old dialog',()=>{
  const env=setup(), f=env.form();env.submit(f.target,f.submitter);f.target.isConnected=false;env.accept.click();assert.equal(f.target.submitted,0);
});
test('capsule activates on scroll and resets at the top',()=>{
  const env=setup();assert.equal(env.header.classList.active,false);env.window.scrollY=100;env.windowEvents.scroll();assert.equal(env.header.classList.active,true);
  env.window.scrollY=0;env.windowEvents.scroll();assert.equal(env.header.classList.active,false);
});
test('capsule targets the new header after HTMX navigation',()=>{
  const env=setup();const old=env.header;env.replaceHeader();env.window.scrollY=80;env.windowEvents.scroll();assert.equal(env.header.classList.active,true);assert.equal(old.classList.active,false);
});
