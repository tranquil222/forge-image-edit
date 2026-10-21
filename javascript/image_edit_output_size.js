// Link in the browser: server responses must never write an older companion edge.
((root) => {
    function linkedSize(value, width, height, axis) {
        value = Number(value);
        if (!Number.isFinite(value) || value < 32 || value > 4096 || width <= 0 || height <= 0) return null;
        const pair = axis === 'height' ? [Math.round(value * width / height), Math.round(value)]
            : [Math.round(value), Math.round(value * height / width)];
        return pair.every(edge => edge >= 32 && edge <= 4096) ? pair : null;
    }
    const api = {linkedSize};
    if (typeof module !== 'undefined') module.exports = api;
    root.ImageEditOutputSize = api;
    if (typeof document === 'undefined') return;
    let syncing = false, lastAxis = 'width';
    const field = axis => document.querySelector(`#image_edit_output_${axis} input[type="number"]`);
    function currentPair(axis, value) {
        const canvas = root.qwenEditPaintCanvas;
        return canvas?.img ? linkedSize(value, canvas.orgWidth, canvas.orgHeight, axis) : null;
    }
    document.addEventListener('input', event => {
        if (syncing || !['range', 'number'].includes(event.target.type)) return;
        const axis = ['width', 'height'].find(name => event.target.closest?.(`#image_edit_output_${name}`));
        if (!axis || event.target.value === '') return;
        const pair = currentPair(axis, event.target.value);
        if (!pair) return;
        lastAxis = axis;
        const other = axis === 'width' ? 'height' : 'width';
        const input = field(other);
        if (!input) return;
        syncing = true;
        try {
            input.value = pair[other === 'width' ? 0 : 1];
            input.dispatchEvent(new Event('input', {bubbles: true}));
        } finally { syncing = false; }
    });
    // Use the latest typed/dragged edge even if Generate follows the input immediately.
    api.submit = args => {
        if (args[36] && args[37] === 'Resize to' && !args[23] && !args[15]) {
            const pair = currentPair(lastAxis, field(lastAxis)?.value);
            if (pair) [args[38], args[39]] = pair;
        }
        return args;
    };
})(typeof window !== 'undefined' ? window : globalThis);
