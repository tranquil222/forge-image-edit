const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');

function setup() {
    const gallery = { selected: null, preview: null, images: [],
        querySelector(selector) { return selector.startsWith('.thumbnail-item.selected') ? this.selected : this.preview; },
        querySelectorAll() { return this.images; } };
    const received = [], requests = [], replies = [], folder = {value:''}, note = { setAttribute(key,value) { this[key]=value; } };
    const button = { textContent:'Import from txt2img' };
    const doc = { readyState:'loading', addEventListener() {}, querySelector(selector) {
        if (selector === '#txt2img_gallery') return gallery;
        if (selector === '#image_edit_txt2img_import') return button;
        if (selector === '#image_edit_import_status') return note;
        if (selector.startsWith('#image_edit_import_folder')) return folder;
        return null;
    } };
    const window = { location:new URL('http://forge.test/subpath/'),
        imageEditLoadImage:async (url,filename)=>received.push({url,filename}) };
    const fetch = async (url, options) => {
        requests.push({url:String(url),data:JSON.parse(options.body).data});
        const reply = replies.shift() || {error:'No readable saved images found in the txt2img output folder yet.'};
        return {ok:!reply.error,json:async()=>reply};
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../javascript/image_edit_imports.js'),'utf8'), {window,document:doc,URL,fetch,AbortSignal,setTimeout:fn=>{fn();return 0;},clearTimeout(){}});
    return { gallery, received, requests, replies, folder, note, button, window, api:window.ImageEditImports };
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

test('empty folders and external galleries leave the source unchanged', async()=>{
    const h=setup();await h.api.importSelection('txt2img');assert.equal(h.received.length,0);
    h.gallery.selected={getAttribute:()=> 'https://other.test/image.png'};
    await h.api.importSelection('txt2img');assert.equal(h.received.length,0);assert.match(h.note.textContent,/this Forge session/);
});

const saved = (name,cursor) => ({data:[{url:'http://forge.test/subpath/file=C:/outputs/'+name,orig_name:name},cursor]});

test('empty gallery starts newest and advances only after a successful import', async()=>{
    const h=setup();h.replies.push(saved('newest.png','cursor-1'),saved('second.png','cursor-2'));
    await h.api.importSelection('txt2img');await h.api.importSelection('txt2img');
    assert.deepEqual(h.received.map(x=>x.filename),['newest.png','second.png']);
    assert.deepEqual(h.requests.map(x=>x.data),[['',''],['cursor-1','']]);
    assert.equal(h.requests[0].url,'http://forge.test/subpath/run/image_edit_recent_txt2img');
    h.replies.push({error:'No older saved images in the txt2img output folder.'});
    await h.api.importSelection('txt2img');assert.match(h.note.textContent,/No older/);
    assert.equal(h.received.length,2);
    h.replies.push(saved('third.png','cursor-3'));
    const load=h.window.imageEditLoadImage;h.window.imageEditLoadImage=async()=>{throw new Error('Download failed');};
    await h.api.importSelection('txt2img');assert.match(h.note.textContent,/Download failed/);
    h.window.imageEditLoadImage=load;h.replies.push(saved('third.png','cursor-3'));
    await h.api.importSelection('txt2img');
    assert.deepEqual(h.requests.at(-1).data,['cursor-2','']);
    assert.equal(h.received.at(-1).filename,'third.png');
});

test('selected gallery image precedes folder history and a new selection resets it', async()=>{
    const h=setup();h.gallery.images=['one.png','two.png'].map(image);h.gallery.selected=h.gallery.images[1];
    await h.api.importSelection('txt2img');assert.equal(h.requests.length,0);
    h.replies.push(saved('newest.png','first'),saved('older.png','second'));
    await h.api.importSelection('txt2img');await h.api.importSelection('txt2img');
    assert.deepEqual(h.received.map(x=>x.filename),['two.png','newest.png','older.png']);
    h.gallery.selected=h.gallery.images[0];await h.api.importSelection('txt2img');
    assert.equal(h.received.at(-1).filename,'one.png');assert.equal(h.requests.length,2);
    h.replies.push(saved('newest.png','first'));await h.api.importSelection('txt2img');
    assert.deepEqual(h.requests.at(-1).data,['','']);
});

test('random and IIB imports never consume or reset txt2img history', async()=>{
    const h=setup();h.replies.push(saved('newest.png','first'));await h.api.importSelection('txt2img');
    h.replies.push(saved('random.png',null));await h.api.importSelection('random');
    assert.ok(h.requests.at(-1).url.endsWith('/run/image_edit_random_txt2img'));
    assert.deepEqual(h.requests.at(-1).data,['']);
    h.window.ImageEditIIB={currentImage:()=>({url:'/file=current.png',filename:'current.png'})};
    await h.api.importSelection('iib');await h.api.importSelection('iib');
    assert.deepEqual(h.received.slice(-2).map(x=>x.filename),['current.png','current.png']);
    assert.equal(h.requests.length,2);
    h.replies.push(saved('older.png','second'));await h.api.importSelection('txt2img');
    assert.deepEqual(h.requests.at(-1).data,['first','']);
});

test('folder override is sent to both saved-image actions and resets the history', async()=>{
    const h=setup();h.replies.push(saved('newest.png','first'));await h.api.importSelection('txt2img');
    h.folder.value='  C:/custom folder  ';h.replies.push(saved('custom.png','custom-first'));
    await h.api.importSelection('txt2img');assert.deepEqual(h.requests.at(-1).data,['','C:/custom folder']);
    h.replies.push(saved('random.png',null));await h.api.importSelection('random');
    assert.deepEqual(h.requests.at(-1).data,['C:/custom folder']);
});
