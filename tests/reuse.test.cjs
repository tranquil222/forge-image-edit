const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function harness({status=200, decodeFails=false, busy=false}={}) {
    const button={}, note={}, loads=[], requests=[];
    const window={location:new URL('http://localhost:7860/'), imageEditCurvesBusy:busy,
        qwenEditPaintCanvas:{loadImage:(...args)=>loads.push(args)}};
    const nodes={
        '#image_edit_reuse_result':button, '#image_edit_reuse_error':note,
        '#qwen_edit_result img':{src:'http://localhost:7860/file=original.png'}
    };
    const edges=[48,0,-32,16].map(value=>({value:String(value),events:[],dispatchEvent(event){this.events.push(event.type)}}));
    ['left','right','top','bottom'].forEach((edge,i)=>{nodes[`#image_edit_canvas_${edge} input[type="number"]`]=edges[i]});
    class Reader {
        async readAsDataURL(blob){this.result='data:image/png;base64,'+Buffer.from(await blob.arrayBuffer()).toString('base64');this.onload()}
    }
    class Image { async decode(){if(decodeFails)throw new Error('Broken image')} }
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../javascript/qwen_edit.js'),'utf8'),{
        window, document:{addEventListener(){}}, gradioApp:()=>({querySelector:s=>nodes[s]}),
        URL, Event, FileReader:Reader, Image, AbortSignal:{timeout:()=>undefined},
        fetch:async url=>{requests.push(url);return {ok:status===200,status,blob:async()=>new Blob(['original bytes + metadata'],{type:'image/png'})}}
    });
    return {use:window.imageEditUseResultAsSource,button,note,loads,requests,window,edges};
}

test('reuse uses original saved bytes without importing a recipe or calling a generation API',async()=>{
    const h=harness();await h.use();
    assert.deepEqual(h.requests,['http://localhost:7860/file=original.png']);
    assert.equal(Buffer.from(h.loads[0][0].split(',')[1],'base64').toString(),'original bytes + metadata');
    assert.equal(h.loads[0][1],true);
    assert.equal(h.button.disabled,false);assert.equal(h.note.hidden,true);
});
test('repeated reuse forces a canvas reset even for the same result',async()=>{
    const h=harness();await h.use();h.edges[0].value='64';await h.use();
    assert.equal(h.loads.length,2);assert.equal(h.loads[0][0],h.loads[1][0]);
    assert.equal(h.loads[1][1],true);
    assert.deepEqual(h.edges.map(e=>e.value),['0','0','0','0']);
    assert.deepEqual(h.edges[0].events,['input','change','input','change']);
    assert.deepEqual(h.edges[1].events,[]);
    assert.deepEqual(h.edges[2].events,['input','change']);
});
test('failed download, damaged image and unfinished curves preserve the current source and show an error',async()=>{
    for(const options of [{status:404},{decodeFails:true},{busy:true}]){
        const h=harness(options);await h.use();
        assert.equal(h.loads.length,0);assert.equal(h.note.hidden,false);assert.ok(h.note.textContent);
        assert.equal(h.button.disabled,false);assert.equal(h.window.imageEditReusingResult,false);
        assert.deepEqual(h.edges.map(e=>e.value),['48','0','-32','16']);
    }
});
test('displayed full-resolution result is used and overlapping clicks do not start duplicate transfers',async()=>{
    const h=harness();await Promise.all([h.use(),h.use()]);
    assert.equal(h.requests.length,1);assert.equal(h.loads.length,1);
    assert.equal(h.requests[0],'http://localhost:7860/file=original.png');
});
