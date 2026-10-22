const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');

function setup() {
    const gallery = { selected: null, preview: null, images: [],
        querySelector(selector) { return selector.startsWith('.thumbnail-item.selected') ? this.selected : this.preview; },
        querySelectorAll() { return this.images; } };
    const received = [], note = { setAttribute(key,value) { this[key]=value; } };
    const button = { textContent:'Import from txt2img' };
    const doc = { readyState:'loading', addEventListener() {}, querySelector(selector) {
        if (selector === '#txt2img_gallery') return gallery;
        if (selector === '#image_edit_txt2img_import') return button;
        if (selector === '#image_edit_import_status') return note;
        return null;
    } };
    const window = { location:new URL('http://forge.test/subpath/'),
        imageEditLoadImage:async (url,filename)=>received.push({url,filename}) };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../javascript/image_edit_imports.js'),'utf8'), {window,document:doc,URL,setTimeout:fn=>{fn();return 0;},clearTimeout(){}});
    return { gallery, received, note, button, window, api:window.ImageEditImports };
}
const image = name => ({getAttribute:()=>'/subpath/file=C:/outputs/'+encodeURIComponent(name),currentSrc:'/file=stale.png'});

test('txt2img import uses the selected thumbnail, not the first batch image or a stale preview', async()=>{
    const h=setup();h.gallery.images=['grid.png','first.png','second + ü.png'].map(image);
    h.gallery.preview=h.gallery.images[1];h.gallery.selected=h.gallery.images[2];
    await h.api.importSelection('txt2img');
    assert.equal(h.received.length,1);assert.equal(h.received[0].filename,'second + ü.png');
    assert.match(h.received[0].url,/second%20%2B%20%C3%BC.png/);
    assert.equal(h.button.textContent,'Import from txt2img');
});

test('single-image and detailed-preview galleries work; an unselected batch is not guessed', async()=>{
    const h=setup();
    h.gallery.images=[image('only.png')];assert.equal(h.api.txt2imgSource().filename,'only.png');
    h.gallery.images.push(image('other.png'));assert.equal(h.api.txt2imgSource(),null);
    await h.api.importSelection('txt2img');assert.equal(h.received.length,0);assert.match(h.note.textContent,/Select an image/);
    h.gallery.preview=h.gallery.images[1];assert.equal(h.api.txt2imgSource().filename,'other.png');
});

test('empty and external galleries leave the source unchanged', async()=>{
    const h=setup();await h.api.importSelection('txt2img');assert.equal(h.received.length,0);
    h.gallery.selected={getAttribute:()=> 'https://other.test/image.png'};
    await h.api.importSelection('txt2img');assert.equal(h.received.length,0);assert.match(h.note.textContent,/this Forge session/);
});
