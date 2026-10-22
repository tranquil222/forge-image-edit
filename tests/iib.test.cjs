const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function bridge({ frames = [], load } = {}) {
    const context = {
        window: { location: new URL('https://forge.test/subpath/'), imageEditLoadImage: load }, URL,
        document: { readyState: 'loading', addEventListener() {}, querySelectorAll: () => frames, querySelector: () => null },
        setTimeout: fn => { fn(); return 0; }, clearTimeout() {},
    };
    const code = fs.readFileSync(path.join(__dirname, '../javascript/image_edit_iib.js'), 'utf8');
    vm.runInNewContext(code, context);
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../javascript/image_edit_imports.js'), 'utf8'), context);
    return { context, code, api: context.window.ImageEditIIB };
}

test('IIB thumbnails and previews resolve to original bytes, retaining the WebUI subpath', () => {
    const { api } = bridge();
    for (const endpoint of ['image-thumbnail', 'img/test.png', 'file']) {
        const result = api.originalImage(`/subpath/infinite_image_browsing/${endpoint}?path=${encodeURIComponent('C:\\images\\name #1 + ü.PNG')}&size=512x512&t=123&disposition=small.png`);
        assert.equal(result.filename, 'name #1 + ü.PNG');
        const url = new URL(result.url);
        assert.equal(url.pathname, '/subpath/infinite_image_browsing/file');
        assert.equal(url.searchParams.get('path'), 'C:\\images\\name #1 + ü.PNG');
        assert.equal(url.searchParams.get('t'), '123');
        assert.equal(url.searchParams.has('size'), false);
        assert.equal(url.searchParams.has('disposition'), false);
    }
});

test('IIB bridge ignores remote URLs, unrelated endpoints, videos and missing paths', () => {
    const { api } = bridge();
    for (const url of [
        'https://other.test/infinite_image_browsing/file?path=x.png',
        '/file=x.png', '/infinite_image_browsing/file',
        '/infinite_image_browsing/video_cover?path=video.mp4',
        '/infinite_image_browsing/image-thumbnail?path=video.mp4',
        '/infinite_image_browsing/file?path=folder',
        '/infinite_image_browsing/delete_files?path=x.png',
        'data:image/png;base64,abc', undefined,
    ]) assert.equal(api.originalImage(url), null);
});

test('IIB bridge retains the existing installation if scripts are loaded twice', () => {
    const { api, code, context } = bridge();
    vm.runInNewContext(code, context);
    assert.equal(context.window.ImageEditIIB, api);
});

test('IIB bridge is a quiet no-op when IIB is not installed', () => {
    const {api,context}=bridge();
    assert.equal(api.currentImage(),null);
    assert.doesNotThrow(() => context.window.ImageEditImports.refresh());
});

function lightbox(src = '/subpath/infinite_image_browsing/img/test.png?path=first.png&size=512x512') {
    const wrap = { isConnected: true, parentElement: null, style: {}, getAttribute: () => null };
    const image = { isConnected: true, parentElement: wrap, style: {}, src,
        currentSrc: '/subpath/infinite_image_browsing/img/test.png?path=old.png',
        getAttribute(name) { return name === 'src' ? this.src : null; },
        getClientRects() { throw new Error('Host tab is hidden: layout rects must not be used'); } };
    const doc = { body: {}, baseURI: 'https://forge.test/subpath/infinite_image_browsing/',
        defaultView: { getComputedStyle: node => node.style }, querySelectorAll: () => [image] };
    image.ownerDocument = wrap.ownerDocument = doc;
    return { doc, image, wrap };
}

test('imports the current lightbox even when its host tab has no layout', () => {
    const box = lightbox(), { api } = bridge({ frames: [{ contentDocument: box.doc }] });
    assert.equal(api.currentImage().filename, 'first.png');
    box.image.src = '/subpath/infinite_image_browsing/image-thumbnail?path=second%20%2B%20%C3%BC.png&size=64';
    assert.equal(api.currentImage().filename, 'second + ü.png');
    assert.equal(new URL(api.currentImage().url).pathname, '/subpath/infinite_image_browsing/file');
});

test('closed lightboxes are not imported and reopening/reloading does not retain a stale image', () => {
    const box = lightbox(), frame = { contentDocument: box.doc }, { api } = bridge({ frames: [frame] });
    assert.ok(api.currentImage());
    box.wrap.style.display = 'none';
    assert.equal(api.currentImage(), null);
    box.wrap.style.display = '';
    box.wrap.getAttribute = name => name === 'aria-hidden' ? 'true' : null;
    assert.equal(api.currentImage(), null);
    frame.contentDocument = lightbox('/subpath/infinite_image_browsing/file?path=new.png').doc;
    assert.equal(api.currentImage().filename, 'new.png');
});

test('unrelated/cross-origin frames are ignored; ambiguous lightboxes are not guessed', () => {
    const inaccessible = { get contentDocument() { throw new Error('Blocked'); } };
    const first = { contentDocument: lightbox().doc }, second = { contentDocument: lightbox('/subpath/infinite_image_browsing/file?path=other.png').doc };
    assert.equal(bridge({ frames: [inaccessible, first] }).api.currentImage().filename, 'first.png');
    assert.throws(() => bridge({ frames: [first, second] }).api.currentImage(), /More than one/);
});

test('import is explicit, duplicate clicks are ignored, and failures are recoverable', async () => {
    const box = lightbox(); let finish, attempts = 0;
    const { api, context } = bridge({ frames: [{ contentDocument: box.doc }], load: async () => {
        attempts++; await new Promise(resolve => { finish = resolve; });
    } });
    const button = { textContent: 'Import', disabled: false };
    const note = { hidden: true, setAttribute(key, value) { this[key] = value; } };
    context.document.querySelector = selector => selector.endsWith('_import') ? button : note;
    const importCurrent = () => context.window.ImageEditImports.importSelection('iib');
    assert.equal(attempts, 0);
    const job = importCurrent();
    await importCurrent();
    assert.equal(attempts, 1); assert.equal(button.disabled, true);
    finish(); await job;
    assert.equal(button.disabled, false); assert.equal(button.textContent, 'Import');
    assert.match(note.textContent, /first.png with its embedded metadata/);
    context.window.imageEditLoadImage = async () => { throw new Error('HTTP 404'); };
    assert.equal(await importCurrent(), null); assert.equal(note.role, 'alert');
    assert.match(note.textContent, /HTTP 404/); assert.equal(button.disabled, false);
    box.wrap.style.display = 'none';
    assert.equal(await importCurrent(), null); assert.match(note.textContent, /leave it open/);
});
