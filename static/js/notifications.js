(() => {
  'use strict';
  let running = false;
  const panel = () => document.querySelector('[data-push-settings]');
  async function api(root, data) {
    const response = await fetch(root.dataset.subscriptionUrl, {
      method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json','X-CSRFToken':root.querySelector('[name=csrfmiddlewaretoken]').value}, body:JSON.stringify(data)
    });
    if(response.redirected || (response.headers && !response.headers.get('content-type')?.includes('application/json'))) throw new Error('Entre novamente na sua conta para gerenciar as notificações.');
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Não foi possível salvar. Tente novamente.');
    return result;
  }
  function keyBytes(key) {
    const raw = atob(key.replace(/-/g,'+').replace(/_/g,'/') + '='.repeat((4-key.length%4)%4));
    return Uint8Array.from(raw, c=>c.charCodeAt(0));
  }
  function supported() { return window.isSecureContext && 'Notification' in window && 'PushManager' in window && 'serviceWorker' in navigator; }
  async function refresh() {
    const root = panel(); if (!root) return;
    const button=root.querySelector('[data-push-toggle]'), status=root.querySelector('[data-push-status]');
    if (!supported()) { button.hidden=true; status.textContent='Para receber avisos, use um navegador compatível. No iPhone, adicione o app à Tela de Início e abra pelo ícone. Os recados continuam disponíveis abaixo.'; return; }
    button.hidden=false;
    if (Notification.permission==='denied') { button.disabled=true; status.textContent='Notificações bloqueadas. Permita os avisos nas configurações deste site no navegador e volte aqui.'; return; }
    button.disabled=running;
    if (!root.dataset.bound) { root.dataset.bound='1'; button.addEventListener('click',()=>toggle(root)); }
    try {
      const registration=await navigator.serviceWorker.getRegistration('/');
      const subscription=await registration?.pushManager.getSubscription();
      if (!root.isConnected) return;
      // Server binding is explicit; browser permission alone is not an account subscription.
      const enabled=subscription && root.dataset.enabled==='true';
      button.textContent=enabled ? 'Desativar notificações' : 'Ativar notificações';
      if(enabled) status.textContent='Notificações ativadas neste aparelho. Os próximos comunicados da equipe poderão chegar mesmo com o app fechado.';
    } catch (_) { status.textContent='Não foi possível verificar este aparelho. Toque para tentar ativar.'; }
  }
  async function toggle(root) {
    if (running) return; running=true;
    const button=root.querySelector('[data-push-toggle]'), status=root.querySelector('[data-push-status]');
    button.disabled=true;
    try {
      // Request directly from the click to preserve the user gesture on iOS.
      if (Notification.permission!=='granted' && await Notification.requestPermission()!=='granted') {
        status.textContent='Permissão não concedida. Você pode continuar lendo os comunicados aqui.'; return;
      }
      const registration=await navigator.serviceWorker.register('/sw.js',{scope:'/'});
      const ready=await Promise.race([navigator.serviceWorker.ready,new Promise((_,reject)=>setTimeout(()=>reject(new Error('O app ainda está iniciando. Tente novamente.')),12000))]);
      let subscription=await ready.pushManager.getSubscription();
      if (subscription && root.dataset.enabled==='true') {
        await api(root,{action:'remove',endpoint:subscription.endpoint});
        await subscription.unsubscribe(); root.dataset.enabled='false';
        status.textContent='Notificações desativadas neste aparelho.';
      } else {
        const response=await fetch(root.dataset.configUrl,{credentials:'same-origin'});
        if(!response.ok || response.redirected || (response.headers && !response.headers.get('content-type')?.includes('application/json'))) throw new Error('Entre novamente na sua conta para ativar.');
        const config=await response.json();
        if(!config.configured) throw new Error('A equipe está preparando as notificações. Os recados continuam disponíveis aqui.');
        if(!subscription) subscription=await ready.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:keyBytes(config.publicKey)});
        try { await api(root,subscription.toJSON()); }
        catch(error) { await subscription.unsubscribe(); throw error; }
        root.dataset.enabled='true'; status.textContent='Notificações ativadas neste aparelho. Você receberá os próximos comunicados publicados para alunos.';
      }
    } catch(error) { status.textContent=error.message || 'Não foi possível ativar. Confira sua conexão e tente novamente.'; }
    finally { running=false; button.disabled=false; refresh(); }
  }
  document.addEventListener('DOMContentLoaded',refresh);
  document.addEventListener('htmx:afterSwap',refresh);
  document.addEventListener('htmx:historyRestore',refresh);
  if(document.readyState!=='loading') refresh();
})();
