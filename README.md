# Forge Image Edit

Native image-editing workspace for **Forge Neo**. Qwen Image 2.1 (base and
Turbo), Fibo 2.0 Edit Turbo, and optional Fibo 2.0 Dev share one **Image Edit**
tab. Version **0.5.6 beta**. No ComfyUI server or cloud image service.

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
4. Use **Download PNG with settings** or **Use result as source**.

**Generate/Cancel** sit on the left, with **Seed** and **Batch count** on the right; in a narrow window the
buttons move together onto the next line. **🎲** sets `-1` (a fresh random seed
for every image). **♻️** copies the selected result's seed for prompt comparisons.

Set **Batch count** to 1–64 for sequential variations of the submitted source,
mask and instruction. This is not a chain of edits or a larger GPU batch size.
A fixed seed increases by one per image; `-1` stays random. Each PNG is saved
immediately to the native img2img output folder with its own seed and recipe.
Thumbnails appear when the batch finishes or is cancelled; select one to view,
download, reuse as source, adjust curves, or copy its seed. Cancel stops the
remaining work and keeps completed files. A GPU operation already in progress
may need to finish before cancellation takes effect.

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
square crop; 0 uses native size. References are scaled proportionally and edge-padded
to the model's 32-pixel grid. Only that padding is removed from the output, so
the grid does not stretch or crop the scene. Output dimensions can therefore be
non-multiples of 32. Integer resizing can differ by less than one pixel from the
exact source ratio. Previously saved images are not modified by this fix.
Fibo is trained near 1 MP; 1024 is a useful
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

### Camera angle

Leave the canvas unpainted and choose **Edit mode → Camera angle** (Qwen or Fibo).
Describe the view you want, such as **Low-angle view, looking up at the underside
of the face and held object**, or **Aerial view looking down at the tops of the
subjects and surrounding ground**. The preset adds short, reusable guidance to
reimagine the scene from that viewpoint, including foreground objects, while
preserving recognizable identity rather than locking the original projection.
It uses the full clean source, without a mask or cropped/composited patch.
Standard leaves your instruction unchanged.

The tip shown in Camera angle mode suggests describing what the new view should
reveal. **Do NOT say “keep things the same” or “keep everything unchanged”**;
that can work against changing the perspective. Optionally, give your source
image and short request to ChatGPT or another
image-capable LLM, ask it to describe the reframed result, then paste that prompt
into Edit instruction. This is a manual option, not an integrated LLM workflow:
no extra model, API key, upload, or service is required by the extension.

This is reusable prompt guidance, not a trained camera-control adapter or a 3D
reconstruction. The model can still miss a requested view, alter a pose, or invent
unseen detail. Prompt comparisons on one scene motivated the shorter wording;
they do not establish reliable camera control across images or models.
The short instruction, expanded model prompt and chosen mode are saved in the PNG;
recipe import and Send to Image Edit restore the mode without doubling the prompt.
Painting switches to local edit modes; clear the mask to choose Camera angle again.

### Painted edits

Painting is always available; no checkbox is needed. **No strokes means a
whole-image edit. Painted strokes mean a local edit.** The scope appears below
the canvas. Paint the complete object plus a small border. Scroll to zoom,
right-drag to pan, Shift+paint to erase, F to enlarge, R to fit, Ctrl+Z to undo,
W+scroll for brush size. The native canvas reset tool clears the mask; undo and
redo also update the scope. Changing the source clears the painting.

Overlapping opaque strokes add to the selection without erasing underneath,
avoiding faint transparent outlines. Edge blending happens during compositing,
not between brush strokes. Other Forge canvases are unchanged.

- **Fibo:** opaque neutral grey (RGB 128), threshold 128. One masked source is
  sent; extra references are disabled in this mode.
- **Qwen Replace / remove:** opaque green source; no clean source is sent.
- **Qwen Refine / expression:** clean source plus green location guide.

A contextual crop is generated and blended back. Pixels outside the painted
support, including source alpha, remain exactly unchanged. Blending feathers
inward. Resolution controls crop detail; final dimensions stay original.
This is model-specific reference preparation plus compositing, not a guarantee
of seamless repairs. Paint a larger border if necessary.

### Crop / outpaint

Enable **Crop / outpaint** below the source to reveal four compact edge sliders.
They start at zero for each new source. **Positive pixels add space; negative
pixels crop that edge.** Left/right and top/bottom are independent, so a single
operation can crop one side and expand another. The resulting canvas dimensions
are shown automatically. **Reset edges** returns to the original bounds.

The green outline is a persistent preview of the final canvas, not a green
overlay. Fibo receives RGB **128, 128, 128** only in the added border; Qwen uses
its own green replacement guide. The outline never enters either model input.
The original image is not resized or overwritten by the controls. Existing
brush strokes are ignored while crop/outpaint is enabled and remain available
when it is turned off.

- **Added space:** describe what should continue beyond the photo, then
  **Generate outpaint**. A blank prompt uses a natural scene-extension instruction.
  The whole canvas supplies context; only newly added pixels are composited in.
  Retained source pixels remain exact. Resolution controls inference detail, not
  the final canvas dimensions. Additional references and painted feathering are
  not used; default global Fibo curves do not apply.
- **Crop only:** **Apply crop** saves the exact retained pixels without model
  inference, resampling, a prompt or a valid edit-model selection. Batch count
  does not produce duplicate crops.

Both use Forge's native img2img save path and metadata controls. Recipes record
the signed edges, retained source rectangle and output dimensions. **Use result
as source** resets the controls, so edges are not accidentally applied twice.
Recipe imports likewise do not recrop or expand an already-edited image.
Curves after outpainting stay within its saved added-border mask. The model
still determines the generated continuation; exact source preservation does not
guarantee a seamless join. Large extensions are often easier in smaller stages.

### Contrast drift and fine texture

**Auto-correct global brightness / contrast** optionally reduces global tone drift after
an object edit, for both Qwen and Fibo. It estimates one neutral gain/offset from
mostly unchanged content and applies it without blurring or sharpening. Leave it
off for intentional lighting/contrast changes or major scene changes. It defaults
off; PNG recipes and **Send to Image Edit** retain the setting and recipes record
the applied correction. In painted mode the selected area is excluded from the
estimate, and compositing still keeps outside pixels exact. This runs on the next
generation, not the result already on screen. The save status reports a negligible
estimate, a skipped estimate, or the gain/offset applied. It cannot repair localized
contrast changes or texture loss; use Curves for a manual correction.

Qwen 2.1's stock VAE has a documented fine checkerboard artifact. The optional
[texture-fix VAE](MODELS.md#qwen-21-texture-fix-vae) addresses that decoder artifact;
it is not a Fibo VAE. Neither tone matching nor this decoder guarantees original
fine-detail preservation. Whole-image edits can regenerate texture even when the
instruction names only one object. For exact preservation elsewhere, **paint an
edit area** and work from the original instead of repeatedly editing the output.

### Live curves and levels

Click the edited result to enlarge it, then **Curves**. The side panel provides
a master RGB curve, separate red/green/blue curves, a histogram, precise point
coordinates, and input black/midtone/white plus output-level controls. Click to
add points, drag to adjust, or use the graph's arrow keys. Delete removes an
interior point. Preview, Undo/Redo, Reset channel and Reset all are available.

- **Painted area:** an edit generated with a mask keeps curves inside that exact
  saved selection, including its inward-feathered edge. Outside pixels and alpha
  stay unchanged. Repainting the source later does not change the result's mask.
- **Whole image:** an edit without a mask applies curves to the entire result.
- The scope is displayed in the panel. An older painted PNG without its selection
  is not silently treated as a whole-image adjustment; generate a new painted edit.

Preview runs locally without model inference and always starts from the unchanged
result pixels. **Apply to result** saves a new full-resolution PNG through Forge's
native img2img saver and updates the result, download, and **Use result as source**.
The previous file is retained. Download PNG also applies an outstanding correction
before downloading. The applied RGB lookup tables and controls are recorded in
metadata when enabled; recipe import does not apply the already-baked curves again.
Large-image previews use at most 2048 pixels on the long edge; saved output retains
the original dimensions. This is an 8-bit RGB adjustment, not detail restoration.

For an unpainted Fibo result, adjust the curves/levels and check **Use as Fibo
default (unpainted)**. This saves your correction for future Fibo Turbo/Dev
whole-image edits. **Apply to result** saves the current preview and updates the
default when checked. Uncheck to disable it; the preset remains available to
re-enable. Qwen and painted edits never use it. The preset is stored in
`image-edit-curves.json` in Forge's data directory and survives extension updates.
Each corrected PNG records the applied RGB tables when metadata is enabled.
Refining an already-corrected result composes the corrections without applying
the previous correction twice. This is a user-calibrated preset, not a universal
Fibo contrast or texture fix.

**Original / Edited share zoom and pan**, even when their native sizes differ.
The 100% reference is the edited result's dimensions; comparisons stay aligned.
The Generate / Cancel row sits directly under the images, above Edit instruction.
Cancel shows its status immediately and checks between preparation stages as well
as sampling steps. An in-flight GPU operation or model transfer must finish before
Forge can stop; cancellation is not an instant hardware abort.

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
Reference pixels are not embedded. New painted outputs retain a compact,
feathered selection in `image_edit_mask` for later local curves; selections too
large for a compact PNG text field remain available only in the current session.
Reproducing model inference still requires the source and a painted selection.
Manual adjustments append to the history and retain an importable generation
recipe; `image_edit_adjustment` records the latest curves and scope. Metadata can identify the
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
node --test tests/image_transfer.test.cjs tests/lightbox.test.cjs tests/curves.test.cjs tests/outpaint.test.cjs
python -m compileall -q forge_qwen_edit tools
```

Tests run without model downloads or a GPU. Use the Forge environment for runtime
checks. Report Forge revision, extension version, GPU/VRAM, model filenames,
settings and the relevant error when filing an issue. Do not include credentials
or personal images unless you intend to share them.

Code and attribution: [LICENSE](LICENSE), [NOTICE.md](NOTICE.md).
Model-weight licenses are separate. Uninstalling the extension removes its tab;
it does not remove shared weights, generated images or an installed core backend.
