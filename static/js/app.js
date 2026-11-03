(() => {
  "use strict";

  /* ----------------------------------------------------------- header */
  const header = document.querySelector("[data-header]");
  if (header) {
    const onScroll = () => header.classList.toggle("is-scrolled", window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  /* ----------------------------------------------------------- mobile nav */
  const navToggle = document.querySelector("[data-nav-toggle]");
  const mobileNav = document.querySelector("[data-mobile-nav]");
  if (navToggle && mobileNav) {
    const setOpen = (open) => {
      navToggle.setAttribute("aria-expanded", String(open));
      navToggle.setAttribute("aria-label", open ? "Fechar menu" : "Abrir menu");
      mobileNav.hidden = !open;
      mobileNav.classList.toggle("is-open", open);
      header?.classList.toggle("is-open", open);
      document.body.style.overflow = open ? "hidden" : "";
    };
    navToggle.addEventListener("click", () =>
      setOpen(navToggle.getAttribute("aria-expanded") !== "true")
    );
    mobileNav.querySelectorAll("a").forEach((link) => link.addEventListener("click", () => setOpen(false)));
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && navToggle.getAttribute("aria-expanded") === "true") setOpen(false);
    });
  }

  /* ----------------------------------------------------------- toasts */
  document.querySelectorAll("[data-toast]").forEach((toast) => {
    const dismiss = () => {
      toast.classList.add("is-hiding");
      setTimeout(() => toast.remove(), 320);
    };
    toast.querySelector("[data-toast-close]")?.addEventListener("click", dismiss);
    setTimeout(dismiss, 6500);
  });

  /* ----------------------------------------------------------- reveal on scroll */
  const revealTargets = document.querySelectorAll(
    "[data-reveal], .pillar, .team-card, .group-card, .plan-card, .news-card, .step"
  );
  if (revealTargets.length && "IntersectionObserver" in window) {
    document.documentElement.classList.add("js-reveal");
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry, i) => {
          if (!entry.isIntersecting) return;
          const el = entry.target;
          const delay = Number(el.dataset.revealDelay || 0);
          setTimeout(() => el.classList.add("is-visible"), delay);
          observer.unobserve(el);
        });
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.08 }
    );
    revealTargets.forEach((el, index) => {
      el.setAttribute("data-reveal", "");
      el.dataset.revealDelay = String((index % 4) * 70);
      observer.observe(el);
    });
  }

  /* ----------------------------------------------------------- auto submit filters */
  document.querySelectorAll("[data-autosubmit]").forEach((field) => {
    field.addEventListener("change", () => field.form?.requestSubmit());
  });

  /* ----------------------------------------------------------- copy to clipboard */
  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      const value = button.getAttribute("data-copy");
      const label = button.querySelector("[data-copy-label]");
      const original = label?.textContent;
      try {
        await navigator.clipboard.writeText(value);
        if (label) label.textContent = "Copiado!";
        button.classList.add("is-copied");
      } catch {
        window.prompt("Copie a chave Pix:", value);
      }
      setTimeout(() => {
        if (label && original) label.textContent = original;
        button.classList.remove("is-copied");
      }, 2200);
    });
  });

  /* ----------------------------------------------------------- attendance shortcuts */
  const attendanceForm = document.querySelector("[data-attendance]");
  if (attendanceForm) {
    attendanceForm.querySelectorAll("[data-mark-all]").forEach((button) => {
      button.addEventListener("click", () => {
        const status = button.dataset.markAll;
        attendanceForm.querySelectorAll('input[type="radio"]').forEach((radio) => {
          if (radio.value === status) radio.checked = true;
        });
      });
    });
    const counter = attendanceForm.querySelector("[data-present-count]");
    const updateCount = () => {
      if (!counter) return;
      const total = attendanceForm.querySelectorAll('input[value="presente"]:checked').length;
      counter.textContent = String(total);
    };
    attendanceForm.addEventListener("change", updateCount);
    updateCount();
  }

  /* ----------------------------------------------------------- confirm actions */
  document.querySelectorAll("[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.getAttribute("data-confirm"))) event.preventDefault();
    });
  });

  /* ----------------------------------------------------------- password visibility */
  document.querySelectorAll("[data-password-toggle]").forEach((button) => {
    const input = document.getElementById(button.getAttribute("data-password-toggle"));
    if (!input) return;
    button.addEventListener("click", () => {
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      button.setAttribute("aria-label", show ? "Ocultar senha" : "Mostrar senha");
    });
  });

  /* ----------------------------------------------------------- service worker */
  if ("serviceWorker" in navigator && window.isSecureContext) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {});
    });
  }

  /* ----------------------------------------------------------- PWA / instalação */
  const installDialog = document.querySelector("[data-install-dialog]");
  const ua = navigator.userAgent || "";
  const isIOS =
    /iphone|ipad|ipod/i.test(ua) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const isAndroid = /android/i.test(ua);
  const isInApp = /(Instagram|FBAN|FBAV|FB_IAB|Line\/|WhatsApp)/i.test(ua);
  const isStandalone =
    window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;

  if (isStandalone) {
    document.documentElement.classList.add("is-standalone");
    document.querySelectorAll(".install-cta").forEach((el) => (el.hidden = true));
  }

  const platform = isIOS ? "ios" : isAndroid ? "android" : "desktop";
  const hideInstallCta = () =>
    document.querySelectorAll(".install-cta").forEach((el) => (el.hidden = true));

  const INSTALL_KEY = "tf_install_prompt_until";
  const dismissedUntil = Number(window.localStorage.getItem(INSTALL_KEY) || 0);
  const markInstallDismissed = () =>
    window.localStorage.setItem(INSTALL_KEY, String(Date.now() + 7 * 24 * 60 * 60 * 1000));

  const openInstallDialog = () => {
    if (!installDialog) return;
    installDialog.querySelectorAll("[data-install-panel]").forEach((panel) => {
      panel.hidden = panel.dataset.installPanel !== platform;
    });
    const inApp = installDialog.querySelector("[data-install-inapp]");
    if (inApp) inApp.hidden = !isInApp;
    const insecure = installDialog.querySelector("[data-install-insecure]");
    if (insecure) insecure.hidden = window.isSecureContext || isIOS;
    installDialog.showModal();
  };

  document.querySelectorAll("[data-install-open]").forEach((button) => {
    button.addEventListener("click", openInstallDialog);
  });

  document.querySelectorAll("[data-install-later]").forEach((button) => {
    button.addEventListener("click", () => {
      markInstallDismissed();
      installDialog?.close();
    });
  });

  if (installDialog) {
    installDialog.querySelectorAll("[data-dialog-close]").forEach((button) => {
      button.addEventListener("click", () => installDialog.close());
    });
    installDialog.addEventListener("click", (event) => {
      if (event.target === installDialog) installDialog.close();
    });
    installDialog.addEventListener("close", markInstallDismissed);
  }

  // Convite automático ao abrir o site (uma vez a cada 7 dias)
  const autoInstallTrigger = document.querySelector("[data-install-auto]");
  if (autoInstallTrigger && !isStandalone && Date.now() > dismissedUntil) {
    window.setTimeout(() => {
      if (!installDialog?.open) openInstallDialog();
    }, 1400);
  }

  document.querySelectorAll("[data-copy-link]").forEach((button) => {
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

  let deferredPrompt = null;
  const nativeButtons = document.querySelectorAll("[data-install-native]");

  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    deferredPrompt = event;
    nativeButtons.forEach((button) => (button.hidden = false));
  });

  nativeButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      if (!deferredPrompt) {
        openInstallDialog();
        return;
      }
      deferredPrompt.prompt();
      const choice = await deferredPrompt.userChoice;
      if (choice.outcome === "accepted") hideInstallCta();
      deferredPrompt = null;
      nativeButtons.forEach((b) => (b.hidden = true));
      if (installDialog?.open) installDialog.close();
    });
  });

  window.addEventListener("appinstalled", () => {
    hideInstallCta();
    nativeButtons.forEach((b) => (b.hidden = true));
    if (installDialog?.open) installDialog.close();
    const wrapper = document.querySelector("[data-toasts]");
    if (wrapper) {
      const toast = document.createElement("div");
      toast.className = "toast toast--success";
      toast.innerHTML =
        '<span class="toast__icon"><svg class="icon"><use href="#i-check"></use></svg></span>' +
        "<p>Team Farias instalado. Procure o ícone na tela inicial.</p>";
      wrapper.appendChild(toast);
      setTimeout(() => toast.remove(), 6000);
    }
  });

  /* ----------------------------------------------------------- marquee duplicate */
  const track = document.querySelector(".marquee__track");
  if (track && !track.dataset.cloned) {
    track.dataset.cloned = "true";
    track.innerHTML += track.innerHTML;
  }
})();
