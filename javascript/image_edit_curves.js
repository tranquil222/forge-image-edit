// Small, local RGB curves/levels engine. No model calls or network dependencies.
(function(root) {
    const channels = ["rgb", "red", "green", "blue"];
    const clone = value => JSON.parse(JSON.stringify(value));
    const clamp = (x, low = 0, high = 255) => Math.max(low, Math.min(high, x));
    function defaults() {
        return Object.fromEntries(channels.map(name => [name, { points: [[0, 0], [255, 255]], levels: [0, 1, 255, 0, 255] }]));
    }
    function table(channel) {
        const Spline = typeof module !== "undefined" && module.exports ? require("./image_edit_spline.js") : root.ImageEditSpline;
        const spline = new Spline(clone(channel.points));
        const [black, gamma, white, low, high] = channel.levels;
        return Array.from({ length: 256 }, (_, value) => {
            const level = low + Math.pow(clamp((value - black) / (white - black), 0, 1), 1 / gamma) * (high - low);
            return Math.round(clamp(spline.interpolate(level)));
        });
    }
    function compile(settings) {
        const master = table(settings.rgb);
        return channels.slice(1).map(name => {
            const lut = table(settings[name]);
            return master.map(value => lut[value]);
        });
    }
    function apply(source, luts, mask = null) {
        const result = new Uint8ClampedArray(source);
        for (let i = 0; i < result.length; i += 4) {
            const alpha = mask ? mask[i / 4] : 255;
            for (let c = 0; c < 3; c++) result[i + c] = Math.floor((luts[c][source[i + c]] * alpha + source[i + c] * (255 - alpha) + 127) / 255);
        }
        return result;
    }
    function identity(luts) { return luts.every(lut => lut.every((value, index) => value === index)); }
    const api = { channels, clone, clamp, defaults, table, compile, apply, identity };
    if (typeof module !== "undefined" && module.exports) module.exports = api;
    else root.ImageEditCurves = api;
})(typeof window === "undefined" ? globalThis : window);
