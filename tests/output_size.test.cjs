const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const {linkedSize, canvasSize} = require('../javascript/image_edit_output_size.js');

test('linked dimensions use the edited edge and the current source ratio', () => {
    assert.deepEqual(linkedSize(500, 1024, 1024, 'width'), [500, 500]);
    assert.deepEqual(linkedSize(500, 1024, 1280, 'height'), [400, 500]);
    assert.deepEqual(linkedSize(777, 1024, 1280, 'width'), [777, 971]);
    for (const value of ['', NaN, 0, 5000]) assert.equal(linkedSize(value, 1024, 1280, 'width'), null);
    assert.equal(linkedSize(4096, 1024, 1280, 'width'), null);
});

test('rapid alternating edits stay linked and immediate submission uses the last edge', () => {
    let onInput, onUpdate;
    const fields = Object.fromEntries(['width', 'height'].map(axis => [axis, {
        value: '1024', type: 'number',
        closest: selector => selector === '#image_edit_output_' + axis,
        dispatchEvent: () => onInput({target: fields[axis]}),
    }]));
    const window = {qwenEditPaintCanvas: {img: 'source', orgWidth: 1024, orgHeight: 1024}};
    const crop = {checked: false}, custom = {checked: false, click() { this.checked = !this.checked; }};
    const edges = {left: {value: 0}};
    const document = {addEventListener: (type, fn) => { if (type === 'input') onInput = fn; }, querySelectorAll: () => [],
        querySelector: selector => selector.includes('_width ') ? fields.width : selector.includes('_height ') ? fields.height :
            selector.includes('_canvas_enabled ') ? crop : selector.includes('_output_size_enabled ') ? custom : selector.includes('_canvas_left ') ? edges.left : null};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../javascript/image_edit_output_size.js'), 'utf8'), {window, document, Event: class {}, onUiUpdate: fn => { onUpdate = fn; }});
    onUpdate();
    for (let value = 900; value >= 500; value--) {
        const axis = value % 2 ? 'height' : 'width';
        fields[axis].value = String(value); onInput({target: fields[axis]});
        assert.equal(Number(fields.width.value), value);
        assert.equal(Number(fields.height.value), value);
    }
    const args = Array(41).fill(null); args[36] = true; args[37] = 'Resize to'; args[38] = 900; args[39] = 700;
    window.ImageEditOutputSize.submit(args);
    assert.deepEqual(args.slice(38, 40), [500, 500]);
    window.qwenEditPaintCanvas.orgHeight = 1280;
    fields.height.value = '750'; onInput({target: fields.height});
    assert.equal(Number(fields.width.value), 600);
    window.ImageEditOutputSize.submit(args);
    assert.deepEqual(args.slice(38, 40), [600, 750]);
    assert.equal(custom.checked, true, 'editing a dimension enables the override');
    onUpdate(); crop.checked = true; edges.left.value = 256; onUpdate();
    assert.equal(Number(fields.width.value), Number(fields.height.value), 'expanded canvas uses its own square ratio');
    args[23] = true; args[38] = 42; window.ImageEditOutputSize.submit(args);
    assert.equal(args[38], args[39], 'canvas generation submits linked dimensions');
    const cropArgs = Array(14).fill(null); cropArgs[9] = true; cropArgs[10] = 'Resize to';
    window.ImageEditOutputSize.cropSubmit(cropArgs);
    assert.equal(cropArgs[11], cropArgs[12], 'crop-only submit uses the same sizing');
    args[23] = false; args[15] = true; args[38] = 42; window.ImageEditOutputSize.submit(args);
    assert.equal(args[38], 42, 'ordinary painted edits keep their source canvas');
});

test('resize geometry includes positive and negative edges only when canvas mode is enabled', () => {
    assert.deepEqual(canvasSize(500, 800, false, {left: 300}), [500, 800]);
    assert.deepEqual(canvasSize(500, 800, true, {left: 300, top: -100}), [800, 700]);
    assert.equal(canvasSize(500, 800, true, {left: -500}), null);
});
