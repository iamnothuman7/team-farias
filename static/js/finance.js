(() => {
  'use strict';
  if (window.__teamFariasFinanceBound) return;
  window.__teamFariasFinanceBound = true;

  function initFinance() {
    document.querySelectorAll('[data-finance-form]').forEach((form) => {
      if (form.dataset.financeBound) return;
      form.dataset.financeBound = '1';
      const status = form.querySelector('[name="status"]');
      const settlement = form.querySelector('[data-finance-settlement]');
      const updateStatus = () => {
        if (!settlement) return;
        const settled = status?.value === 'settled';
        settlement.hidden = !settled;
        settlement.querySelectorAll('input,select').forEach((field) => {
          field.disabled = !settled;
          field.required = settled;
        });
      };
      status?.addEventListener('change', updateStatus);
      updateStatus();

      const kind = form.querySelector('[name="kind"]');
      const category = form.querySelector('[name="category"]');
      if (!category) return;
      const choices = Array.from(category.options).map((option) => option.cloneNode(true));
      const caption = document.createElement('p');
      caption.className = 'selection-caption';
      caption.id = `${category.id}-selection`;
      category.insertAdjacentElement('afterend', caption);
      category.setAttribute('aria-describedby', `${category.getAttribute('aria-describedby') || ''} ${caption.id}`.trim());
      const updateCaption = () => {
        caption.textContent = category.selectedOptions[0]?.textContent.trim() || '';
        caption.hidden = !category.value;
      };
      const updateKind = () => {
        // Data attributes are rendered from the allowed server-side category queryset.
        if (!choices.some((option) => option.dataset.kind)) return;
        const selected = category.value;
        category.replaceChildren(...choices.filter((option) => !option.value || !option.dataset.kind || option.dataset.kind === kind?.value).map((option) => option.cloneNode(true)));
        category.value = selected;
        if (category.selectedIndex < 0) category.selectedIndex = 0;
        updateCaption();
      };
      category.addEventListener('change', updateCaption);
      kind?.addEventListener('change', updateKind);
      updateKind();
      updateCaption();
    });

    document.querySelectorAll('[data-finance-dialog]').forEach((dialog) => {
      if (dialog.dataset.financeBound) return;
      dialog.dataset.financeBound = '1';
      dialog.querySelectorAll('[data-finance-dialog-close]').forEach((button) => button.addEventListener('click', () => dialog.close()));
      dialog.addEventListener('click', (event) => {
        if (event.target !== dialog) return;
        const rect = dialog.getBoundingClientRect();
        if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
      });
      if (dialog.hasAttribute('data-finance-dialog-auto')) dialog.showModal();
    });
    document.querySelectorAll('[data-finance-dialog-open]').forEach((button) => {
      if (button.dataset.financeBound) return;
      button.dataset.financeBound = '1';
      button.addEventListener('click', () => {
        const dialog = document.getElementById(button.dataset.financeDialogOpen);
        if (dialog?.matches('[data-finance-dialog]') && !dialog.open) dialog.showModal();
      });
    });
  }

  document.addEventListener('htmx:afterSwap', initFinance);
  document.addEventListener('htmx:historyRestore', initFinance);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initFinance);
  else initFinance();
})();
