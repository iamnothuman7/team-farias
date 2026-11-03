(() => {
  "use strict";

  const sidebar = document.querySelector("[data-sidebar]");
  const toggle = document.querySelector("[data-sidebar-toggle]");
  const backdrop = document.querySelector("[data-sidebar-backdrop]");

  const setSidebar = (open) => {
    if (!sidebar) return;
    sidebar.classList.toggle("is-open", open);
    toggle?.setAttribute("aria-expanded", String(open));
    document.body.classList.toggle("has-drawer", open);
  };

  toggle?.addEventListener("click", () => setSidebar(!sidebar.classList.contains("is-open")));
  backdrop?.addEventListener("click", () => setSidebar(false));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setSidebar(false);
  });

  /* Confirmação de ações destrutivas */
  document.querySelectorAll("[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.getAttribute("data-confirm"))) event.preventDefault();
    });
  });

  /* Filtros que submetem sozinhos */
  document.querySelectorAll("[data-autosubmit]").forEach((field) => {
    field.addEventListener("change", () => field.form?.requestSubmit());
  });

  /* Marcar todos os presentes / limpar */
  const attendance = document.querySelector("[data-attendance]");
  if (attendance) {
    attendance.querySelectorAll("[data-mark-all]").forEach((button) => {
      button.addEventListener("click", () => {
        const status = button.dataset.markAll;
        attendance.querySelectorAll('input[type="radio"]').forEach((radio) => {
          if (radio.value === status) radio.checked = true;
        });
        attendance.dispatchEvent(new Event("change"));
      });
    });

    const counter = attendance.querySelector("[data-present-count]");
    const update = () => {
      if (!counter) return;
      counter.textContent = String(attendance.querySelectorAll('input[value="presente"]:checked').length);
    };
    attendance.addEventListener("change", update);
    update();
  }

  /* Alternar painéis (lançamento individual / coletivo) */
  document.querySelectorAll("[data-tabs]").forEach((tabs) => {
    const buttons = tabs.querySelectorAll("[data-tab]");
    const panels = document.querySelectorAll("[data-tab-panel]");
    buttons.forEach((button) => {
      button.addEventListener("click", () => {
        buttons.forEach((b) => b.classList.toggle("is-active", b === button));
        panels.forEach((panel) => {
          panel.hidden = panel.dataset.tabPanel !== button.dataset.tab;
        });
      });
    });
  });

  /* Copiar chave Pix */
  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      const label = button.querySelector("[data-copy-label]");
      const original = label?.textContent;
      try {
        await navigator.clipboard.writeText(button.dataset.copy);
        if (label) label.textContent = "Copiado!";
      } catch {
        window.prompt("Copie a chave Pix:", button.dataset.copy);
      }
      setTimeout(() => {
        if (label && original) label.textContent = original;
      }, 2000);
    });
  });

  /* Modal de pagamento */
  document.querySelectorAll("[data-dialog-open]").forEach((button) => {
    button.addEventListener("click", () => {
      const dialog = document.getElementById(button.dataset.dialogOpen);
      if (!dialog) return;
      const invoice = button.dataset.invoice;
      const student = button.dataset.student;
      const amount = button.dataset.amount;
      const input = dialog.querySelector('input[name="invoice"]');
      if (input) input.value = invoice;
      dialog.querySelector("[data-dialog-student]")?.replaceChildren(document.createTextNode(student || ""));
      dialog.querySelector("[data-dialog-amount]")?.replaceChildren(document.createTextNode(amount || ""));
      dialog.showModal();
    });
  });

  document.querySelectorAll("dialog[data-dialog]").forEach((dialog) => {
    dialog.querySelectorAll("[data-dialog-close]").forEach((button) =>
      button.addEventListener("click", () => dialog.close())
    );
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
  });
})();
