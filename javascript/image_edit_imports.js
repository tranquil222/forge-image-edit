// Explicit source imports; neither action generates or modifies another tab.
(() => {
    if (window.ImageEditImports) return;
    const buttons = new WeakSet();
    let busy = false;
    let feedbackTimer, buttonTimer, restoreFeedbackButton;
    let txt2imgHistory = {signature: null, selectedImported: false, cursor: '', count: 0};
    const appRoot = () => typeof gradioApp === "function" ? gradioApp() : document;
    const importFolder = () => (appRoot().querySelector('#image_edit_import_folder textarea, #image_edit_import_folder input')?.value || '').trim();

    function txt2imgSource() {
        const gallery = appRoot().querySelector("#txt2img_gallery");
        if (!gallery) return null;
        // Scope to txt2img even after the user switches tabs. Forge's global
        // selected_gallery_index() only searches the currently visible tab.
        // Gradio uses the original file URL for both preview and thumbnails.
        let image = gallery.querySelector(".thumbnail-item.selected img") ||
            gallery.querySelector('.preview img[data-testid="detailed-image"], .preview .image-button img');
        if (!image) {
            const images = gallery.querySelectorAll(".thumbnail-item img");
            if (images.length === 1) image = images[0];
        }
        const src = image?.getAttribute("src") || image?.currentSrc;
        if (!src) return null;
        const url = new URL(src, window.location.href);
        if (url.origin !== window.location.origin) throw new Error("The selected image must come from this Forge session.");
        const filename = decodeURIComponent(url.pathname).split(/[\\/]/).pop() || "txt2img.png";
        return { url: url.href, filename };
    }

    function txt2imgEmpty() {
        const gallery = appRoot().querySelector("#txt2img_gallery");
        return !gallery || (!gallery.querySelector('.preview img, .thumbnail-item img') &&
            !gallery.querySelectorAll('.thumbnail-item img').length);
    }

    function txt2imgSignature(selected) {
        const gallery = appRoot().querySelector("#txt2img_gallery");
        const images = [...(gallery?.querySelectorAll('.thumbnail-item img') || [])]
            .map(image => image.getAttribute('src') || image.currentSrc || '');
        return JSON.stringify([selected?.url || '', images, importFolder()]);
    }

    async function savedTxt2imgSource(cursor, random = false) {
        const root = new URL(window.gradio_config?.root || window.location.href, window.location.href);
        root.pathname = root.pathname.replace(/\/$/, '') + '/';
        root.search = ''; root.hash = '';
        const response = await fetch(new URL(random ? 'run/image_edit_random_txt2img' : 'run/image_edit_recent_txt2img', root), {
            method: 'POST', credentials: 'same-origin',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify({data: random ? [importFolder()] : [cursor, importFolder()]}),
            signal: AbortSignal.timeout(60000),
        });
        const reply = await response.json();
        if (!response.ok || reply.error) {
            throw new Error(typeof reply.error === 'string' ? reply.error : 'Could not read the txt2img output folder. Try again.');
        }
        const file = reply.data?.[0];
        if (!file?.url) throw new Error('No saved images found in the txt2img output folder yet.');
        const url = new URL(file.url, root);
        if (url.origin !== window.location.origin) throw new Error('The saved image must come from this Forge session.');
        return {url: url.href, filename: file.orig_name || file.path?.split(/[\\/]/).pop() || 'txt2img.png', fromFolder: true, random, cursor: reply.data[1]};
    }

    async function importSelection(kind) {
        if (busy) return;
        clearTimeout(feedbackTimer);
        clearTimeout(buttonTimer);
        restoreFeedbackButton?.();
        restoreFeedbackButton = null;
        const app = appRoot(), button = app.querySelector(`#image_edit_${kind}_import`);
        const note = app.querySelector("#image_edit_import_status");
        const label = button?.textContent;
        const width = button?.style?.width;
        let succeeded = false;
        function restoreButton() {
            if (!button) return;
            button.disabled = false; button.textContent = label;
            if (button.style) button.style.width = width;
        }
        busy = true;
        if (note) { note.hidden = true; note.textContent = ""; }
        if (button) {
            const pixels = button.getBoundingClientRect?.().width;
            if (pixels && button.style) button.style.width = pixels + "px";
            button.disabled = true; button.textContent = "Importing…";
        }
        try {
            if (window.imageEditCurvesBusy) throw new Error("Wait for the curves adjustment to finish saving, then import again.");
            let source;
            if (kind === 'txt2img') {
                const selected = txt2imgSource(), signature = txt2imgSignature(selected);
                if (signature !== txt2imgHistory.signature) {
                    txt2imgHistory = {signature, selectedImported: false, cursor: '', count: 0};
                }
                if (selected && !txt2imgHistory.selectedImported) source = selected;
                else if (selected || txt2imgEmpty()) source = await savedTxt2imgSource(txt2imgHistory.cursor);
            } else if (kind === 'random') source = await savedTxt2imgSource('', true);
            else source = window.ImageEditIIB?.currentImage();
            if (!source) throw new Error(kind === "txt2img"
                ? "Select an image in txt2img’s results, then switch to Image Edit and import again."
                : "Open an image in Infinite Image Browser’s lightbox, leave it open, then switch to Image Edit and import again.");
            const load = window.imageEditLoadImage || window.qwenEditLoadImage;
            if (typeof load !== "function") throw new Error("The source image control is not ready. Refresh Forge and try again.");
            await load(source.url, source.filename);
            succeeded = true;
            if (kind === 'txt2img') {
                if (source.fromFolder) { txt2imgHistory.cursor = source.cursor; txt2imgHistory.count++; }
                else txt2imgHistory.selectedImported = true;
            }
            const detail = source.random ? ' (random saved txt2img image)' : source.fromFolder
                ? (txt2imgHistory.count === 1 ? ' (newest saved txt2img image)' : ` (saved txt2img image ${txt2imgHistory.count}, newest first)`) : '';
            const message = `Imported ${source.filename}${detail} with its embedded metadata.`;
            if (button) button.title = message;
            if (note) {
                note.setAttribute("role", "status");
                note.setAttribute("data-kind", "success");
                note.textContent = message;
                note.hidden = false;
            }
            return source;
        } catch (error) {
            if (note) {
                note.setAttribute("role", "alert");
                note.setAttribute("data-kind", "error");
                note.textContent = error?.message || "Could not import the image. Try again.";
                note.hidden = false;
                feedbackTimer = setTimeout(() => { note.hidden = true; }, 8000);
            }
            return null;
        } finally {
            busy = false;
            if (button && succeeded) {
                button.disabled = false; button.textContent = "Imported ✓";
                restoreFeedbackButton = restoreButton;
                buttonTimer = setTimeout(() => { restoreButton(); restoreFeedbackButton = null; }, 2000);
            } else restoreButton();
        }
    }

    function refresh() {
        const app = appRoot(), iib = app.querySelector("#image_edit_iib_control");
        if (iib) {
            const available = !!app.querySelector('#infinite_image_browsing_container_wrapper, #tab_infinite-image-browsing, iframe[src*="/infinite_image_browsing"]');
            if (iib.hidden === available) iib.hidden = !available;
        }
        for (const kind of ["txt2img", "iib", "random"]) {
            const button = app.querySelector(`#image_edit_${kind}_import`);
            if (button && !buttons.has(button)) {
                buttons.add(button);
                button.addEventListener("click", () => importSelection(kind));
            }
        }
    }
    window.ImageEditImports = { txt2imgSource, importSelection, refresh };
    if (typeof onUiLoaded === "function") onUiLoaded(refresh);
    if (typeof onUiUpdate === "function") onUiUpdate(refresh);
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", refresh, { once: true });
    else refresh();
})();
