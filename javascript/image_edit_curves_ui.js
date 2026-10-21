// Viewer-only adjustment mode. Preview always starts from immutable result pixels.
(() => {
    window.createImageEditCurves = function(dialog, picture, preview, callbacks) {
        const C = window.ImageEditCurves;
        const panel = dialog.querySelector(".qe-curves-panel");
        panel.innerHTML = `<div class="qe-curves-title"><strong>Curves & levels</strong><label><input type="checkbox" data-field="preview" checked> Preview</label></div>
            <div class="qe-curves-scope">Loading adjustment area…</div>
            <label class="qe-curves-channel">Channel <select aria-label="Curve channel"><option value="rgb">RGB · all channels</option><option value="red">Red</option><option value="green">Green</option><option value="blue">Blue</option></select></label>
            <canvas class="qe-curves-graph" width="280" height="280" tabindex="0" aria-label="Tone curve. Click to add a point; drag or use arrow keys to adjust; Delete removes a point."></canvas>
            <div class="qe-curves-points"><label>Input <input type="number" min="0" max="255" step="1" data-field="input" value="0"></label><label>Output <input type="number" min="0" max="255" step="1" data-field="output" value="0"></label><button type="button" data-curve="delete" title="Delete selected point">Delete</button></div>
            <div class="qe-curves-hint">Click to add a point · drag to shape the curve</div>
            <details><summary>Levels</summary><div class="qe-levels-grid">
                <label>Black<input type="number" min="0" max="254" step="1" data-level="0" value="0"></label>
                <label>Midtones<input type="number" min="0.1" max="10" step="0.05" data-level="1" value="1"></label>
                <label>White<input type="number" min="1" max="255" step="1" data-level="2" value="255"></label>
                <label>Output black<input type="number" min="0" max="255" step="1" data-level="3" value="0"></label>
                <label>Output white<input type="number" min="0" max="255" step="1" data-level="4" value="255"></label>
            </div></details>
            <div class="qe-curves-actions"><button type="button" data-curve="undo">Undo</button><button type="button" data-curve="redo">Redo</button><button type="button" data-curve="reset-channel">Reset channel</button><button type="button" data-curve="reset-all">Reset all</button></div>
            <button type="button" data-curve="apply" class="qe-curves-apply" disabled>Apply to result</button>
            <label class="qe-curves-default"><input type="checkbox" data-field="fibo-default" disabled> Use as Fibo default (unpainted)</label>
            <div class="qe-curves-hint" data-field="default-hint">Fibo whole-image edits only.</div>
            <p class="qe-curves-status" role="status">Apply saves a new PNG; the previous file is kept.</p>`;
        const graph = panel.querySelector("canvas"), ctx = graph.getContext("2d");
        const status = panel.querySelector(".qe-curves-status");
        const scopeLabel = panel.querySelector(".qe-curves-scope");
        const channelSelect = panel.querySelector("select");
        const previewCheck = panel.querySelector('[data-field="preview"]');
        const defaultCheck = panel.querySelector('[data-field="fibo-default"]');
        const defaultHint = panel.querySelector('[data-field="default-hint"]');
        const input = panel.querySelector('[data-field="input"]'), output = panel.querySelector('[data-field="output"]');
        let settings = C.defaults(), channel = "rgb", selected = 0, undo = [], redo = [];
        let raw = null, histogram = null, hash = "", currentUrl = "", downloadUrl = "";
        let original = false, dragging = false, pendingFrame = 0, loadVersion = 0, pending = null;
        let loadPromise = null, loadError = "", luts = C.compile(settings);
        let mask = null, contextId = null, contextReady = false;
        let fiboDefault = {eligible: false, enabled: false, available: false, can_capture: false};
        const colors = {rgb: "#e7e9ed", red: "#ef8585", green: "#79cba0", blue: "#81b6ff"};
        const changed = () => !C.identity(luts);
        function remember() { undo.push(C.clone(settings)); if (undo.length > 40) undo.shift(); redo = []; }
        function visibility() {
            const show = !!raw && contextReady && !original && previewCheck.checked && changed();
            preview.hidden = !show;
            picture.style.display = show ? "none" : "block";
        }
        function controls() {
            const points = settings[channel].points;
            selected = Math.min(selected, points.length - 1);
            input.value = points[selected][0]; output.value = points[selected][1];
            input.disabled = selected === 0 || selected === points.length - 1;
            panel.querySelector('[data-curve="delete"]').disabled = input.disabled;
            panel.querySelectorAll("[data-level]").forEach(el => {
                if (document.activeElement !== el) el.value = settings[channel].levels[Number(el.dataset.level)];
            });
            panel.querySelector('[data-curve="undo"]').disabled = !undo.length || !!pending;
            panel.querySelector('[data-curve="redo"]').disabled = !redo.length || !!pending;
            panel.querySelector('[data-curve="apply"]').disabled = !raw || !hash || !contextReady || !changed() || !!pending;
            defaultCheck.disabled = !contextReady || !!pending || !fiboDefault.eligible ||
                (!changed() && !fiboDefault.available && !fiboDefault.can_capture);
            defaultHint.textContent = !fiboDefault.eligible ? "Fibo whole-image edits only." :
                defaultCheck.checked ? "Saved for future unpainted Fibo edits. Apply also saves later curve changes." :
                "Save this correction for future unpainted Fibo edits. Qwen and painted edits are unaffected.";
        }
        function draw() {
            const size = graph.width, pad = 12, span = size - 2 * pad;
            ctx.clearRect(0, 0, size, size); ctx.fillStyle = "#14171d"; ctx.fillRect(0, 0, size, size);
            if (histogram) {
                const bins = histogram[channel], max = Math.max(1, ...bins);
                ctx.fillStyle = colors[channel] + "36"; ctx.beginPath(); ctx.moveTo(pad, size - pad);
                for (let i = 0; i < 256; i++) ctx.lineTo(pad + i / 255 * span, size - pad - Math.sqrt(bins[i] / max) * span * .92);
                ctx.lineTo(size - pad, size - pad); ctx.closePath(); ctx.fill();
            }
            ctx.strokeStyle = "#383d48"; ctx.lineWidth = 1; ctx.beginPath();
            for (let i = 0; i <= 4; i++) {
                const p = pad + span * i / 4;
                ctx.moveTo(p, pad); ctx.lineTo(p, size - pad); ctx.moveTo(pad, p); ctx.lineTo(size - pad, p);
            }
            ctx.stroke(); ctx.setLineDash([3, 4]); ctx.beginPath();
            ctx.moveTo(pad, size - pad); ctx.lineTo(size - pad, pad); ctx.stroke(); ctx.setLineDash([]);
            const curve = C.table({...settings[channel], levels: [0, 1, 255, 0, 255]});
            ctx.strokeStyle = colors[channel]; ctx.lineWidth = 2; ctx.beginPath();
            curve.forEach((y, x) => { const a = pad + x / 255 * span, b = size - pad - y / 255 * span; x ? ctx.lineTo(a, b) : ctx.moveTo(a, b); }); ctx.stroke();
            settings[channel].points.forEach(([x, y], index) => {
                ctx.beginPath(); ctx.arc(pad + x / 255 * span, size - pad - y / 255 * span, index === selected ? 5 : 3.5, 0, Math.PI * 2);
                ctx.fillStyle = index === selected ? "#fff" : colors[channel]; ctx.fill();
                ctx.strokeStyle = "#111318"; ctx.lineWidth = 1; ctx.stroke();
            });
        }
        function render() {
            pendingFrame = 0;
            if (raw && contextReady) preview.getContext("2d").putImageData(new ImageData(C.apply(raw.data, luts, mask), raw.width, raw.height), 0, 0);
            visibility();
        }
        function update() {
            luts = C.compile(settings); controls(); draw();
            if (!pendingFrame) pendingFrame = requestAnimationFrame(render);
        }
        function pointAt(event) {
            const rect = graph.getBoundingClientRect();
            return [Math.round(C.clamp(((event.clientX - rect.left) / rect.width * 280 - 12) / 256 * 255)),
                Math.round(C.clamp((268 - (event.clientY - rect.top) / rect.height * 280) / 256 * 255))];
        }
        function movePoint(x, y) {
            const points = settings[channel].points;
            if (selected === 0) x = 0;
            else if (selected === points.length - 1) x = 255;
            else x = C.clamp(x, points[selected - 1][0] + 1, points[selected + 1][0] - 1);
            points[selected] = [Math.round(x), Math.round(C.clamp(y))]; update();
        }
        graph.addEventListener("pointerdown", event => {
            if (pending || event.button !== 0) return;
            event.preventDefault(); graph.focus();
            const [x, y] = pointAt(event), points = settings[channel].points;
            const nearest = points.map(([px, py], i) => [Math.hypot(px - x, py - y), i]).sort((a, b) => a[0] - b[0])[0];
            remember();
            if (nearest[0] <= 14) selected = nearest[1];
            else if (points.length < 16 && x > 0 && x < 255 && !points.some(p => p[0] === x)) {
                points.push([x, y]); points.sort((a, b) => a[0] - b[0]); selected = points.findIndex(p => p[0] === x);
            } else { undo.pop(); return; }
            dragging = true; graph.setPointerCapture(event.pointerId); update();
        });
        graph.addEventListener("pointermove", event => { if (dragging && !pending) movePoint(...pointAt(event)); });
        for (const type of ["pointerup", "pointercancel", "lostpointercapture"]) graph.addEventListener(type, () => { dragging = false; });
        function deletePoint() {
            if (selected === 0 || selected === settings[channel].points.length - 1) return;
            remember(); settings[channel].points.splice(selected, 1); selected--; update();
        }
        graph.addEventListener("keydown", event => {
            if (pending) return;
            if (["Delete", "Backspace"].includes(event.key)) { event.preventDefault(); deletePoint(); }
            else if (event.key.startsWith("Arrow")) {
                event.preventDefault(); event.stopPropagation(); remember();
                const [x, y] = settings[channel].points[selected], step = event.shiftKey ? 10 : 1;
                movePoint(x + (event.key === "ArrowRight" ? step : event.key === "ArrowLeft" ? -step : 0),
                    y + (event.key === "ArrowUp" ? step : event.key === "ArrowDown" ? -step : 0));
            }
        });
        for (const field of [input, output]) field.addEventListener("change", () => {
            if (pending || !Number.isFinite(field.valueAsNumber)) return;
            remember(); movePoint(input.valueAsNumber, output.valueAsNumber);
        });
        channelSelect.addEventListener("change", () => { channel = channelSelect.value; selected = 0; controls(); draw(); });
        previewCheck.addEventListener("change", visibility);
        defaultCheck.addEventListener("change", () => {
            const field = gradioApp().querySelector("#image_edit_curves_request textarea");
            if (!field || pending || !contextReady) { defaultCheck.checked = fiboDefault.enabled; return; }
            const id = crypto.randomUUID();
            pending = {id, op: "fibo_default"}; window.imageEditCurvesBusy = true;
            field.value = JSON.stringify({version: 1, id, op: "fibo_default", enabled: defaultCheck.checked,
                base_sha256: hash, settings, luts});
            updateInput(field); status.textContent = "Saving Fibo default…"; controls();
        });
        panel.querySelectorAll("[data-level]").forEach(field => {
            field.addEventListener("input", () => {
                if (pending || !Number.isFinite(field.valueAsNumber)) return;
                const index = Number(field.dataset.level), levels = settings[channel].levels;
                remember();
                const bounds = [[0, levels[2] - 1], [.1, 10], [levels[0] + 1, 255], [0, levels[4]], [levels[3], 255]][index];
                levels[index] = C.clamp(field.valueAsNumber, ...bounds); update();
            });
            field.addEventListener("blur", () => { field.value = settings[channel].levels[Number(field.dataset.level)]; });
        });
        panel.addEventListener("click", event => {
            const action = event.target.closest("[data-curve]")?.dataset.curve;
            if (!action || pending) return;
            if (action === "apply") { save(false); return; }
            if (action === "delete") { deletePoint(); return; }
            if (action === "undo" && undo.length) { redo.push(C.clone(settings)); settings = undo.pop(); }
            if (action === "redo" && redo.length) { undo.push(C.clone(settings)); settings = redo.pop(); }
            if (action === "reset-channel") { remember(); settings[channel] = C.defaults()[channel]; }
            if (action === "reset-all") { remember(); settings = C.defaults(); }
            selected = 0; update();
        });
        async function loadPixels() {
            if (raw || loadPromise) return loadPromise;
            const token = loadVersion, url = downloadUrl || currentUrl;
            loadPromise = (async () => {
                const response = await fetch(url, {credentials: "same-origin", signal: AbortSignal.timeout(30000)});
                if (!response.ok) throw new Error("Could not load the full-resolution result.");
                const blob = await response.blob(), bytes = await blob.arrayBuffer();
                const digest = await crypto.subtle.digest("SHA-256", bytes);
                const bitmap = await createImageBitmap(blob);
                if (token !== loadVersion) { bitmap.close(); return; }
                hash = Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, "0")).join("");
                const factor = Math.min(1, 2048 / Math.max(bitmap.width, bitmap.height));
                preview.width = Math.round(bitmap.width * factor); preview.height = Math.round(bitmap.height * factor);
                const context = preview.getContext("2d", {willReadFrequently: true});
                context.drawImage(bitmap, 0, 0, preview.width, preview.height); bitmap.close();
                raw = context.getImageData(0, 0, preview.width, preview.height);
                const field = gradioApp().querySelector("#image_edit_curves_request textarea");
                if (!field) throw new Error("Reload Forge's UI to enable curves.");
                contextId = crypto.randomUUID();
                field.value = JSON.stringify({version: 1, id: contextId, op: "context", base_sha256: hash});
                updateInput(field);
                status.textContent = "Loading adjustment area…";
                update();
            })().catch(error => { if (token === loadVersion) { loadError = error.message; status.textContent = loadError; } });
            return loadPromise;
        }
        async function save(downloadAfter) {
            if (pending || !changed()) return false;
            await loadPixels();
            if (!raw || !hash || !contextReady) { status.textContent = loadError || "The result or selection is still loading."; return true; }
            const field = gradioApp().querySelector("#image_edit_curves_request textarea");
            if (!field) { status.textContent = "Reload Forge's UI to enable saving curves."; return true; }
            const id = crypto.randomUUID();
            pending = {id, downloadAfter, oldDownload: downloadUrl}; window.imageEditCurvesBusy = true;
            field.value = JSON.stringify({version: 1, id, base_sha256: hash, settings, luts,
                use_fibo_default: fiboDefault.eligible && defaultCheck.checked});
            updateInput(field); status.textContent = "Saving full-resolution PNG…"; controls();
            return true;
        }
        const controller = {
            open(url, savedUrl) {
                if (currentUrl === url && downloadUrl === savedUrl) return;
                currentUrl = url; downloadUrl = savedUrl; loadVersion++; loadPromise = null; loadError = "";
                raw = histogram = mask = null; contextId = null; contextReady = false; hash = "";
                fiboDefault = {eligible: false, enabled: false, available: false, can_capture: false};
                defaultCheck.checked = false;
                scopeLabel.textContent = "Loading adjustment area…";
                settings = C.defaults(); undo = []; redo = []; selected = 0;
                previewCheck.checked = true; update();
                if (!panel.hidden) { status.textContent = "Loading result…"; loadPixels(); }
            },
            toggle() {
                panel.hidden = !panel.hidden;
                dialog.querySelector('[data-action="curves"]').setAttribute("aria-pressed", String(!panel.hidden));
                if (!panel.hidden) { callbacks.selectEdited(); loadPixels(); }
                callbacks.layoutChanged();
            },
            compare(value) { original = value; visibility(); },
            async download(event) {
                if (pending || changed()) { event.preventDefault(); if (!pending) await save(true); }
            },
            async completed(receipt) {
                let data; try { data = JSON.parse(receipt); } catch { return; }
                if (contextId && data.id === contextId) {
                    const token = loadVersion;
                    contextId = null;
                    if (!data.ok) { loadError = data.error; status.textContent = loadError; scopeLabel.textContent = "Selection unavailable"; controls(); return; }
                    if (data.mask) {
                        try {
                            const blob = await (await fetch(data.mask)).blob();
                            const bitmap = await createImageBitmap(blob);
                            if (token !== loadVersion) { bitmap.close(); return; }
                            const canvas = document.createElement("canvas"); canvas.width = raw.width; canvas.height = raw.height;
                            const context = canvas.getContext("2d"); context.drawImage(bitmap, 0, 0, canvas.width, canvas.height); bitmap.close();
                            const bytes = context.getImageData(0, 0, canvas.width, canvas.height).data;
                            mask = new Uint8ClampedArray(raw.width * raw.height);
                            for (let i = 0; i < mask.length; i++) mask[i] = bytes[i * 4];
                        } catch { status.textContent = "The painted selection could not be loaded."; controls(); return; }
                    }
                    if (token !== loadVersion) return;
                    contextReady = true; scopeLabel.textContent = data.scope;
                    fiboDefault = data.fibo_default || {eligible: false, enabled: false, available: false, can_capture: false};
                    defaultCheck.checked = fiboDefault.eligible && fiboDefault.enabled;
                    status.textContent = mask ? "Only the painted area changes. Outside pixels stay exact." : "The whole image is adjusted. Apply keeps the previous file.";
                    histogram = Object.fromEntries(C.channels.map(name => [name, new Array(256).fill(0)]));
                    for (let i = 0; i < raw.data.length; i += 4) if (raw.data[i + 3] && (!mask || mask[i / 4])) {
                        C.channels.slice(1).forEach((name, c) => { histogram[name][raw.data[i + c]]++; histogram.rgb[raw.data[i + c]]++; });
                    }
                    update(); return;
                }
                if (!pending || data.id !== pending.id) return;
                const done = pending; pending = null; window.imageEditCurvesBusy = false;
                if (!data.ok) { defaultCheck.checked = fiboDefault.eligible && fiboDefault.enabled; status.textContent = data.error || "Could not save curves."; controls(); return; }
                if (done.op === "fibo_default") {
                    fiboDefault.enabled = data.enabled; fiboDefault.available = data.available;
                    defaultCheck.checked = data.enabled;
                    status.textContent = data.enabled ? "Default saved. Apply to result saves this preview too." : "Fibo default disabled. The saved image is unchanged.";
                    controls(); return;
                }
                let link, image;
                for (let i = 0; i < 30; i++) {
                    link = gradioApp().querySelector("#image_edit_download_data a[href]");
                    image = gradioApp().querySelector("#qwen_edit_result img");
                    if (link?.href && link.href !== done.oldDownload && image?.src && image.src !== currentUrl) break;
                    await new Promise(resolve => setTimeout(resolve, 100));
                }
                if (image?.src && link?.href && link.href !== done.oldDownload) {
                    callbacks.applied(image.currentSrc || image.src, link.href);
                    status.textContent = "Saved. The corrected image is now the result.";
                    if (done.downloadAfter) { const a = document.createElement("a"); a.href = link.href; a.download = ""; document.body.appendChild(a); a.click(); a.remove(); }
                } else status.textContent = "Saved. Close the viewer to use the updated result.";
                controls();
            }
        };
        window.imageEditCurvesSaved = receipt => controller.completed(receipt);
        update();
        return controller;
    };
})();
