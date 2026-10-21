const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

test("Gradio's button-wrapped result opens the viewer; compare and zoom use existing images", () => {
    const listeners = new Map();
    const element = () => ({ style: {}, events: {}, addEventListener(type, fn) { this.events[type] = fn; }, setAttribute(name, value) { this[name] = value; } });
    const picture = { ...element(), naturalWidth: 1200, naturalHeight: 800, complete: true };
    const viewport = { ...element(), clientWidth: 1000, clientHeight: 700, scrollLeft: 0, scrollTop: 0,
        querySelector: () => picture, scrollTo(x, y) { this.scrollLeft = x; this.scrollTop = y; } };
    const controls = new Map([
        [".qe-viewer-viewport", viewport], [".qe-viewer-caption", element()], [".qe-viewer-zoom", element()],
        ['[data-action="original"]', element()], ['[data-action="edited"]', element()], [".qe-viewer-download", element()]
    ]);
    const dialog = { ...element(), querySelector: name => controls.get(name), showModal() { this.open = true; }, close() { this.open = false; this.events.close(); } };
    const original = { src: "/source.png" };
    const thumbnail = { src: "/result.png" };
    const button = { querySelector: () => thumbnail };
    const target = { closest(selector) {
        if (selector === "#image_edit_batch_gallery .thumbnail-item") return null;
        if (selector === "#qwen_edit_result") return {};
        if (selector === "img") return thumbnail;
        if (selector === "button") return button;
        if (selector === ".icon-buttons, a") return null;
        throw Error(`Unexpected selector: ${selector}`);
    } };
    const document = { addEventListener: (name, fn) => listeners.set(name, fn), createElement: () => dialog, body: { appendChild() {} } };
    const window = { addEventListener() {} };
    let submittedSource = null;
    const selection = {}, thumbnails = [{}, {}, {}];
    let selectionUpdates = 0;
    const app = { querySelector(selector) {
        if (selector === "#image_edit_batch_source textarea") return submittedSource;
        if (selector === "#image_edit_batch_selection textarea") return selection;
        if (selector === "#qwen_edit_source img") return original;
        if (selector === "#qwen_edit_download a[href]") return { href: "/recipe.png" };
        throw Error(`Unexpected control access: ${selector}`);
    }, querySelectorAll: () => thumbnails };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../javascript/qwen_edit.js"), "utf8"), { window, document, gradioApp: () => app, updateInput: () => selectionUpdates++ });
    listeners.get("click")({ target, preventDefault() {} });
    assert.equal(dialog.open, true);
    assert.equal(picture.src, "/result.png");
    assert.equal(controls.get(".qe-viewer-download").href, "/recipe.png");
    const click = action => dialog.events.click({ target: { closest: () => ({ dataset: { action } }) } });
    click("original");
    assert.equal(picture.src, "/source.png");
    click("edited");
    click("actual");
    assert.equal(picture.style.width, "1200px");
    click("in");
    assert.equal(picture.style.width, "1500px");
    // Different native dimensions must keep one frame and never refit/reset pan.
    viewport.scrollTo(123, 77);
    picture.naturalWidth = 1800; picture.naturalHeight = 1200;
    click("original"); picture.events.load();
    assert.equal(picture.style.width, "1500px");
    assert.equal(picture.style.height, "1000px");
    assert.equal(viewport.scrollLeft, 123); assert.equal(viewport.scrollTop, 77);
    picture.naturalWidth = 1200; picture.naturalHeight = 800;
    click("edited"); picture.events.load();
    assert.equal(picture.style.width, "1500px");
    assert.equal(viewport.scrollLeft, 123); assert.equal(viewport.scrollTop, 77);
    click("close");
    assert.equal(dialog.open, false);
    submittedSource = { value: "data:image/png;base64,submitted-source" };
    original.src = "/different-source.png";
    listeners.get("click")({ target, preventDefault() {} });
    click("original");
    assert.equal(picture.src, submittedSource.value);
    click("close");
    // Thumbnail selection sends an index, never a client-controlled file path.
    listeners.get("click")({ target: { closest: () => thumbnails[1] } });
    assert.equal(JSON.parse(selection.value).index, 1);
    assert.equal(selectionUpdates, 1);
    assert.equal(JSON.parse(selection.value).path, undefined);
});
