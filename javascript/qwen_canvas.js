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
            // Add opaque selection strokes. Erase-then-paint creates alpha
            // seams at antialiased edges when strokes overlap in Forge's brush.
            this.scribbleColor = window.imageEditMaskColor || "#00ff00";
            if (this.scribbleAlpha > 0) this.scribbleAlpha = 100;
            this.scribbleSoftness = 0;
            const canvas = this.drawingCanvas_, ctx = canvas.getContext("2d");
            const rect = canvas.getBoundingClientRect();
            const point = [(event.clientX - rect.left) / this.imgScale, (event.clientY - rect.top) / this.imgScale];
            this.temp_draw_points.push(point);
            ctx.putImageData(this.temp_draw_bg, 0, 0);
            ctx.save();
            ctx.globalCompositeOperation = this.scribbleAlpha <= 0 ? "destination-out" : "source-over";
            ctx.globalAlpha = 1;
            ctx.strokeStyle = ctx.fillStyle = this.scribbleColor;
            ctx.lineCap = ctx.lineJoin = "round";
            ctx.lineWidth = this.scribbleWidth * 4 / (this.scribbleWidthConsistent ? this.imgScale : 1);
            ctx.beginPath();
            if (this.temp_draw_points.length === 1) {
                ctx.arc(point[0], point[1], ctx.lineWidth / 2, 0, Math.PI * 2);
                ctx.fill();
            } else {
                this.temp_draw_points.forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y));
                ctx.stroke();
            }
            ctx.restore();
            canvas.style.opacity = "1";
        }
    }

    const canvas = new QwenEditCanvas(uuid, false, false, false, 420,
        window.imageEditMaskColor || "#00ff00", true, 12, false, consistentBrush, 100, true, 0, true);
    window.qwenEditPaintCanvas = canvas;
    document.getElementById(`resetButton_${uuid}`).title = "Clear painted area [Ctrl + X]";
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
