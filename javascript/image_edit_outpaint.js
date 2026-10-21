// Preview geometry only. Model input and masks are built from original pixels in Python.
((root) => {
    const edges = ["left", "right", "top", "bottom"];
    function plan(width, height, values) {
        const [left, right, top, bottom] = edges.map(key => Number(values[key] || 0));
        if (![width, height, left, right, top, bottom].every(Number.isInteger)) return null;
        const w = width + left + right, h = height + top + bottom;
        const box = [Math.max(0, -left), Math.max(0, -top), Math.min(width, width + right), Math.min(height, height + bottom)];
        if (Math.min(w, h) < 1 || Math.max(w, h) > 16384 || w * h > 64000000 || box[0] >= box[2] || box[1] >= box[3]) return null;
        return {width: w, height: h, left, top, box,
            fitWidth: width + Math.max(0, left) + Math.max(0, right),
            fitHeight: height + Math.max(0, top) + Math.max(0, bottom)};
    }
    const api = {plan};
    if (typeof module !== "undefined") module.exports = api;
    root.ImageEditOutpaint = api;
    root.imageEditCanvasEdges = {enabled: false, left: 0, right: 0, top: 0, bottom: 0};
    root.imageEditSetCanvasEdges = (enabled, left, right, top, bottom) => {
        root.imageEditCanvasEdges = {enabled: !!enabled, left: Number(left), right: Number(right), top: Number(top), bottom: Number(bottom)};
        const canvas = root.qwenEditPaintCanvas;
        if (!canvas) return;
        canvas.no_scribbles = false;
        canvas.drawing = false;
        canvas.adjustInitialPositionAndScale();
        canvas.drawImage();
    };
    if (typeof document === "undefined") return;
    document.addEventListener("input", event => {
        const key = edges.find(name => event.target.closest?.(`#image_edit_canvas_${name}`));
        if (!key || !["range", "number"].includes(event.target.type)) return;
        const value = Number(event.target.value);
        if (!Number.isFinite(value) || event.target.value === "") return;
        const current = {...root.imageEditCanvasEdges, [key]: value};
        root.imageEditSetCanvasEdges(current.enabled, ...edges.map(name => current[name]));
    });
})(typeof window !== "undefined" ? window : globalThis);
