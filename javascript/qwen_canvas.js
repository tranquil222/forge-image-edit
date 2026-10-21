// Reuse Forge's inpainting interface. Changes below affect only this instance.
window.qwenEditInitCanvas = function (uuid, consistentBrush = false) {
    class QwenEditCanvas extends ForgeCanvas {
        canvasLayout() {
            const values = window.imageEditCanvasEdges;
            return this.img && values?.enabled ? window.ImageEditOutpaint?.plan(this.orgWidth, this.orgHeight, values) : null;
        }
        adjustInitialPositionAndScale() {
            const layout = this.canvasLayout();
            if (!layout) { super.adjustInitialPositionAndScale(); return; }
            const container = document.getElementById(`container_${this.uuid}`);
            this.imgScale = Math.min((container.clientWidth - 24) / layout.fitWidth, (container.clientHeight - 24) / layout.fitHeight);
            this.imgX = (container.clientWidth - layout.fitWidth * this.imgScale) / 2 + Math.max(0, -layout.left) * this.imgScale;
            this.imgY = (container.clientHeight - layout.fitHeight * this.imgScale) / 2 + Math.max(0, -layout.top) * this.imgScale;
        }
        drawImage() {
            super.drawImage();
            const image = document.getElementById(`image_${this.uuid}`);
            const container = document.getElementById(`imageContainer_${this.uuid}`);
            const layout = this.canvasLayout();
            if (!this.canvasFrame) {
                this.canvasFrame = document.createElement("div");
                this.canvasFrame.className = "qe-outpaint-frame";
                this.canvasFrame.setAttribute("aria-hidden", "true");
                container.insertBefore(this.canvasFrame, image);
            }
            this.canvasFrame.hidden = !layout;
            container.classList.toggle("qe-outpaint-active", !!window.imageEditCanvasEdges?.enabled);
            this.drawingCanvas_.style.display = this.img ? "" : "none";
            this.drawingCanvas_.style.clipPath = "";
            image.style.clipPath = "";
            if (!layout) return;
            Object.assign(this.canvasFrame.style, {left: `${this.imgX}px`, top: `${this.imgY}px`,
                width: `${layout.width * this.imgScale}px`, height: `${layout.height * this.imgScale}px`});
            image.style.left = `${this.imgX + layout.left * this.imgScale}px`;
            image.style.top = `${this.imgY + layout.top * this.imgScale}px`;
            const [x1, y1, x2, y2] = layout.box;
            image.style.clipPath = `inset(${y1 / this.orgHeight * 100}% ${(this.orgWidth - x2) / this.orgWidth * 100}% ${(this.orgHeight - y2) / this.orgHeight * 100}% ${x1 / this.orgWidth * 100}%)`;
            // Keep the painting bitmap in original-image coordinates. Only its
            // display position/clip changes, so strokes survive canvas changes.
            Object.assign(this.drawingCanvas_.style, {left: image.style.left, top: image.style.top, clipPath: image.style.clipPath});
        }
        isInsideImage(x, y) {
            const layout = this.canvasLayout();
            return layout ? x > this.imgX && x < this.imgX + layout.width * this.imgScale && y > this.imgY && y < this.imgY + layout.height * this.imgScale : super.isInsideImage(x, y);
        }
        updateBackgroundImageData() {
            // Original file bytes retain PNG/EXIF metadata on unmodified Forge.
            this.background_gradio_bind.set_value(this.img || "");
        }
        loadImage(value) {
            if (value && value === this.img) return;
            const enabled = !!window.imageEditCanvasEdges?.enabled;
            window.imageEditCanvasEdges = {enabled, left: 0, right: 0, top: 0, bottom: 0};
            this.no_scribbles = false;
            // A new source must not inherit strokes or undo history, even when
            // it has the same dimensions as the previous source.
            const canvas = this.drawingCanvas_;
            canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
            this.history = [];
            this.historyIndex = -1;
            this.drawing = false;
            this.dragging = false;
            super.loadImage(value);
            // Older Forge canvases clear only the preview, not the Python input.
            if (!value && this.background_gradio_bind.target.value) this.updateBackgroundImageData();
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
    const paintHelp = "Paint an edit area to confine changes. Leave unpainted for a whole-image edit.";
    document.getElementById(`scribbleWidthBlock_${uuid}`).title = `${paintHelp}\nW + scroll adjusts brush size. Shift + paint erases.`;
    document.getElementById(`scribbleWidth_${uuid}`).setAttribute("aria-description", paintHelp);
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
