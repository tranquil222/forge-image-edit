const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function harness({ existing = false, status = 200, recipe = false } = {}) {
    let ready = !existing;
    const events = [];
    const input = { dispatchEvent: event => events.push(event.type) };
    const recipeInput = {};
    const source = { querySelector(selector) {
        if (selector === 'input[type="file"]') return ready ? input : null;
        return { click() { ready = true; events.push("clear-source"); } };
    } };
    const app = {
        querySelector(selector) {
            if (selector === "#tab_qwen_edit-button") return { click: () => events.push("qwen-tab") };
            if (selector === "#image_edit_handoff textarea") return recipe ? recipeInput : null;
            assert.equal(selector, "#qwen_edit_source");
            return source;
        }
    };
    class Transfer {
        files = [];
        items = { add: file => this.files.push(file) };
    }
    const window = { location: new URL("http://localhost:7860/") };
    class Reader {
        async readAsDataURL(blob) {
            this.result = "data:image/png;base64," + Buffer.from(await blob.arrayBuffer()).toString("base64");
            this.onload();
        }
    }
    const context = { window, document: { addEventListener() {} }, gradioApp: () => app, URL, File, Blob, Event, DataTransfer: Transfer,
        FileReader: Reader, updateInput: field => { assert.equal(field, recipeInput); events.push("recipe-change"); },
        AbortSignal: { timeout: () => undefined }, setTimeout: fn => fn(),
        fetch: async () => ({ ok: status === 200, status, blob: async () => new Blob(["original bytes"], { type: "image/png" }) }) };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../javascript/qwen_edit.js"), "utf8"), context);
    return { send: window.imageEditLoadImage, input, recipeInput, events };
}

test("handoff opens Image Edit and uploads original file bytes", async () => {
    const h = harness();
    await h.send("/infinite_image_browsing/file?path=selected.png", "selected.png");
    assert.deepEqual(h.events, ["qwen-tab", "change"]);
    assert.equal(h.input.files[0].name, "selected.png");
    assert.equal(await h.input.files[0].text(), "original bytes");
});

test("handoff supplies original metadata bytes to the data-only recipe importer", async () => {
    const h = harness({ recipe: true });
    await h.send("/file=source.png");
    assert.deepEqual(h.events, ["qwen-tab", "change", "recipe-change"]);
    assert.equal(Buffer.from(h.recipeInput.value.split(",")[1], "base64").toString(), "original bytes");
});

test("handoff replaces an already loaded source", async () => {
    const h = harness({ existing: true });
    await h.send("/infinite_image_browsing/file?path=next.png", "next.png");
    assert.deepEqual(h.events, ["qwen-tab", "clear-source", "change"]);
    assert.equal(h.input.files[0].name, "next.png");
});

test("failed download and external URL leave existing source untouched", async () => {
    const h = harness({ existing: true, status: 404 });
    await assert.rejects(h.send("/missing.png"), /HTTP 404/);
    await assert.rejects(h.send("https://example.com/image.png"), /this Forge image browser/);
    assert.deepEqual(h.events, []);
});
