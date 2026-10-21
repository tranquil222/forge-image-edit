// Link in the browser: server responses must never write an older companion edge.
((root) => {
    function linkedSize(value, width, height, axis) {
        value = Number(value);
        if (!Number.isFinite(value) || value < 32 || value > 4096 || width <= 0 || height <= 0) return null;
        const pair = axis === 'height' ? [Math.round(value * width / height), Math.round(value)]
            : [Math.round(value), Math.round(value * height / width)];
        return pair.every(edge => edge >= 32 && edge <= 4096) ? pair : null;
    }
    function canvasSize(width, height, enabled, edges = {}) {
        const values = ['left', 'right', 'top', 'bottom'].map(key => enabled ? Number(edges[key] || 0) : 0);
        const [left, right, top, bottom] = values;
        const size = [width + left + right, height + top + bottom];
        return [...size, ...values].every(Number.isInteger) && Math.min(...size) > 0 &&
            Math.max(0, -left) < Math.min(width, width + right) &&
            Math.max(0, -top) < Math.min(height, height + bottom) ? size : null;
    }
    const api = {linkedSize, canvasSize};
    if (typeof module !== 'undefined') module.exports = api;
    root.ImageEditOutputSize = api;
    if (typeof document === 'undefined') return;
    let syncing = false, lastAxis = 'width', previous = null, previousImage = null;
    const field = axis => document.querySelector(`#image_edit_output_${axis} input[type="number"]`);
    const checkbox = id => document.querySelector(`#image_edit_${id} input[type="checkbox"]`);
    function geometry(override = {}) {
        const canvas = root.qwenEditPaintCanvas;
        if (!canvas?.img) return null;
        const enabled = checkbox('canvas_enabled');
        const edges = Object.fromEntries(['left', 'right', 'top', 'bottom'].map(key =>
            [key, override[key] ?? document.querySelector(`#image_edit_canvas_${key} input[type="number"]`)?.value ?? 0]));
        return canvasSize(canvas.orgWidth, canvas.orgHeight, enabled?.checked && !enabled.disabled, edges);
    }
    function write(axis, value) {
        const input = field(axis);
        if (input && Number(input.value) !== value) {
            input.value = value;
            input.dispatchEvent(new Event('input', {bubbles: true}));
        }
    }
    function enable() {
        const input = checkbox('output_size_enabled');
        if (input && !input.checked && !input.disabled) input.click();
    }
    function refresh(override) {
        if (syncing) return;
        const size = geometry(override), img = root.qwenEditPaintCanvas?.img;
        if (!size) return;
        syncing = true;
        try {
            // Keep the selected scale as edges change, linking to the full planned canvas.
            if (previous && img === previousImage && size.some((v, i) => v !== previous[i])) {
                const scale = Number(field('width')?.value) / previous[0];
                const width = Math.max(Math.ceil(Math.max(32, 32 * size[0] / size[1])),
                    Math.min(Math.floor(Math.min(4096, 4096 * size[0] / size[1])), Math.round(size[0] * scale)));
                const pair = linkedSize(width, ...size, 'width');
                if (pair) { write('width', pair[0]); write('height', pair[1]); }
            }
            previous = size; previousImage = img;
            for (const [i, axis] of ['width', 'height'].entries()) {
                const ratio = size[i] / size[1-i];
                document.querySelectorAll(`#image_edit_output_${axis} input`).forEach(input => {
                    input.min = Math.ceil(Math.max(32, 32 * ratio));
                    input.max = Math.floor(Math.min(4096, 4096 * ratio));
                });
            }
        } finally { syncing = false; }
    }
    document.addEventListener('input', event => {
        if (syncing || !['range', 'number'].includes(event.target.type)) return;
        const edge = ['left', 'right', 'top', 'bottom'].find(name => event.target.closest?.(`#image_edit_canvas_${name}`));
        if (edge && event.target.value !== '') { refresh({[edge]: event.target.value}); return; }
        if (event.target.closest?.('#image_edit_output_scale')) { enable(); return; }
        const axis = ['width', 'height'].find(name => event.target.closest?.(`#image_edit_output_${name}`));
        if (!axis || event.target.value === '') return;
        const size = geometry();
        const pair = size && linkedSize(event.target.value, ...size, axis);
        if (!pair) return;
        lastAxis = axis; syncing = true;
        try { write(axis === 'width' ? 'height' : 'width', pair[axis === 'width' ? 1 : 0]); }
        finally { syncing = false; }
        enable();
    });
    document.addEventListener('change', event => {
        if (event.target.closest?.('#image_edit_canvas_enabled')) refresh();
    });
    if (typeof onUiUpdate === 'function') onUiUpdate(() => refresh());
    // Capture the latest edited edge even when Generate immediately follows a drag.
    function submitPair(args, enabled, mode, width, height) {
        if (args[enabled] && args[mode] === 'Resize to') {
            const size = geometry();
            const pair = size && linkedSize(field(lastAxis)?.value, ...size, lastAxis);
            if (pair) [args[width], args[height]] = pair;
        }
        return args;
    }
    api.submit = args => args[23] || !args[15] ? submitPair(args, 36, 37, 38, 39) : args;
    api.cropSubmit = args => submitPair(args, 9, 10, 11, 12);
})(typeof window !== 'undefined' ? window : globalThis);
