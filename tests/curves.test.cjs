const test = require('node:test');
const assert = require('node:assert/strict');
const C = require('../javascript/image_edit_curves.js');

test('identity curves preserve every RGB value and alpha, including transparent pixels', () => {
    const source = Uint8ClampedArray.from(Array.from({length: 256}, (_, i) => [i, 255 - i, i, i]).flat());
    const luts = C.compile(C.defaults());
    assert.ok(C.identity(luts));
    assert.deepEqual(C.apply(source, luts), source);
});

test('master curve and channel levels compose without changing other channels', () => {
    const settings = C.defaults();
    settings.rgb.points = [[0, 0], [128, 160], [255, 255]];
    settings.red.levels[1] = 2;
    const luts = C.compile(settings);
    assert.equal(luts[1][128], 160); assert.equal(luts[2][128], 160);
    assert.ok(luts[0][128] > 160);
    const raw = new Uint8ClampedArray([128, 128, 128, 97]);
    const preview = C.apply(raw, luts);
    assert.deepEqual(Array.from(preview), [luts[0][128], 160, 160, 97]);
    // Rendering again starts from the immutable base, not the previous preview.
    assert.deepEqual(C.apply(raw, luts), preview);
    assert.deepEqual(Array.from(raw), [128, 128, 128, 97]);
});

test('painted support is exact and feather blending matches Pillow integer rounding', () => {
    const raw = new Uint8ClampedArray([100, 120, 130, 80, 100, 120, 130, 150, 100, 120, 130, 255]);
    const luts = [0, 1, 2].map(() => Array.from({length: 256}, (_, i) => Math.min(255, i + 50)));
    const out = C.apply(raw, luts, new Uint8ClampedArray([0, 128, 255]));
    assert.deepEqual(Array.from(out), [100, 120, 130, 80, 125, 145, 155, 150, 150, 170, 180, 255]);
});

test('endpoint changes and resets stay bounded and independent per channel', () => {
    const settings = C.defaults(); settings.blue.points = [[0, 30], [50, 20], [160, 230], [255, 240]];
    const luts = C.compile(settings);
    assert.ok(luts.flat().every(n => Number.isInteger(n) && n >= 0 && n <= 255));
    assert.equal(luts[2][0], 30); assert.equal(luts[2][255], 240);
    assert.equal(luts[0][64], 64); assert.equal(luts[1][64], 64);
    settings.blue = C.defaults().blue; assert.ok(C.identity(C.compile(settings)));
});
