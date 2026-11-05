(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const state = { globalBound: false };

  function updateKeyboard() {
    const viewport = window.visualViewport;
    document.documentElement.style.setProperty('--visual-height', `${Math.round(viewport?.height || window.innerHeight)}px`);
    document.documentElement.style.setProperty('--visual-top', `${Math.round(viewport?.offsetTop || 0)}px`);
    const active = document.activeElement;
    const editing = active?.matches('input:not([type=checkbox]):not([type=radio]):not([type=button]):not([type=submit]),textarea,[contenteditable=true]');
    const covered = window.visualViewport && window.innerHeight - window.visualViewport.height > 150;
    // Mantém o popup estável entre o toque no botão e o teclado recolher.
    const keyboard = covered && (editing || document.documentElement.classList.contains('has-keyboard'));
    document.documentElement.classList.toggle('has-keyboard', !!keyboard);
    if (keyboard && editing && active.closest('.management-dialog')) {
      requestAnimationFrame(() => {
        const body = active.closest('.dialog__body');
        if (!body || !active.isConnected) return;
        const field = (active.closest('.field') || active).getBoundingClientRect();
        const area = body.getBoundingClientRect();
        if (field.bottom > area.bottom) body.scrollTop += field.bottom - area.bottom + 12;
        else if (field.top < area.top) body.scrollTop -= area.top - field.top + 12;
      });
    }
  }
  window.visualViewport?.addEventListener('resize', updateKeyboard);
  window.visualViewport?.addEventListener('scroll', updateKeyboard);
  document.addEventListener('focusin', updateKeyboard);
  document.addEventListener('focusout', () => setTimeout(updateKeyboard, 0));

  function setSidebar(open) {
    const sidebar = $("[data-sidebar]");
    const toggle = $("[data-sidebar-toggle]");
    const backdrop = $("[data-sidebar-backdrop]");
    if (!sidebar) return;
    const mobile = window.matchMedia("(max-width: 1024px)").matches;
    open = mobile && open;
    const wasOpen = sidebar.classList.contains("is-open");
    sidebar.classList.toggle("is-open", open);
    sidebar.inert = mobile && !open;
    document.querySelector(".app-main")?.toggleAttribute("inert", open);
    document.querySelector(".app-tabbar")?.toggleAttribute("inert", open);
    if (open) sidebar.querySelector("[data-sidebar-close]")?.focus();
    else if (wasOpen) toggle?.focus();
    toggle?.setAttribute("aria-expanded", String(open));
    if (backdrop) backdrop.hidden = !open;
    document.body.classList.toggle("has-drawer", open);
  }

  function bindSidebar() {
    const toggle = $("[data-sidebar-toggle]");
    const backdrop = $("[data-sidebar-backdrop]");
    const sidebar = $("[data-sidebar]");
    if (!sidebar) return;
    setSidebar(false);

    if (toggle && !toggle.dataset.bound) {
      toggle.dataset.bound = "1";
      toggle.addEventListener("click", () => setSidebar(!sidebar.classList.contains("is-open")));
    }
    if (backdrop && !backdrop.dataset.bound) {
      backdrop.dataset.bound = "1";
      backdrop.addEventListener("click", () => setSidebar(false));
    }
    $$("[data-sidebar-close]").forEach((button) => {
      if (button.dataset.bound) return;
      button.dataset.bound = "1";
      button.addEventListener("click", () => setSidebar(false));
    });
    if (!state.globalBound) {
      state.globalBound = true;
      window.matchMedia("(max-width: 1024px)").addEventListener("change", () => setSidebar(false));
      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") setSidebar(false);
        const drawer = $("[data-sidebar].is-open");
        if (event.key === "Tab" && drawer) {
          const items = $$("a[href], button:not([disabled]), input:not([disabled])", drawer).filter((el) => el.getClientRects().length);
          const first = items[0], last = items[items.length - 1];
          if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
          else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
        }
      });
      document.body.addEventListener("htmx:beforeRequest", () => {
        setSidebar(false);
        document.body.classList.remove("has-drawer");
      });
    }
  }

  function bindTabs() {
    $$("[data-tabs]").forEach((tabs) => {
      if (tabs.dataset.bound) return;
      tabs.dataset.bound = "1";
      const buttons = $$("[data-tab]", tabs);
      const panels = $$("[data-tab-panel]");
      buttons.forEach((button) => {
        button.addEventListener("click", () => {
          buttons.forEach((b) => b.classList.toggle("is-active", b === button));
          panels.forEach((panel) => {
            panel.hidden = panel.dataset.tabPanel !== button.dataset.tab;
          });
        });
      });
    });
  }

  function bindPaymentDialog() {
    const dialog = document.getElementById("pay-dialog");
    if (!dialog || dialog.dataset.bound) return;
    dialog.dataset.bound = "1";

    $$("[data-dialog-open]").forEach((button) => {
      if (button.dataset.bound) return;
      button.dataset.bound = "1";
      button.addEventListener("click", () => {
        dialog.querySelector('form')?.reset();
        const input = dialog.querySelector('input[name="invoice"]');
        if (input) input.value = button.dataset.invoice || "";
        dialog.querySelector("[data-dialog-student]")?.replaceChildren(
          document.createTextNode(button.dataset.student || "")
        );
        dialog.querySelector("[data-dialog-amount]")?.replaceChildren(
          document.createTextNode(button.dataset.amount || "")
        );
        dialog.showModal();
      });
    });

    dialog.querySelectorAll("[data-dialog-close]").forEach((button) => {
      button.addEventListener("click", () => dialog.close());
    });
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
  }

  function initDashboard() {
    updateKeyboard();
    $$('.management-form select[name="class_group"], .management-form select[name="plan"], .management-form select[name="student"]').forEach((select) => {
      if (select.dataset.choiceBound || !select.id) return;
      select.dataset.choiceBound = '1';
      const caption = document.createElement('p');
      caption.id = `${select.id}-selection`;
      caption.className = 'selection-caption';
      select.insertAdjacentElement('afterend', caption);
      const describedBy = select.getAttribute('aria-describedby') || '';
      select.setAttribute('aria-describedby', `${describedBy} ${caption.id}`.trim());
      const update = () => {
        const text = select.selectedOptions[0]?.textContent.trim() || '';
        caption.textContent = text;
        caption.hidden = !select.value;
      };
      select.addEventListener('change', update);
      update();
    });
    $$(".table").forEach((table) => {
      if (table.closest('.billing-table')) return;
      const labels = $$("thead th", table).map((th) => th.textContent.trim());
      if (!labels.length) return;
      table.dataset.mobileCards = "true";
      $$("tbody tr", table).forEach((row) => {
        Array.from(row.cells).forEach((cell, i) => { cell.dataset.label = labels[i] || ""; });
      });
    });
    bindSidebar();
    bindTabs();
    bindPaymentDialog();
  }

  document.addEventListener("htmx:afterSwap", initDashboard);
  document.addEventListener("htmx:historyRestore", initDashboard);

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initDashboard);
  } else {
    initDashboard();
  }
})();
