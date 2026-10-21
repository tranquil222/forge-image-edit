const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const {linkedSize} = require('../javascript/image_edit_output_size.js');

test('linked dimensions use the edited edge and the current source ratio', () => {
    assert.deepEqual(linkedSize(500, 1024, 1024, 'width'), [500, 500]);
    assert.deepEqual(linkedSize(500, 1024, 1280, 'height'), [400, 500]);
    assert.deepEqual(linkedSize(777, 1024, 1280, 'width'), [777, 971]);
    for (const value of ['', NaN, 0, 5000]) assert.equal(linkedSize(value, 1024, 1280, 'width'), null);
    assert.equal(linkedSize(4096, 1024, 1280, 'width'), null);
});

test('rapid alternating edits stay linked and immediate submission uses the last edge', () => {
    let onInput;
    const fields = Object.fromEntries(['width', 'height'].map(axis => [axis, {
        value: '1024', type: 'number',
        closest: selector => selector === '#image_edit_output_' + axis,
        dispatchEvent: () => onInput({target: fields[axis]}),
    }]));
    const window = {qwenEditPaintCanvas: {img: 'source', orgWidth: 1024, orgHeight: 1024}};
    const document = {addEventListener: (_, fn) => { onInput = fn; },
        querySelector: selector => fields[selector.includes('_width ') ? 'width' : 'height']};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../javascript/image_edit_output_size.js'), 'utf8'), {window, document, Event: class {}});
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
    args[23] = true; args[38] = 42; window.ImageEditOutputSize.submit(args);
    assert.equal(args[38], 42, 'canvas sizing is not overwritten');
});
