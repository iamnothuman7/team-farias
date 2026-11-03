(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const state = { globalBound: false };

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
