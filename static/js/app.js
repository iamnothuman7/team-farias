(() => {
  "use strict";

  const ua = navigator.userAgent || "";
  const isIOS =
    /iphone|ipad|ipod/i.test(ua) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const isAndroid = /android/i.test(ua);
  const isInApp = /(Instagram|FBAN|FBAV|FB_IAB|Line\/|WhatsApp)/i.test(ua);
  const isStandalone =
    window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  const platform = isIOS ? "ios" : isAndroid ? "android" : "desktop";

  const state = {
    installDeferred: null,
    autoTimer: null,
    observer: null,
    htmxBound: false,
    loading: 0,
    booted: false,
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  /* ----------------------------------------------------------- helpers */
  function setLoading(delta) {
    state.loading = Math.max(0, state.loading + delta);
    document.documentElement.classList.toggle("is-loading", state.loading > 0);
  }

  function toast(message) {
    const wrapper = $("[data-toasts]");
    if (!wrapper) return;
    const node = document.createElement("div");
    node.className = "toast toast--error";
    node.innerHTML =
      '<span class="toast__icon"><svg class="icon"><use href="#i-alert"></use></svg></span><p></p>';
    node.querySelector("p").textContent = message;
    wrapper.appendChild(node);
    setTimeout(() => node.remove(), 7000);
  }

  function closeSiteNav() {
    const toggle = $("[data-nav-toggle]");
    const nav = $("[data-mobile-nav]");
    if (!toggle || !nav) return;
    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-label", "Abrir menu");
    nav.hidden = true;
    nav.classList.remove("is-open");
    $("[data-header]")?.classList.remove("is-open");
    document.body.style.overflow = "";
  }

  function closeOverlays() {
    closeSiteNav();
  }

  /* ----------------------------------------------------------- PWA */
  const INSTALL_KEY = "tf_install_prompt_until";
  const markInstallDismissed = () =>
    window.localStorage.setItem(INSTALL_KEY, String(Date.now() + 7 * 24 * 60 * 60 * 1000));
  const installDismissed = () => Number(window.localStorage.getItem(INSTALL_KEY) || 0) > Date.now();
  const hideInstallCta = () => $$(".install-cta").forEach((el) => (el.hidden = true));

  function openInstallDialog() {
    const dialog = $("[data-install-dialog]");
    if (!dialog) return;
    dialog.querySelectorAll("[data-install-panel]").forEach((panel) => {
      panel.hidden = panel.dataset.installPanel !== platform;
    });
    const inApp = dialog.querySelector("[data-install-inapp]");
    if (inApp) inApp.hidden = !isInApp;
    const insecure = dialog.querySelector("[data-install-insecure]");
    if (insecure) insecure.hidden = window.isSecureContext || isIOS;
    dialog.showModal();
  }

  function bindInstall() {
    if (isStandalone) {
      document.documentElement.classList.add("is-standalone");
      hideInstallCta();
    }

    $$("[data-install-open]").forEach((button) => {
      if (button.dataset.bound) return;
      button.dataset.bound = "1";
      button.addEventListener("click", openInstallDialog);
    });

    $$("[data-install-later]").forEach((button) => {
      if (button.dataset.bound) return;
      button.dataset.bound = "1";
      button.addEventListener("click", () => {
        markInstallDismissed();
        $("[data-install-dialog]")?.close();
      });
    });

    $$("[data-copy-link]").forEach((button) => {
      if (button.dataset.bound) return;
      button.dataset.bound = "1";
      button.addEventListener("click", async () => {
        const label = button.querySelector("[data-copy-link-label]");
        const original = label?.textContent;
        try {
          await navigator.clipboard.writeText(`${window.location.origin}/entrar/`);
          if (label) label.textContent = "Link copiado!";
        } catch {
          window.prompt("Copie o link para abrir no celular:", `${window.location.origin}/entrar/`);
        }
        setTimeout(() => {
          if (label && original) label.textContent = original;
        }, 2200);
      });
    });

    const dialog = $("[data-install-dialog]");
    if (dialog && !dialog.dataset.bound) {
      dialog.dataset.bound = "1";
      dialog.querySelectorAll("[data-dialog-close]").forEach((button) => {
        button.addEventListener("click", () => dialog.close());
      });
      dialog.addEventListener("click", (event) => {
        if (event.target === dialog) dialog.close();
      });
      dialog.addEventListener("close", markInstallDismissed);
    }

    $$("[data-install-native]").forEach((button) => {
      if (state.installDeferred) button.hidden = false;
      if (button.dataset.bound) return;
      button.dataset.bound = "1";
      button.addEventListener("click", async () => {
        if (!state.installDeferred) {
          openInstallDialog();
          return;
        }
        state.installDeferred.prompt();
        const choice = await state.installDeferred.userChoice;
        if (choice.outcome === "accepted") hideInstallCta();
        state.installDeferred = null;
        $$("[data-install-native]").forEach((b) => (b.hidden = true));
        $("[data-install-dialog]")?.close();
      });
    });
  }

  function maybeAutoInstall() {
    if (!document.querySelector("[data-install-auto]")) return;
    if (isStandalone || installDismissed()) return;
    clearTimeout(state.autoTimer);
    state.autoTimer = window.setTimeout(() => {
      const dialog = $("[data-install-dialog]");
      if (dialog && !dialog.open) openInstallDialog();
    }, 1400);
  }

  /* ----------------------------------------------------------- page bindings */
  function bindHeader() {
    const header = $("[data-header]");
    if (!header) return;
    const toggle = () => header.classList.toggle("is-scrolled", window.scrollY > 8);
    toggle();
    window.addEventListener("scroll", toggle, { passive: true, once: false });
    // remove duplicação: guarda a função no elemento atual
    header.dataset.scrollBound = "1";
  }

  function bindSiteNav() {
    const toggle = $("[data-nav-toggle]");
    const nav = $("[data-mobile-nav]");
    if (!toggle || !nav || toggle.dataset.bound) return;
    toggle.dataset.bound = "1";

    const setOpen = (open) => {
      toggle.setAttribute("aria-expanded", String(open));
      toggle.setAttribute("aria-label", open ? "Fechar menu" : "Abrir menu");
      nav.hidden = !open;
      nav.classList.toggle("is-open", open);
      $("[data-header]")?.classList.toggle("is-open", open);
      document.body.style.overflow = open ? "hidden" : "";
    };

    toggle.addEventListener("click", () =>
      setOpen(toggle.getAttribute("aria-expanded") !== "true")
    );
    nav.querySelectorAll("a").forEach((link) => link.addEventListener("click", () => setOpen(false)));
  }

  function bindToasts() {
    $$("[data-toast]").forEach((toastNode) => {
      if (toastNode.dataset.bound) return;
      toastNode.dataset.bound = "1";
      const dismiss = () => {
        toastNode.classList.add("is-hiding");
        setTimeout(() => toastNode.remove(), 320);
      };
      toastNode.querySelector("[data-toast-close]")?.addEventListener("click", dismiss);
      setTimeout(dismiss, 6500);
    });
  }

  function bindReveal() {
    const targets = $$(
      "[data-reveal], .pillar, .team-card, .group-card, .plan-card, .news-card, .step"
    ).filter((el) => !el.dataset.revealBound);
    if (!targets.length || !("IntersectionObserver" in window)) return;

    document.documentElement.classList.add("js-reveal");
    if (state.observer) state.observer.disconnect();
    state.observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          const el = entry.target;
          const delay = Number(el.dataset.revealDelay || 0);
          setTimeout(() => el.classList.add("is-visible"), delay);
          state.observer.unobserve(el);
        });
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.08 }
    );
    targets.forEach((el, index) => {
      el.dataset.revealBound = "1";
      el.setAttribute("data-reveal", "");
      el.dataset.revealDelay = String((index % 4) * 70);
      state.observer.observe(el);
    });
  }

  function bindCopy() {
    $$("[data-copy]").forEach((button) => {
      if (button.dataset.bound) return;
      button.dataset.bound = "1";
      button.addEventListener("click", async () => {
        const value = button.getAttribute("data-copy");
        const label = button.querySelector("[data-copy-label]");
        const original = label?.textContent;
        try {
          await navigator.clipboard.writeText(value);
          if (label) label.textContent = "Copiado!";
          button.classList.add("is-copied");
        } catch {
          window.prompt("Copie o valor:", value);
        }
        setTimeout(() => {
          if (label && original) label.textContent = original;
          button.classList.remove("is-copied");
        }, 2200);
      });
    });
  }

  function bindAttendance() {
    const form = $("[data-attendance]");
    if (!form || form.dataset.bound) return;
    form.dataset.bound = "1";

    form.querySelectorAll("[data-mark-all]").forEach((button) => {
      button.addEventListener("click", () => {
        const status = button.dataset.markAll;
        form.querySelectorAll('input[type="radio"]').forEach((radio) => {
          if (radio.value === status) radio.checked = true;
        });
      });
    });

    const counter = form.querySelector("[data-present-count]");
    const updateCount = () => {
      if (!counter) return;
      counter.textContent = String(form.querySelectorAll('input[value="presente"]:checked').length);
    };
    form.addEventListener("change", updateCount);
    updateCount();
  }

  function bindPasswordToggles() {
    $$("[data-password-toggle]").forEach((button) => {
      if (button.dataset.bound) return;
      button.dataset.bound = "1";
      const input = document.getElementById(button.getAttribute("data-password-toggle"));
      if (!input) return;
      button.addEventListener("click", () => {
        const show = input.type === "password";
        input.type = show ? "text" : "password";
        button.setAttribute("aria-label", show ? "Ocultar senha" : "Mostrar senha");
      });
    });
  }

  function disableBoostOnHashLinks() {
    $$('a[href*="#"]').forEach((anchor) => {
      const href = anchor.getAttribute("href");
      if (!href || href.startsWith("#") || href.includes("#")) {
        anchor.setAttribute("hx-boost", "false");
      }
    });
    $$('a[href^="/admin"], a[download], a[target="_blank"]').forEach((anchor) => {
      anchor.setAttribute("hx-boost", "false");
    });
  }

  function duplicateMarquee() {
    const track = $(".marquee__track");
    if (track && !track.dataset.cloned) {
      track.dataset.cloned = "1";
      track.innerHTML += track.innerHTML;
    }
  }

  function initPage({ initial = false } = {}) {
    bindSiteNav();
    bindToasts();
    bindReveal();
    bindCopy();
    bindAttendance();
    bindPasswordToggles();
    bindInstall();
    disableBoostOnHashLinks();
    duplicateMarquee();
    if (initial) maybeAutoInstall();
  }

  /* ----------------------------------------------------------- HTMX */
  function syncHead(xhr) {
    try {
      const doc = new DOMParser().parseFromString(xhr.responseText, "text/html");
      const robots = doc.head.querySelector('meta[name="robots"]');
      document.querySelectorAll('meta[name="robots"]').forEach((node) => node.remove());
      if (robots) document.head.appendChild(robots.cloneNode(true));

      const description = doc.head.querySelector('meta[name="description"]');
      const currentDescription = document.head.querySelector('meta[name="description"]');
      if (description && currentDescription) {
        currentDescription.setAttribute("content", description.getAttribute("content") || "");
      }

      const canonical = doc.head.querySelector('link[rel="canonical"]');
      const currentCanonical = document.head.querySelector('link[rel="canonical"]');
      currentCanonical?.remove();
      if (canonical) document.head.appendChild(canonical.cloneNode(true));
      for (const selector of ['meta[property^="og:"]', 'meta[name^="twitter:"]']) {
        document.head.querySelectorAll(selector).forEach((node) => node.remove());
        doc.head.querySelectorAll(selector).forEach((node) => document.head.appendChild(node.cloneNode(true)));
      }
    } catch {
      /* resposta não HTML */
    }
  }

  function syncBodyClass(xhr) {
    try {
      const doc = new DOMParser().parseFromString(xhr.responseText, "text/html");
      if (doc.body) {
        document.body.className = doc.body.className;
        document.body.style.cssText = doc.body.style.cssText;
      }
      const historyAttr = doc.body?.getAttribute("hx-history");
      if (historyAttr !== null) document.body.setAttribute("hx-history", historyAttr);
      else document.body.removeAttribute("hx-history");
    } catch {
      /* resposta não HTML */
    }
  }

  function bootHtmx() {
    if (!window.htmx || state.htmxBound) return;
    state.htmxBound = true;

    htmx.config.allowScriptTags = false;
    htmx.config.globalViewTransitions = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    htmx.config.historyCacheSize = 0;
    htmx.config.historyRestoreAsHxRequest = false;
    try { localStorage.removeItem("htmx-history-cache"); } catch {}

    const body = document.body;
    window.addEventListener("popstate", () => {
      // Uma resposta atrasada não deve sobrescrever a página escolhida no histórico.
      document.querySelectorAll(".htmx-request").forEach((element) => htmx.trigger(element, "htmx:abort"));
    });

    body.addEventListener("htmx:beforeRequest", (event) => {
      setLoading(1);
      closeOverlays();
      clearTimeout(state.autoTimer);
      const form = event.detail.elt?.closest?.("form");
      if (form) {
        form.querySelectorAll('button[type="submit"]').forEach((button) => (button.disabled = true));
      }
    });

    body.addEventListener("htmx:afterRequest", (event) => {
      setLoading(-1);
      const form = event.detail.elt?.closest?.("form");
      if (form) {
        form.querySelectorAll('button[type="submit"]').forEach((button) => (button.disabled = false));
      }
    });

    body.addEventListener("htmx:beforeSwap", (event) => {
      if (event.detail.shouldSwap || [403, 404].includes(event.detail.xhr.status)) {
        syncBodyClass(event.detail.xhr);
        syncHead(event.detail.xhr);
      }
      const status = event.detail.xhr.status;
      if (status === 403 || status === 404) {
        event.detail.shouldSwap = true;
        event.detail.isError = false;
      }
    });

    body.addEventListener("htmx:afterSwap", (event) => {
      initPage();
      if (event.detail.requestConfig?.boosted) {
        window.scrollTo({ top: 0, left: 0, behavior: "instant" });
      }
    });

    body.addEventListener("htmx:historyCacheMissLoad", (event) => {
      syncBodyClass(event.detail.xhr);
      syncHead(event.detail.xhr);
    });
    body.addEventListener("htmx:historyRestore", () => initPage());

    body.addEventListener("htmx:responseError", () => {
      toast("Não foi possível concluir. Verifique a conexão e tente novamente.");
    });

    body.addEventListener("htmx:sendError", () => {
      toast("Sem conexão. Seus campos continuam aqui; tente novamente quando a internet voltar.");
    });
  }

  /* ----------------------------------------------------------- boot */
  function boot() {
    if (state.booted) return;
    state.booted = true;

    const header = $("[data-header]");
    if (header) {
      const onScroll = () => header.classList.toggle("is-scrolled", window.scrollY > 8);
      onScroll();
      window.addEventListener("scroll", onScroll, { passive: true });
    }

    // confirmação de ações (captura antes do htmx)
    document.addEventListener(
      "submit",
      (event) => {
        const form = event.target.closest("form[data-confirm]");
        if (!form) return;
        if (!window.confirm(form.getAttribute("data-confirm"))) {
          event.preventDefault();
          event.stopImmediatePropagation();
        }
      },
      true
    );

    // Esc fecha menu/drawer
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeOverlays();
    });

    window.addEventListener("beforeinstallprompt", (event) => {
      event.preventDefault();
      state.installDeferred = event;
      $$("[data-install-native]").forEach((button) => (button.hidden = false));
    });

    window.addEventListener("appinstalled", () => {
      hideInstallCta();
      $$("[data-install-native]").forEach((button) => (button.hidden = true));
      $("[data-install-dialog]")?.close();
      const wrapper = $("[data-toasts]");
      if (wrapper) {
        const node = document.createElement("div");
        node.className = "toast toast--success";
        node.innerHTML =
          '<span class="toast__icon"><svg class="icon"><use href="#i-check"></use></svg></span>' +
          "<p>Team Farias instalado. Procure o ícone na tela inicial.</p>";
        wrapper.appendChild(node);
        setTimeout(() => node.remove(), 6000);
      }
    });

    if ("serviceWorker" in navigator && window.isSecureContext) {
      window.addEventListener("load", () => {
        navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {});
      });
    }

    initPage({ initial: true });
    bootHtmx();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
