// Small, field-local shortcuts. Preserve the cursor/selection when clicking.
(() => {
    function install() {
        for (const id of ['qwen_edit_instruction', 'fibo_edit_result_description']) {
            const block = gradioApp().querySelector('#' + id);
            const field = block?.querySelector('textarea');
            const heading = block?.querySelector('[data-testid="block-info"]');
            if (!field || !heading || heading.querySelector('.qe-prompt-tokens')) continue;
            heading.classList.add('qe-prompt-heading');
            const buttons = document.createElement('span');
            buttons.className = 'qe-prompt-tokens';
            for (const number of [1, 2, 3]) {
                const token = `<image_${number}>`, button = document.createElement('button');
                button.type = 'button'; button.textContent = token;
                button.title = `Insert ${token} at the cursor`;
                button.setAttribute('aria-label', `Insert ${token}`);
                button.addEventListener('pointerdown', event => event.preventDefault());
                button.addEventListener('click', event => {
                    event.preventDefault(); event.stopPropagation();
                    if (field.disabled || field.readOnly) return;
                    const start = field.selectionStart, end = field.selectionEnd;
                    field.focus({preventScroll: true});
                    field.setRangeText(token, start, end, 'end');
                    updateInput(field);
                });
                buttons.appendChild(button);
            }
            heading.appendChild(buttons);
        }
    }
    onUiUpdate(install);
})();
