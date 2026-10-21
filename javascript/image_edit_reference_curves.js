// Per-reference tone controls. Never replace the Gradio upload or its file URL.
(() => {
    const slots = new Map();
    function sync() {
        if (!window.createImageEditCurves) return;
        const app = gradioApp();
        for (const slot of [2, 3]) {
            const root = app.querySelector(`.qe-reference-editor[data-reference-slot="${slot}"]`);
            const upload = app.querySelector(`#image_edit_reference${slot}`);
            if (!root || !upload) continue;
            const picture = upload.querySelector('img:not(.qe-reference-preview)'), url = picture?.currentSrc || picture?.src || "";
            let state = slots.get(slot);
            if (state?.root === root && state.picture === picture && state.url === url) continue;
            const open = state?.root === root && !root.querySelector('.qe-curves-panel').hidden;
            state?.controller?.destroy(); state?.preview?.remove();
            state = {root, picture, url}; slots.set(slot, state);
            const button = root.querySelector('[data-action="curves"]'), panel = root.querySelector('.qe-curves-panel');
            const note = root.querySelector('.qe-reference-note');
            button.disabled = !url; button.textContent = open && url ? "Close edit" : "Edit";
            panel.hidden = !(open && url); button.setAttribute('aria-expanded', String(!panel.hidden));
            button.setAttribute('aria-pressed', String(!panel.hidden));
            note.textContent = url ? "Original kept · adjustments apply to generation" : "Load a reference to adjust its tones.";
            if (!url) { panel.innerHTML = ""; button.onclick = null; continue; }
            const preview = document.createElement('canvas'); preview.className = 'qe-reference-preview'; preview.hidden = true;
            const parent = picture.parentElement;
            parent.classList.add('qe-reference-image-stage'); parent.appendChild(preview); state.preview = preview;
            state.controller = window.createImageEditCurves(root, picture, preview, {
                selectEdited() {}, layoutChanged() { button.textContent = panel.hidden ? "Edit" : "Close edit"; },
                changed(value) { note.textContent = value ? "Adjusted for generation · original kept" : "Original kept · adjustments apply to generation"; }
            }, {reference: true});
            state.controller.open(url, url);
            button.onclick = () => state.controller.toggle();
        }
    }
    // Submit the current LUTs directly, including the last drag before Generate.
    // The server checks the upload hash so another image cannot inherit old LUTs.
    window.imageEditReferencePayloads = () => {
        sync();
        return [2, 3].map(slot => slots.get(slot)?.controller?.payload() || "");
    };
    onUiUpdate(sync);
    document.addEventListener('load', event => {
        if (event.target.matches?.('#image_edit_reference2 img, #image_edit_reference3 img')) sync();
    }, true);
})();
