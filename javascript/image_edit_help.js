// Move detailed help out of the layout without removing Gradio-managed content.
(() => {
    const extras = {
        image_edit_output_size_enabled: () => text('image_edit_output_hint'),
        qwen_edit_quality: () => text('qwen_edit_preset_summary'),
        qwen_edit_area_mode: () => 'Standard follows your instruction. Camera angle changes the viewpoint. Expression transfer uses the first additional reference for expression only.\n\n' + text('image_edit_camera_help') + '\n\n' + text('image_edit_mask_help'),
        image_edit_fibo_shift_mode: () => text('image_edit_shift_hint'),
        image_edit_fibo_rope: () => text('image_edit_rope_hint'),
        image_edit_qwen_shift_mode: () => text('image_edit_qwen_shift_hint'),
        image_edit_qwen_rope: () => text('image_edit_qwen_rope_hint'),
    };
    function text(id) { return document.getElementById(id)?.textContent.trim() || ''; }
    let active, popup;
    function close() { if (popup) popup.hidden = true; active?.removeAttribute('aria-describedby'); active = null; }
    function show(button, content) {
        if (!popup) {
            popup = document.createElement('div'); popup.id = 'image_edit_help_popup';
            popup.setAttribute('role', 'tooltip'); document.body.append(popup);
        }
        active?.removeAttribute('aria-describedby'); active = button;
        popup.textContent = content(); popup.hidden = false;
        button.setAttribute('aria-describedby', popup.id);
        const r = button.getBoundingClientRect(), p = popup.getBoundingClientRect();
        popup.style.left = Math.max(8, Math.min(r.left, innerWidth - p.width - 8)) + 'px';
        popup.style.top = (r.bottom + p.height + 10 < innerHeight ? r.bottom + 6 : Math.max(8, r.top - p.height - 6)) + 'px';
    }
    function attach(host, content, label) {
        if (!host || host.querySelector('.qe-help-button')) return;
        const button = document.createElement('button');
        button.type = 'button'; button.className = 'qe-help-button'; button.textContent = '?';
        button.setAttribute('aria-label', label + ' help');
        button.addEventListener('click', event => { event.preventDefault(); event.stopPropagation(); show(button, content); });
        button.addEventListener('mouseenter', () => show(button, content));
        button.addEventListener('focus', () => show(button, content));
        button.addEventListener('mouseleave', () => { if (document.activeElement !== button) close(); });
        button.addEventListener('blur', close);
        host.append(button);
    }
    function install() {
        const workspace = document.getElementById('qwen_edit_workspace');
        if (!workspace) return;
        workspace.querySelectorAll('[data-testid="block-info"].has-info').forEach(label => {
            const info = label.nextElementSibling;
            if (!info || info.classList.contains('wrap') || info.classList.contains('qe-help-button')) return;
            attach(label, () => info.textContent.trim(), label.firstChild?.textContent || 'Setting');
            info.classList.add('qe-help-detail');
        });
        for (const [id, content] of Object.entries(extras)) {
            const component = document.getElementById(id);
            attach(component?.querySelector('[data-testid="block-info"]') || component?.querySelector('label'), content,
                component?.querySelector('[data-testid="block-info"]')?.firstChild?.textContent || component?.querySelector('label span')?.textContent || 'Setting');
        }
        attach(document.getElementById('image_edit_import_help'),
            () => 'Crop / outpaint: positive edges extend; negative edges crop. No changes = normal edit.\n\nTxt2img: selected image first, then newest saved → older with each press. Empty gallery starts at newest. New selection resets.\n\nIIB: open its lightbox, switch here, then import that image only.\n\nRandom: a random saved txt2img image.\n\nSaved imports include subfolders. Newest means last modified. All imports keep embedded metadata for Get prompt from metadata.',
            'Crop and image imports');
        workspace.classList.add('qe-help-enabled');
    }
    document.addEventListener('keydown', event => { if (event.key === 'Escape') close(); });
    document.addEventListener('click', event => { if (!event.target.closest('.qe-help-button')) close(); });
    document.addEventListener('scroll', close, true);
    if (typeof onUiUpdate === 'function') onUiUpdate(install);
})();
