# Forge Image Edit

Native image-editing workspace for **Forge Neo**. Qwen Image 2.1 (base and
Turbo), Fibo 2.0 Edit Turbo, and optional Fibo 2.0 Dev share one **Image Edit**
tab. Version **0.4.2 beta**. No ComfyUI server or cloud image service.

## Install

Repository URL for **Extensions → Install from URL**:

```text
https://github.com/tranquil222/forge-image-edit.git
```

Installing from this URL adds the editing tab and installs verified backend
support on compatible Forge builds. Model weights are downloaded separately.
See [COMPATIBILITY.md](COMPATIBILITY.md) for supported builds and manual setup.

1. Install this repository through Forge's **Extensions → Install from URL**,
   or put it directly inside `extensions/forge-image-edit/`. Do not nest another
   repository folder inside it. Existing users can keep `extensions/forge-qwen-edit/`;
   do **not** enable both copies.
2. The installer checks the affected backend files, backs them up, and adds
   native model support when they match a verified patch. Existing compatible
   backends are left alone. Other builds get a setup message, not a forced patch.
3. Obtain one model set from [MODELS.md](MODELS.md). Weights are optional,
   downloaded separately, and never bundled or installed on startup.
4. Fully close and relaunch Forge after installation. Refresh the top model list.
5. Choose the checkpoint in Forge's **top Checkpoint** field. Open **Image Edit**
   and click **Use matching encoder / VAE**. This fills an installed compatible
   pair and sets `qwen21` or `fibo2` in **UI Preset**. It never changes the checkpoint.

The installer never runs `git pull`, changes branches, installs Python dependencies,
replaces personal settings, or modifies another extension.
The extension uses Forge's Python environment; don't install a second Torch.
See [validation and limitations](VALIDATION.json) before treating this beta as
compatible with a different Forge fork, GPU, or dependency set.

## Edit

1. Upload the source image and describe the change.
2. Choose a model-appropriate speed/quality preset and resolution.
3. Optionally paint an area or add reference images, then **Generate edit**.
4. Use **Download PNG with recipe** or **Use result as source**.

The **main model bar is the source of truth**. There is no hidden second model
selection in the tab. Missing, incompatible, or extra encoder/VAE selections
block generation and show the required combination. The correction button
selects only a complete installed pair; it does not download or partially fix it.
Retain recognizable publisher filenames so variant/component validation can
identify them; renamed or arbitrary architectures are not inferred from a label.

For **12–16 GB VRAM**, see the [smaller model downloads and settings](MODELS.md#smaller-qwen-download).
Use Forge's normal CPU offloading and turn off Qwen's reference-attention cache.
The optional Qwen Turbo Q4/W4A8 set uses the same model bar and editing controls.
Exact tested combinations and memory-limit methodology are in [VALIDATION.json](VALIDATION.json).

| Model | Default | Other options |
| --- | --- | --- |
| Qwen 2.1 base | Normal: 12 steps | Quick 8; High 16; Extra high 40; Custom |
| Qwen 2.1 Turbo | 8 steps, official schedule, CFG 1 | Custom; official schedule requires 8 Euler steps |
| Fibo Edit Turbo | 4 Euler / Simple steps, CFG 1 | Custom step counts are experimental, not quality upgrades |
| Fibo Dev | 50 Euler / Simple steps, CFG 5 | Preview 30; Custom steps and CFG |

Quality presets never resize the image or secretly switch base/Turbo weights.
The resolution value is approximate square pixel-area equivalence, not a forced
square crop; 0 uses native size. Fibo is trained near 1 MP; 1024 is a useful
starting point. Above 1024 can be expensive. Initial model loading adds latency.
Qwen's reference cache is disabled for Fibo. Negative prompts are inactive at
CFG 1; Dev supports text-only negative conditioning, with the trained null
caption when empty. No LoRA, face restoration, Hires pass or prompt macros run
through this editing path. Instructions are literal.

### Fibo instruction following

Short instructions can miss objects. Be specific about the object and what
should replace it: “Remove the entire inflatable shark toy, including its fins
and tail. Reconstruct the bedding. Keep the person and room unchanged.”
The optional **Describe the finished image** field supplies a native structured
result caption. It does not contact an LLM. Use either that field or your own
structured JSON instruction, not both. More Turbo steps do not guarantee better
instruction following. Dev is a separate optional checkpoint, not a Turbo switch.

### Painted edits

Paint the complete object plus a small border. Scroll to zoom, right-drag to
pan, Shift+paint to erase, F to enlarge, R to fit, Ctrl+Z to undo, W+scroll for
brush size. Changing the source clears the painting and disables painted mode.

- **Fibo:** opaque neutral grey (RGB 128), threshold 128. One masked source is
  sent; extra references are disabled in this mode.
- **Qwen Replace / remove:** opaque green source; no clean source is sent.
- **Qwen Refine / expression:** clean source plus green location guide.

A contextual crop is generated and blended back. Pixels outside the painted
support, including source alpha, remain exactly unchanged. Blending feathers
inward. Resolution controls crop detail; final dimensions stay original.
This is model-specific reference preparation plus compositing, not a guarantee
of seamless repairs. Paint a larger border if necessary.

### Contrast drift and fine texture

**Match source brightness / contrast** optionally reduces global tone drift after
an object edit, for both Qwen and Fibo. It estimates one neutral gain/offset from
mostly unchanged content and applies it without blurring or sharpening. Leave it
off for intentional lighting/contrast changes or major scene changes. It defaults
off; PNG recipes and **Send to Image Edit** retain the setting and recipes record
the applied correction. In painted mode the selected area is excluded from the
estimate, and compositing still keeps outside pixels exact.

Qwen 2.1's stock VAE has a documented fine checkerboard artifact. The optional
[texture-fix VAE](MODELS.md#qwen-21-texture-fix-vae) addresses that decoder artifact;
it is not a Fibo VAE. Neither tone matching nor this decoder guarantees original
fine-detail preservation. Whole-image edits can regenerate texture even when the
instruction names only one object. For exact preservation elsewhere, **paint an
edit area** and work from the original instead of repeatedly editing the output.

## Native saving and metadata

Outputs use Forge's configured **img2img image output directory**, or its shared
output-directory override, through `modules.images.save_image`. Normal filename
patterns, subdirectories, numbering and save callbacks apply. The workspace
saves a PNG so recipes and transparency can be retained. No extension-specific
output folder or machine-specific path is used.

**Keep original metadata** is on by default:

- Original PNG text and supported EXIF/ICC/DPI data are retained.
- `parameters` keeps the original generation information and appends numbered
  **Image Edit** sections containing each edit's generation settings.
- `Image Edit history` records the original metadata and the sequence of edits.
- `image_edit` holds the latest importable recipe: model family, components,
  prompt, steps, CFG, sampler, seed, resolution, masks/crop hashes and description.

Turn it off to omit original metadata and keep only the new edit record.
Forge's global **Write infotext to metadata** setting takes precedence: when
it is off, neither original metadata nor an edit recipe is written.
Reference pixels and painted masks are not embedded. Reproducing a masked edit
requires its source and a newly painted selection. Metadata can identify the
original and subsequent edits; it is not a tamper-proof provenance system.

## Image browser and PNG import

The optional [IIB integration](integrations/README.md) labels its action
**Send to Image Edit**. It transfers original file bytes, then loads an
`image_edit` or legacy `qwen_edit` recipe when present. Ordinary images do not
change generation settings. Missing recipe models give a clear error; no model
is downloaded and no saved workflow path is opened. Sending never generates.

The manual PNG importer supports this extension's recipes and simple Qwen 2.1
Comfy PNGs with one encoder and one sampler. Complex graphs are not executed.
The original internal tab/package IDs and `qwenEditLoadImage` entry point remain
for compatibility; the preferred public handoff is `imageEditLoadImage`.

## Development and tests

The adapter registry is `forge_qwen_edit/adapters.py`. Supporting a new edit
architecture requires a compatible backend, conditioning and mask handling,
component validation and tests—not just adding a checkpoint filename.

From the extension directory:

```sh
python -m unittest discover -s tests -v
node --test tests/image_transfer.test.cjs tests/lightbox.test.cjs
python -m compileall -q forge_qwen_edit tools
```

Tests run without model downloads or a GPU. Use the Forge environment for runtime
checks. Report Forge revision, extension version, GPU/VRAM, model filenames,
settings and the relevant error when filing an issue. Do not include credentials
or personal images unless you intend to share them.

Code and attribution: [LICENSE](LICENSE), [NOTICE.md](NOTICE.md).
Model-weight licenses are separate. Uninstalling the extension removes its tab;
it does not remove shared weights, generated images or an installed core backend.
