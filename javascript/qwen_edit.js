function qwenEditSubmit(...args) {
    if (window.imageEditCurvesBusy) throw new Error("Wait for the curves adjustment to finish saving.");
    const id = randomId();
    window.qwenEditPendingOriginalUrl = gradioApp().querySelector("#qwen_edit_source img")?.src || "";
    const container = gradioApp().getElementById("qwen_edit_result_container");
    if (container) requestProgress(id, container, null, () => {});
    args[0] = id;
    return args;
}

// Original file bytes go to the source. Our own edit recipes are imported by a
// separate data-only handler; ordinary images do not change generation settings.
window.qwenEditLoadImage = async function (imageUrl, filename = "source.png") {
    const app = gradioApp();
    const source = app.querySelector("#qwen_edit_source");
    const tab = app.querySelector("#tab_qwen_edit-button");
    if (!source || !tab) throw new Error("Image Edit is unavailable. Enable the extension and refresh Forge.");

    const url = new URL(imageUrl, window.location.href);
    if (url.origin !== window.location.origin) throw new Error("The image must come from this Forge image browser.");
    const response = await fetch(url.href, { credentials: "same-origin", signal: AbortSignal.timeout(30000) });
    if (!response.ok) throw new Error(`Could not load the source image (HTTP ${response.status}).`);
    const blob = await response.blob();
    if (!blob.type.startsWith("image/")) throw new Error("The selected file is not a supported image.");

    tab.click();
    let input = source.querySelector('input[type="file"]');
    if (!input) {
        source.querySelector('button[aria-label="Remove Image"], button[title="Remove Image"]')?.click();
        for (let attempt = 0; attempt < 30 && !input; attempt++) {
            await new Promise(resolve => setTimeout(resolve, 50));
            input = source.querySelector('input[type="file"]');
        }
    }
    if (!input) throw new Error("The source image control is not ready. Refresh the Forge page and try again.");
    const transfer = new DataTransfer();
    transfer.items.add(new File([blob], filename.split(/[\\/]/).pop() || "source.png", { type: blob.type }));
    input.files = transfer.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
    const recipeInput = app.querySelector("#image_edit_handoff textarea");
    if (recipeInput) {
        const data = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = () => reject(new Error("Could not read the edit recipe."));
            reader.readAsDataURL(blob);
        });
        recipeInput.value = data;
        updateInput(recipeInput);
    }
};
window.imageEditLoadImage = window.qwenEditLoadImage;

// Local viewer and optional curves workspace. Viewing never runs a model.
(() => {
    if (window.qwenEditLightboxInstalled) return;
    window.qwenEditLightboxInstalled = true;
    let dialog, viewport, picture, stage, preview, curves, caption, zoomLabel, originalButton, editedButton, download;
    let originalUrl = "", editedUrl = "", showingOriginal = false, scale = 1, fit = true;
    let frameWidth = 0, frameHeight = 0;
    let drag = null;
    const originals = new Map();

    document.addEventListener("load", event => {
        if (!event.target.matches?.("#qwen_edit_result img") || !window.qwenEditPendingOriginalUrl) return;
        originals.set(event.target.currentSrc || event.target.src, window.qwenEditPendingOriginalUrl);
        if (originals.size > 12) originals.delete(originals.keys().next().value);
        window.qwenEditPendingOriginalUrl = "";
    }, true);

    function resize(nextScale) {
        if (!frameWidth) return;
        scale = Math.max(0.05, Math.min(8, nextScale));
        const width = `${Math.round(frameWidth * scale)}px`, height = `${Math.round(frameHeight * scale)}px`;
        for (const element of [stage, picture, preview]) if (element) { element.style.width = width; element.style.height = height; }
        zoomLabel.textContent = `${Math.round(scale * 100)}%`;
        caption.textContent = `${showingOriginal ? "Original" : "Edited"} · ${picture.naturalWidth} × ${picture.naturalHeight}`;
    }

    function fitImage() {
        fit = true;
        resize(Math.min(1, (viewport.clientWidth - 32) / frameWidth, (viewport.clientHeight - 32) / frameHeight));
        viewport.scrollTo(0, 0);
    }

    function zoom(factor) {
        fit = false;
        const x = (viewport.scrollLeft + viewport.clientWidth / 2) / scale;
        const y = (viewport.scrollTop + viewport.clientHeight / 2) / scale;
        resize(scale * factor);
        viewport.scrollTo(x * scale - viewport.clientWidth / 2, y * scale - viewport.clientHeight / 2);
    }

    function selectOriginal(value) {
        if (value && !originalUrl) return;
        showingOriginal = value;
        originalButton.setAttribute("aria-pressed", String(value));
        editedButton.setAttribute("aria-pressed", String(!value));
        picture.alt = value ? "Original source image" : "Edited result";
        picture.src = value ? originalUrl : editedUrl;
        curves?.compare(value);
    }

    function createViewer() {
        dialog = document.createElement("dialog");
        dialog.id = "qwen_edit_lightbox";
        dialog.setAttribute("aria-label", "Image viewer");
        dialog.innerHTML = `<header class="qe-viewer-toolbar">
            <div class="qe-viewer-compare"><button type="button" data-action="original">Original</button><button type="button" data-action="edited">Edited</button></div>
            <span class="qe-viewer-caption"></span>
            <div class="qe-viewer-tools"><button type="button" data-action="curves" aria-pressed="false">Curves</button><button type="button" data-action="fit">Fit</button><button type="button" data-action="actual" title="100% of edited dimensions; comparison framing stays linked">100%</button><button type="button" data-action="out" aria-label="Zoom out">−</button><span class="qe-viewer-zoom"></span><button type="button" data-action="in" aria-label="Zoom in">+</button><a class="qe-viewer-download" download>Download PNG</a><button type="button" data-action="close" aria-label="Close image viewer">✕</button></div>
            </header><div class="qe-viewer-body"><div class="qe-viewer-viewport"><div class="qe-viewer-stage"><img draggable="false" alt="Edited result"><canvas class="qe-viewer-preview" hidden></canvas></div></div><aside class="qe-curves-panel" hidden></aside></div>
            <footer>Scroll to zoom · drag to pan · ← / → compare · linked zoom and pan · Esc to close</footer>`;
        document.body.appendChild(dialog);
        viewport = dialog.querySelector(".qe-viewer-viewport");
        picture = viewport.querySelector("img");
        stage = dialog.querySelector(".qe-viewer-stage");
        preview = dialog.querySelector(".qe-viewer-preview");
        caption = dialog.querySelector(".qe-viewer-caption");
        zoomLabel = dialog.querySelector(".qe-viewer-zoom");
        originalButton = dialog.querySelector('[data-action="original"]');
        editedButton = dialog.querySelector('[data-action="edited"]');
        download = dialog.querySelector(".qe-viewer-download");
        picture.addEventListener("load", () => {
            if (!frameWidth) { frameWidth = picture.naturalWidth; frameHeight = picture.naturalHeight; fitImage(); }
            else resize(scale); // Comparing must never reset zoom or pan.
        });
        if (window.createImageEditCurves) curves = window.createImageEditCurves(dialog, picture, preview, {
            selectEdited: () => selectOriginal(false),
            layoutChanged: () => fit ? fitImage() : resize(scale),
            applied: (url, savedUrl) => {
                originals.set(url, originalUrl); editedUrl = url; download.href = savedUrl;
                curves.open(url, savedUrl); selectOriginal(false); resize(scale);
            }
        });
        download.addEventListener("click", event => curves?.download(event));
        dialog.addEventListener("click", event => {
            const action = event.target.closest("[data-action]")?.dataset.action;
            if (action === "close" || event.target === dialog) dialog.close();
            if (action === "original") selectOriginal(true);
            if (action === "edited") selectOriginal(false);
            if (action === "fit") fitImage();
            if (action === "actual") { fit = false; resize(1); }
            if (action === "in") zoom(1.25);
            if (action === "out") zoom(0.8);
            if (action === "curves") curves?.toggle();
        });
        dialog.addEventListener("keydown", event => {
            if (event.target.closest?.("input, select, textarea, .qe-curves-graph")) return;
            if (event.key === "ArrowLeft") selectOriginal(true);
            else if (event.key === "ArrowRight") selectOriginal(false);
            else if (["+", "="].includes(event.key)) zoom(1.25);
            else if (event.key === "-") zoom(0.8);
            else if (event.key === "0") fitImage();
            else return;
            event.preventDefault();
        });
        viewport.addEventListener("wheel", event => {
            event.preventDefault();
            zoom(event.deltaY < 0 ? 1.15 : 1 / 1.15);
        }, { passive: false });
        viewport.addEventListener("pointerdown", event => {
            if (event.button !== 0) return;
            drag = { x: event.clientX, y: event.clientY, left: viewport.scrollLeft, top: viewport.scrollTop };
            viewport.setPointerCapture(event.pointerId);
        });
        viewport.addEventListener("pointermove", event => {
            if (drag) viewport.scrollTo(drag.left + drag.x - event.clientX, drag.top + drag.y - event.clientY);
        });
        const stopDrag = () => { drag = null; };
        viewport.addEventListener("pointerup", stopDrag);
        viewport.addEventListener("pointercancel", stopDrag);
        dialog.addEventListener("close", stopDrag);
        window.addEventListener("resize", () => { if (dialog.open && fit) fitImage(); });
    }

    document.addEventListener("click", event => {
        const thumbnail = event.target.closest?.("#image_edit_batch_gallery .thumbnail-item");
        if (thumbnail) {
            const app = gradioApp();
            const index = Array.from(app.querySelectorAll("#image_edit_batch_gallery .thumbnail-item")).indexOf(thumbnail);
            const selection = app.querySelector("#image_edit_batch_selection textarea");
            if (selection && index >= 0) {
                selection.value = JSON.stringify({ index, request: Date.now() });
                updateInput(selection);
            }
            return;
        }
        if (!event.target.closest?.("#qwen_edit_result") || event.target.closest(".icon-buttons, a")) return;
        // Gradio wraps the result image in a button; keep that click (and Enter).
        const image = event.target.closest("img") || event.target.closest("button")?.querySelector("img");
        if (!image?.src) return;
        event.preventDefault();
        if (!dialog) createViewer();
        const app = gradioApp();
        editedUrl = image.currentSrc || image.src;
        frameWidth = image.naturalWidth || 0; frameHeight = image.naturalHeight || 0;
        const source = app.querySelector("#qwen_edit_source img");
        // The batch retains its submitted source even if the canvas changes later.
        originalUrl = app.querySelector("#image_edit_batch_source textarea")?.value || originals.get(editedUrl) || source?.currentSrc || source?.src || "";
        originalButton.disabled = !originalUrl;
        const link = app.querySelector("#qwen_edit_download a[href]");
        download.href = link?.href || editedUrl;
        curves?.open(editedUrl, download.href);
        fit = true;
        dialog.showModal();
        selectOriginal(false);
        if (!frameWidth && picture.complete && picture.naturalWidth) { frameWidth = picture.naturalWidth; frameHeight = picture.naturalHeight; }
        if (frameWidth) fitImage();
    });
})();
