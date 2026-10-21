// Per-reference tone controls. Never replace the Gradio upload or its file URL.
(() => {
    const slots = new Map();
    let activeSlot = null;
    function updateWorkspace() {
        const workspace = gradioApp().querySelector('#image_edit_reference_workspace');
        if (!workspace) return;
        const hidden = activeSlot === null;
        if (workspace.hidden !== hidden) workspace.hidden = hidden;
        const source = workspace.querySelector('.qe-reference-source img');
        // The canvas keeps clean source bytes separately from painting/outpaint guides.
        const url = window.qwenEditPaintCanvas?.img || '';
        if (source.getAttribute('src') !== (url || null)) {
            if (url) source.setAttribute('src', url);
            else source.removeAttribute('src');
        }
        if (source.hidden !== !url) source.hidden = !url;
        const empty = workspace.querySelector('.qe-reference-source p');
        if (empty.hidden !== !!url) empty.hidden = !!url;
    }
    function toggleSlot(slot) {
        activeSlot = activeSlot === slot ? null : slot;
        for (const [number, state] of slots) {
            if (state.controller && state.panel.hidden !== (number !== activeSlot)) state.controller.toggle();
        }
        updateWorkspace();
    }
    function sync() {
        if (!window.createImageEditCurves) return;
        const app = gradioApp();
        for (const slot of [2, 3]) {
            const root = app.querySelector(`.qe-reference-editor[data-reference-slot="${slot}"]`);
            const upload = app.querySelector(`#image_edit_reference${slot}`);
            const panel = app.querySelector(`#image_edit_reference_panel${slot}`);
            if (!root || !upload || !panel) continue;
            const picture = upload.querySelector('img:not(.qe-reference-preview)'), url = picture?.currentSrc || picture?.src || "";
            let state = slots.get(slot);
            if (state?.root === root && state.panel === panel && state.picture === picture && state.url === url) continue;
            const open = activeSlot === slot && !!url;
            state?.controller?.destroy(); state?.preview?.remove();
            state = {root, picture, url, panel}; slots.set(slot, state);
            const button = root.querySelector('[data-action="curves"]');
            const note = root.querySelector('.qe-reference-note');
            button.disabled = !url; button.textContent = open && url ? "Close edit" : "Edit";
            panel.hidden = !(open && url); button.setAttribute('aria-expanded', String(!panel.hidden));
            button.setAttribute('aria-pressed', String(!panel.hidden));
            note.textContent = url ? "Original kept · adjustments apply to generation" : "Load a reference to adjust its tones.";
            if (!url) {
                panel.innerHTML = ""; button.onclick = null;
                if (activeSlot === slot) activeSlot = null;
                continue;
            }
            const preview = document.createElement('canvas'); preview.className = 'qe-reference-preview'; preview.hidden = true;
            const parent = picture.parentElement;
            parent.classList.add('qe-reference-image-stage'); parent.appendChild(preview); state.preview = preview;
            state.controller = window.createImageEditCurves(root, picture, preview, {
                selectEdited() {}, layoutChanged() { button.textContent = panel.hidden ? "Edit" : "Close edit"; },
                changed(value) { note.textContent = value ? "Adjusted for generation · original kept" : "Original kept · adjustments apply to generation"; }
            }, {reference: true, panel});
            panel.querySelector('.qe-curves-title strong').textContent = `Image ${slot} · Curves & levels`;
            state.controller.open(url, url);
            button.onclick = () => toggleSlot(slot);
        }
        updateWorkspace();
    }
    // Submit the current LUTs directly, including the last drag before Generate.
    // The server checks the upload hash so another image cannot inherit old LUTs.
    window.imageEditReferencePayloads = () => {
        sync();
        return [2, 3].map(slot => slots.get(slot)?.controller?.payload() || "");
    };
    onUiUpdate(sync);
    document.addEventListener('load', event => {
        if (event.target.matches?.('#image_edit_reference2 img, #image_edit_reference3 img, #qwen_edit_source img')) sync();
    }, true);
})();
