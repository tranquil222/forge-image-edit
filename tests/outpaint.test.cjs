const test = require('node:test');
const assert = require('node:assert/strict');
const {plan} = require('../javascript/image_edit_outpaint.js');
test('signed-edge preview matches crop and mixed expansion geometry without changing source size', () => {
    assert.deepEqual(plan(80, 60, {left:-10,right:30,top:20,bottom:-15}),
        {width:100,height:65,left:-10,top:20,box:[10,0,80,45],fitWidth:110,fitHeight:80});
    const cropped=plan(100,80,{left:-5,right:-15,top:-10,bottom:-20});
    assert.equal(cropped.width,80);assert.equal(cropped.height,50);
    assert.deepEqual(cropped.box,[5,10,85,60]);
    assert.equal(cropped.fitWidth,100);assert.equal(cropped.fitHeight,80);
});
test('preview rejects empty, fractional and excessive canvases', () => {
    for(const edges of [{left:-100},{left:-60,right:-60},{left:.5},{left:17000}]) assert.equal(plan(100,80,edges),null);
    assert.equal(plan(8000,8000,{left:1}),null);
});
