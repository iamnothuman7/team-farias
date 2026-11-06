(() => {
  'use strict';
  if (window.__teamManagement) return;
  window.__teamManagement = true;
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-add-schedule]');
    if (!button) return;
    const editor = button.closest('[data-schedule-editor]');
    const total = editor.closest('form').querySelector(`[name="${editor.dataset.prefix}-TOTAL_FORMS"]`);
    const count = Number(total.value);
    if (count >= 50) {
      editor.querySelector('[data-schedule-status]').textContent = 'Limite de 50 horários por turma.';
      return;
    }
    const fragment = editor.querySelector('template').content.cloneNode(true);
    fragment.querySelectorAll('*').forEach(element => {
      for (const attribute of [...element.attributes]) {
        if (attribute.value.includes('__prefix__')) element.setAttribute(attribute.name, attribute.value.replaceAll('__prefix__', String(count)));
      }
    });
    const field = fragment.querySelector('select, input:not([type="hidden"])');
    editor.querySelector('[data-schedule-list]').append(fragment);
    document.dispatchEvent(new Event('management:scheduleAdded'));
    total.value = String(count + 1);
    editor.querySelector('[data-schedule-status]').textContent = 'Novo horário adicionado. Preencha os campos e salve a turma.';
    field?.focus();
  });
})();
