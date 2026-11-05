/* Estado de instalação por navegador. Não usa ausência de prompt como prova. */
(() => {
  "use strict";
  const KEY = "tf_pwa_install_v1";
  const ua = navigator.userAgent || "";
  const ios = /iphone|ipad|ipod/i.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const platform = ios ? "ios" : /android/i.test(ua) ? "android" : "desktop";
  const inApp = /(Instagram|FBAN|FBAV|FB_IAB|Line\/|WhatsApp)/i.test(ua);
  const $ = (s) => document.querySelector(s);
  const all = (s) => Array.from(document.querySelectorAll(s));
  const standalone = () => window.matchMedia("(display-mode: standalone)").matches || window.matchMedia("(display-mode: minimal-ui)").matches || navigator.standalone === true;
  let record = null;
  let deferred = null;
  let pending = false;
  let pendingTimer = null;
  let checking = false;
  let generation = 0;
  function readRecord() {
    try {
      const value = JSON.parse(localStorage.getItem(KEY));
      return value && ["confirmed", "manual"].includes(value.status) ? value : null;
    } catch { return null; }
  }
  function remember(status, source) {
    generation += 1;
    record = status ? { status, source, at: Date.now() } : null;
    try {
      if (record) localStorage.setItem(KEY, JSON.stringify(record));
      else localStorage.removeItem(KEY);
    } catch { /* A interface funciona também com armazenamento bloqueado. */ }
  }
  function setText(selector, text) { all(selector).forEach((el) => { el.textContent = text; }); }
  function render() {
    const inAppMode = standalone();
    const known = !!record;
    const confirmed = record?.status === "confirmed";
    const label = inAppMode ? "Você está no app" : confirmed ? "App instalado" : known ? "Atalho informado" : pending ? "Confirmar instalação" : "Adicionar como app";
    document.documentElement.classList.toggle("is-standalone", inAppMode);
    all("[data-install-status]").forEach((el) => { el.hidden = inAppMode; });
    all(".install-cta").forEach((el) => { el.hidden = inAppMode; });
    all("[data-install-open]").forEach((button) => {
      let text = button.querySelector("[data-install-label]");
      if (!text) {
        // Preserva o ícone e troca apenas o rótulo dos botões antigos.
        Array.from(button.childNodes).filter((n) => n.nodeType === 3).forEach((n) => n.remove());
        text = document.createElement("span");
        text.setAttribute("data-install-label", "");
        button.appendChild(text);
      }
      text.textContent = label;
      button.setAttribute("aria-label", label);
    });
    setText("[data-install-status-title]", confirmed ? "Seu app já está instalado." : known ? "Atalho lembrado neste navegador." : "Seu time, a um toque.");
    setText("[data-install-status-detail]", known ? "Abra pelo ícone na sua tela inicial." : "Adicione o app à sua tela inicial.");
    all("[data-install-panel]").forEach((el) => { el.hidden = known || (!!deferred && window.isSecureContext) || el.dataset.installPanel !== platform; });
    setText("#install-title", known ? "Seu time já está por perto." : "Seu time, sempre perto.");
    setText("#install-description", known ? "Abra pelo ícone na sua tela inicial." : "Treinos e novidades a um toque. Adicione à sua tela inicial.");
    all("[data-install-inapp]").forEach((el) => { el.hidden = !inApp; });
    all("[data-install-insecure]").forEach((el) => { el.hidden = window.isSecureContext; });
    all("[data-install-native]").forEach((el) => {
      el.hidden = !deferred || known || !window.isSecureContext;
      el.disabled = pending;
    });
    all("[data-install-remember], [data-install-manual-hint]").forEach((el) => { el.hidden = known || !!deferred || pending; });
    all("[data-install-reset]").forEach((el) => { el.hidden = !known; });
    all("[data-install-confirmed]").forEach((el) => {
      el.hidden = !known;
      el.textContent = confirmed ? "Instalação reconhecida neste navegador. Seu app está na tela inicial ou na lista de aplicativos." : "Atalho lembrado neste navegador. Abra pelo ícone para confirmar o modo app.";
    });
  }
  function openDialog() {
    render();
    const dialog = $("[data-install-dialog]");
    if (dialog && !dialog.open) dialog.showModal();
  }
  async function install() {
    if (!deferred || record || pending || !window.isSecureContext) { openDialog(); return; }
    const prompt = deferred;
    deferred = null;
    pending = true;
    render();
    try {
      await prompt.prompt();
      const choice = await prompt.userChoice;
      if (choice.outcome !== "accepted") pending = false;
      // A aceitação sozinha não confirma que a instalação terminou.
      if (!record && choice.outcome === "accepted") {
        setText("[data-install-feedback]", "Confirme a instalação na janela do navegador. O status será atualizado quando ele confirmar.");
        openDialog();
        pendingTimer = setTimeout(() => {
          if (record) return;
          pending = false;
          setText("[data-install-feedback]", "A instalação ainda não foi confirmada. Verifique o menu do navegador ou siga as instruções abaixo.");
          render();
        }, 20000);
      }
    } catch {
      pending = false;
      setText("[data-install-feedback]", "Não foi possível abrir a instalação. Use as instruções do seu navegador.");
      openDialog();
    }
    render();
  }
  function bind(selector, handler) {
    all(selector).forEach((el) => {
      if (el.dataset.installBound) return;
      el.dataset.installBound = "1";
      el.addEventListener("click", handler);
    });
  }
  function refresh() {
    bind("[data-install-open], [data-install-native]", install);
    bind("[data-install-later], [data-install-dialog] [data-dialog-close]", () => {
      try { sessionStorage.setItem("tf_pwa_prompt_dismissed", "1"); } catch {}
      $("[data-install-dialog]")?.close();
    });
    bind("[data-install-remember]", () => { remember("manual", "user"); pending = false; render(); $("[data-install-dialog]")?.close(); });
    bind("[data-install-reset]", () => { remember(null); pending = false; setText("[data-install-feedback]", ""); render(); });
    bind("[data-copy-link]", async () => {
      const url = `${window.location.origin}/entrar/`;
      try { await navigator.clipboard.writeText(url); setText("[data-copy-link-label]", "Link copiado!"); }
      catch { window.prompt("Copie o link:", url); }
    });
    const dialog = $("[data-install-dialog]");
    if (dialog && !dialog.dataset.installBound) {
      dialog.dataset.installBound = "1";
      dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
    }
    render();
  }
  async function checkInstalled() {
    if (standalone()) {
      remember("confirmed", "standalone"); pending = false; deferred = null; refresh(); return;
    }
    if (checking || typeof navigator.getInstalledRelatedApps !== "function") return;
    checking = true;
    const version = generation;
    try {
      const apps = await navigator.getInstalledRelatedApps();
      const id = new URL("/app/", window.location.origin).href;
      const manifest = new URL("/manifest.webmanifest", window.location.origin).href;
      const installed = apps.some((app) => app.platform === "webapp" && ((app.id && new URL(app.id, window.location.origin).href === id) || (app.url && new URL(app.url, window.location.origin).href === manifest)));
      if (version === generation && installed) { remember("confirmed", "related"); deferred = null; pending = false; }
      // [] não é prova universal de desinstalação. beforeinstallprompt corrige registros antigos.
    } catch { /* Sem suporte ou acesso negado: mantém somente o que foi confirmado. */ }
    finally { checking = false; refresh(); }
  }
  record = readRecord();
  window.TeamFariasInstall = { refresh, checkInstalled };
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    // Um atalho manual pode existir sem contar como instalação para o navegador.
    if (record?.status !== "manual") remember(null);
    deferred = event; pending = false; clearTimeout(pendingTimer); refresh();
  });
  window.addEventListener("appinstalled", () => {
    remember("confirmed", "event"); deferred = null; pending = false;
    clearTimeout(pendingTimer);
    setText("[data-install-feedback]", "Instalação confirmada pelo navegador."); refresh(); $("[data-install-dialog]")?.close();
  });
  window.addEventListener("storage", (event) => { if (event.key === KEY) { generation += 1; record = readRecord(); refresh(); } });
  window.addEventListener("pageshow", checkInstalled);
  window.addEventListener("focus", checkInstalled);
  window.matchMedia("(display-mode: standalone)").addEventListener?.("change", checkInstalled);
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") checkInstalled(); });
  document.addEventListener("htmx:afterSwap", refresh);
  function boot() {
    refresh(); checkInstalled();
    let dismissed = false;
    try { dismissed = sessionStorage.getItem("tf_pwa_prompt_dismissed") === "1"; } catch {}
    if ($("[data-install-auto]") && !dismissed) {
      setTimeout(() => { if (!record && !standalone()) openDialog(); }, 1400);
    }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
