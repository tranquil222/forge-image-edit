// Read-only IIB integration: import its open lightbox from Image Edit.
// No IIB menus, files, settings, private Vue state or global patches are changed.
(() => {
    if (window.ImageEditIIB) return;
    const frameSelector = '#infinite_image_browsing_container_wrapper iframe, iframe[src*="/infinite_image_browsing"]';

    function originalImage(value, base = window.location.href) {
        try {
            const url = new URL(value, base);
            if (url.origin !== window.location.origin) return null;
            const endpoint = url.pathname.match(/^(.*\/infinite_image_browsing)\/(?:file|image-thumbnail|img\/[^/]+)$/);
            const path = url.searchParams.get("path");
            if (!endpoint || !path || !/\.(png|jpe?g|jpe|webp|gif|bmp|avif|jxl)$/i.test(path)) return null;
            // Import the original bytes, not a resized preview or canvas snapshot.
            url.pathname = endpoint[1] + "/file";
            url.searchParams.delete("size");
            url.searchParams.delete("disposition");
            return { url: url.href, filename: path.split(/[\\/]/).pop() };
        } catch (_) { return null; }
    }

    function openInFrame(node) {
        if (!node?.isConnected) return false;
        // The host Gradio tab/iframe is hidden after switching to Image Edit.
        // Check only ancestors inside IIB, not layout rects in the hidden tab.
        const view = node.ownerDocument.defaultView;
        for (let current = node; current; current = current.parentElement) {
            const style = view.getComputedStyle(current);
            if (current.hidden || current.getAttribute("aria-hidden") === "true" ||
                style.display === "none" || style.visibility === "hidden" || style.visibility === "collapse") return false;
        }
        return true;
    }

    function previewImage(doc) {
        if (!doc?.body) return null;
        for (const image of doc.querySelectorAll(".ant-image-preview-wrap .ant-image-preview-img")) {
            if (!openInFrame(image)) continue;
            // src updates immediately on next/previous; currentSrc can still be
            // the old image while the new preview is loading.
            const source = originalImage(image.getAttribute("src") || image.currentSrc, doc.baseURI);
            if (source) return source;
        }
        return null;
    }

    function appRoot() { return typeof gradioApp === "function" ? gradioApp() : document; }

    function currentImage() {
        const sources = new Map();
        for (const frame of appRoot().querySelectorAll(frameSelector)) {
            try {
                const source = previewImage(frame.contentDocument);
                if (source) sources.set(source.url, source);
            } catch (_) { /* An unrelated/cross-origin frame is not an IIB source. */ }
        }
        if (sources.size > 1) throw new Error("More than one IIB lightbox is open. Keep one open, then import again.");
        return sources.values().next().value || null;
    }

    window.ImageEditIIB = { originalImage, previewImage, currentImage };
})();
