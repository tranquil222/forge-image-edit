// Reuse Forge's inpainting interface. Changes below affect only this instance.
window.qwenEditInitCanvas = function (uuid, consistentBrush = false) {
    class QwenEditCanvas extends ForgeCanvas {
        updateBackgroundImageData() {
            // Original file bytes retain PNG/EXIF metadata on unmodified Forge.
            this.background_gradio_bind.set_value(this.img || "");
        }
        loadImage(value) {
            if (value === this.img) return;
            // A new source must not inherit strokes or undo history, even when
            // it has the same dimensions as the previous source.
            const canvas = this.drawingCanvas_;
            canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
            this.history = [];
            this.historyIndex = -1;
            this.drawing = false;
            this.dragging = false;
            super.loadImage(value);
        }

        handleDraw(event) {
            // Fixed opaque selection data; Shift still activates the eraser.
            this.scribbleColor = window.imageEditMaskColor || "#00ff00";
            if (this.scribbleAlpha > 0) this.scribbleAlpha = 100;
            this.scribbleSoftness = 0;
            super.handleDraw(event);
        }
    }

    const canvas = new QwenEditCanvas(uuid, false, true, false, 420,
        window.imageEditMaskColor || "#00ff00", true, 12, false, consistentBrush, 100, true, 0, true);
    window.qwenEditPaintCanvas = canvas;
};

window.qwenEditSetModel = function (family) {
    window.imageEditMaskColor = family.startsWith("Fibo 2.0") ? "#808080" : "#00ff00";
    const canvas = window.qwenEditPaintCanvas;
    if (!canvas) return;
    canvas.scribbleColor = window.imageEditMaskColor;
    const drawing = canvas.drawingCanvas_;
    const context = drawing.getContext("2d");
    context.save();
    context.globalCompositeOperation = "source-in";
    context.fillStyle = window.imageEditMaskColor;
    context.fillRect(0, 0, drawing.width, drawing.height);
    context.restore();
    canvas.updateDrawingData();
};

window.qwenEditSetPainting = function (enabled) {
    const canvas = window.qwenEditPaintCanvas;
    if (!canvas) return;
    canvas.no_scribbles = !enabled;
    const toolbar = document.getElementById(`toolbar_${canvas.uuid}`);
    toolbar.querySelector(".forge-toolbar-box-b").style.display = enabled ? "" : "none";
    toolbar.title = enabled ? "[Shift] for Eraser" : "";
    for (const action of ["reset", "undo", "redo"]) {
        document.getElementById(`${action}Button_${canvas.uuid}`).style.display = enabled ? "" : "none";
    }
    // Hide ignored selection strokes while whole-image editing is selected.
    canvas.drawingCanvas_.style.opacity = enabled ? "1" : "0";
    document.getElementById(`scribbleIndicator_${canvas.uuid}`).style.display = "none";
};
