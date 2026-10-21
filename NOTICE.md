# Third-party code and model weights

- Forge / Forge Neo and its canvas: AUTOMATIC1111, lllyasviel, Haoming02 and
  contributors; AGPL-3.0. See [LICENSE](LICENSE).
- Fibo transformer and prompt processing adapted from ComfyUI commit
  `e3699a745d513941f17ecbc9a3c58d00fc7768cb`, including contributions in
  [PR 17240](https://github.com/Comfy-Org/ComfyUI/pull/17240); GPL-3.0.
  See [upstream license](licenses/ComfyUI-GPL-3.0.txt). Port modifications use
  Forge's operations, attention and model-management interfaces.
- CyberZiT schedule formula: Cyberdelia/ComfyUI-CyberZiT, MIT; see
  [license](licenses/CyberZiT.txt).
- Optional high-resolution Fibo RoPE settings: [reverentelusarca's 2K workflow](https://huggingface.co/reverentelusarca/fibo-2.0-2K-rope),
  revision `49ad4a3aa3e1b524fd798c8423e2cb7f343f2a65`. X 0.85 / Y 0.80 follows the
  linked node inputs, not the disconnected widget value. Coordinate semantics
  match ComfyUI's `ScaleROPE` and `comfy/ldm/lumina/model.py:pos_ids_x`.
- Curves spline interpolation: Evan Wallace's [glfx.js](https://github.com/evanw/glfx.js),
  MIT, pinned at `86ae72acfffcd50774507eb7b69887ba2493dc35`, `src/core/spline.js`.
  Its original Paint.NET attribution is retained. Only the spline is bundled,
  wrapped under an extension-specific name; no CDN or WebGL dependency is added.
  See [license](licenses/glfx-MIT.txt).

Model weights are **not bundled** and have separate publisher licenses.
See [Fibo](https://huggingface.co/Comfy-Org/Fibo-2.0),
[Bria](https://huggingface.co/briaai/Fibo-2.0-dev), and
[Qwen](https://huggingface.co/Comfy-Org/Qwen-Image-2.1).
Installing this extension does not grant additional rights to model weights.
No ComfyUI server, Gemini key or external image service is used at runtime.
