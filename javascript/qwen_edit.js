function qwenEditSubmit(...args) {
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

// Local full-resolution viewer. No generation, upload or model change occurs.
(() => {
    if (window.qwenEditLightboxInstalled) return;
    window.qwenEditLightboxInstalled = true;
    let dialog, viewport, picture, caption, zoomLabel, originalButton, editedButton, download;
    let originalUrl = "", editedUrl = "", showingOriginal = false, scale = 1, fit = true;
    let drag = null;
    const originals = new Map();

    document.addEventListener("load", event => {
        if (!event.target.matches?.("#qwen_edit_result img") || !window.qwenEditPendingOriginalUrl) return;
        originals.set(event.target.currentSrc || event.target.src, window.qwenEditPendingOriginalUrl);
        if (originals.size > 12) originals.delete(originals.keys().next().value);
        window.qwenEditPendingOriginalUrl = "";
    }, true);

    function resize(nextScale) {
        if (!picture.naturalWidth) return;
        scale = Math.max(0.05, Math.min(8, nextScale));
        picture.style.width = `${Math.round(picture.naturalWidth * scale)}px`;
        picture.style.height = `${Math.round(picture.naturalHeight * scale)}px`;
        zoomLabel.textContent = `${Math.round(scale * 100)}%`;
        caption.textContent = `${showingOriginal ? "Original" : "Edited"} · ${picture.naturalWidth} × ${picture.naturalHeight}`;
    }

    function fitImage() {
        fit = true;
        resize(Math.min(1, (viewport.clientWidth - 32) / picture.naturalWidth, (viewport.clientHeight - 32) / picture.naturalHeight));
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
    }

    function createViewer() {
        dialog = document.createElement("dialog");
        dialog.id = "qwen_edit_lightbox";
        dialog.setAttribute("aria-label", "Image viewer");
        dialog.innerHTML = `<header class="qe-viewer-toolbar">
            <div class="qe-viewer-compare"><button type="button" data-action="original">Original</button><button type="button" data-action="edited">Edited</button></div>
            <span class="qe-viewer-caption"></span>
            <div class="qe-viewer-tools"><button type="button" data-action="fit">Fit</button><button type="button" data-action="actual">100%</button><button type="button" data-action="out" aria-label="Zoom out">−</button><span class="qe-viewer-zoom"></span><button type="button" data-action="in" aria-label="Zoom in">+</button><a class="qe-viewer-download" download>Download PNG</a><button type="button" data-action="close" aria-label="Close image viewer">✕</button></div>
            </header><div class="qe-viewer-viewport"><img draggable="false" alt="Edited result"></div>
            <footer>Scroll to zoom · drag to pan · ← / → compare · Esc to close</footer>`;
        document.body.appendChild(dialog);
        viewport = dialog.querySelector(".qe-viewer-viewport");
        picture = viewport.querySelector("img");
        caption = dialog.querySelector(".qe-viewer-caption");
        zoomLabel = dialog.querySelector(".qe-viewer-zoom");
        originalButton = dialog.querySelector('[data-action="original"]');
        editedButton = dialog.querySelector('[data-action="edited"]');
        download = dialog.querySelector(".qe-viewer-download");
        picture.addEventListener("load", () => fit ? fitImage() : resize(scale));
        dialog.addEventListener("click", event => {
            const action = event.target.closest("[data-action]")?.dataset.action;
            if (action === "close" || event.target === dialog) dialog.close();
            if (action === "original") selectOriginal(true);
            if (action === "edited") selectOriginal(false);
            if (action === "fit") fitImage();
            if (action === "actual") { fit = false; resize(1); }
            if (action === "in") zoom(1.25);
            if (action === "out") zoom(0.8);
        });
        dialog.addEventListener("keydown", event => {
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
        if (!event.target.closest?.("#qwen_edit_result") || event.target.closest(".icon-buttons, a")) return;
        // Gradio wraps the result image in a button; keep that click (and Enter).
        const image = event.target.closest("img") || event.target.closest("button")?.querySelector("img");
        if (!image?.src) return;
        event.preventDefault();
        if (!dialog) createViewer();
        const app = gradioApp();
        editedUrl = image.currentSrc || image.src;
        const source = app.querySelector("#qwen_edit_source img");
        originalUrl = originals.get(editedUrl) || source?.currentSrc || source?.src || "";
        originalButton.disabled = !originalUrl;
        const link = app.querySelector("#qwen_edit_download a[href]");
        download.href = link?.href || editedUrl;
        fit = true;
        dialog.showModal();
        selectOriginal(false);
        if (picture.complete && picture.naturalWidth) fitImage();
    });
})();
