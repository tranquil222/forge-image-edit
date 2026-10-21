# Forge Image Edit

Native image-editing workspace for **Forge Neo**. Qwen Image 2.1 (base and
Turbo), Fibo 2.0 Edit Turbo, and optional Fibo 2.0 Dev share one **Image Edit**
tab. Version **0.5.18 beta**. No ComfyUI server or cloud image service.

## Main controls, Fibo Shift and RoPE

Edit mode, Generate / Cancel, Seed / Batch, and Speed / quality / Resolution are grouped
below the result. Expanding sizing or crop controls does not move Generate down.

Fibo has two independent experimental controls in this group:

- **Shift** changes the sampling schedule and
  can affect contrast and texture. Manual **1.15** preserves the existing
  default. **Image-size adjusted** computes Shift from the actual model working
  dimensions, not the saved canvas size. It is not inherently better for outpainting.
- **RoPE adjustment** is independent of output size and available for whole-image,
  painted and crop/outpaint edits. It can affect contrast, texture and detail at
  any resolution. It uses the spatial-coordinate scaling from
  [reverentelusarca's 2K workflow](https://huggingface.co/reverentelusarca/fibo-2.0-2K-rope):
  **X 0.85 / Y 0.80**, applied to both output and reference positions. It generates
  at the selected resolution directly; there is no upscale-and-downscale pass.
  The toggle does not change resolution, steps, Shift, or your image pixels.

To approximate that workflow, use **Fibo Edit Turbo**, **Resolution 2048**
(roughly 4 MP), **8 steps**, **CFG 1**, **Euler / Simple**, **Manual Shift 1.15**,
and enable **RoPE adjustment**. Our aspect-preserving sizing/grid and Forge
backend differ from ComfyUI, so matching the RoPE trick does not promise identical
images. Larger model images need more memory and time. The workflow targets
high-resolution stretching; neither control is an established contrast fix.

Both controls are saved in the PNG recipe. Older PNGs restore Manual 1.15 and
RoPE off. Qwen ignores these Fibo-only controls. Existing 4-step Turbo defaults
and low-resolution behavior are unchanged unless you enable a control.

The shared **Output size** section holds sizing controls. For exact whole-image
dimensions, enable **Custom output size**.
**Resize to** provides linked Width / Height sliders; **Resize by** scales from
the loaded source (for example, 2× doubles each dimension). This sets the actual
whole-image inference/output size, not a post-generation enlargement. It overrides
Resolution for the source/output; additional references still use Resolution.
Sizes are limited to 32–4096 pixels per edge. Loading a new source resets the
dimensions and scale, but keeps your checkbox preference. The controls are hidden
for painted and crop/outpaint edits, which retain their existing canvas geometry.
Use Crop / outpaint to change the aspect ratio or add content outside the image.
In that mode, the same Output size section shows **Resize by** percentages for
the complete canvas (formerly Shrink by); **50%** halves width and height.
Canvas scaling only reduces size; enlarge the canvas with the edge controls.
An unchanged, unpainted canvas disables Generate and explains what to change.
Painting still enables generation with every edge set to zero.

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

### Expression transfer

Choose **Edit mode → Expression transfer** and add an expression reference.
The source is `<image_1>`; the first filled additional reference is `<image_2>`.
The preset adds expression-only guidance and asks the model to retain the source
person's identity, appearance, lighting and background. An optional edit instruction
can specify the person or expression details. This is a prompting preset, not a
trained identity lock; reference appearance can still leak into a global result.

If the reference takes over, describe only the expression in words (or ask an
image-capable LLM to describe it), remove the additional references, switch to
**Standard**, and paint the face. Fibo then uses its normal masked edit; for Qwen,
choose **Refine / expression** after painting. For example: "Pucker her lips into
a small rounded kiss and narrow one eye slightly." The in-app tip names the
appropriate fallback mode for the current model and painted/unpainted state.

Paint the face to preserve pixels outside the selection. In this mode the model
receives a clean source crop, not a grey-covered face, and the mask is used for the
final feathered composite. The preset remains selected when painting is added or
cleared. Crop/outpaint uses its own mode. The PNG recipe retains the preset and
expanded prompt without changing the text you entered.

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

- **Fibo:** opaque neutral grey (RGB 128), threshold 128. The masked source is
  image 1. Optional extra references use its multi-image conditioning path.
- **Qwen Replace / remove:** opaque green source; no clean source is sent.
- **Qwen Refine / expression:** clean source plus green location guide.

A contextual crop is generated and blended back. Pixels outside the painted
support, including source alpha, remain exactly unchanged. Blending feathers
inward. Resolution controls crop detail; final dimensions stay original.
This is model-specific reference preparation plus compositing, not a guarantee
of seamless repairs. Paint a larger border if necessary.

**Additional reference images** work with both painting and outpaint. Use them
for architecture, materials, objects or appearance in the editable region.
For Fibo, an example instruction is: "Extend the room using the architecture
from `<image_2>`, adapted to the perspective and lighting of `<image_1>`."
References are numbered in filled-slot order; fill Image 2 before Image 3 to
keep the labels aligned. Additional references increase memory use.

Use **Edit** beneath an additional reference to expand its **Curves & levels**.
Each slot has independent RGB/channel curves, levels, undo/redo and resets. The
clean **`<image_1>` source** appears beside the curves for color comparison. Only
one editor opens at a time; switching editors retains both references' settings.
The preview updates in place, while the uploaded file stays untouched. Generation
applies those adjustments to the full-resolution original before resizing it for
the model, including during painting and outpaint. Closing Edit keeps the changes;
**Reset all** restores the original tones. **Preview** only switches the displayed
comparison, not what is sent. Clearing or replacing a reference resets that slot.
The generated recipe records the adjustment; re-uploaded references start unadjusted.

The small `<image_1>`, `<image_2>` and `<image_3>` buttons beside **Edit instruction**
and **Describe the finished image** insert the selected token at that field's cursor
(or replace its selected text).

Fibo's masked + multi-reference combination is **experimental**: its documented
[masked pipeline](https://github.com/muhammadali-afridi/diffusers/blob/ali/fibo2/src/diffusers/pipelines/bria_fibo2/pipeline_bria_fibo2.py)
accepts one image. This extension instead sends the already grey-masked source
and extra images through multi-image conditioning, then composites only the edit
selection. Reference adherence is model-dependent; this is not a separate trained
outpaint or reference-guided inpaint model.

### Crop / outpaint

Enable **Crop / outpaint** below the source to reveal four compact edge sliders.
The toggle is disabled without a source image. It remembers your selection
until you uncheck it, including across uploads, IIB transfers and result reuse.
The four sliders have consistent ranges with zero centered, and reset to zero
for each new source. **Positive pixels add space; negative
pixels crop that edge.** Left/right and top/bottom are independent, so a single
operation can crop one side and expand another. The resulting canvas dimensions
are shown automatically. **Reset edges** returns to the original bounds.

**Output size → Resize by** reduces the whole planned canvas before generation
and saves at that smaller size. For example, a 3072 × 2048 canvas at **50%**
becomes 1536 × 1024 (half the width and height, one quarter of the pixels).
Choose 100% (original size), 67%, 50%, 33% or 25%. Edge values remain in loaded-source pixels; the
summary shows the reduced output and model-image dimensions. The loaded source
and its strokes are untouched. The scale stays selected across source changes;
Reset edges resets only the four edges.

**Resolution** already limits model working size independently of the saved
canvas. It can reduce the shrunk canvas further for inference, but will not
enlarge it. Native resolution (0) uses the reduced canvas, plus model-grid padding.
Shrinking a large saved canvas does not necessarily reduce inference cost if a
lower Resolution already limits it.

The green outline is a persistent preview of the final canvas, not a green
overlay. Fibo receives RGB **128, 128, 128** only in the added border; Qwen uses
its own green replacement guide. The outline never enters either model input.
The original image is not resized or overwritten by the controls. Painting stays
available: cover edge objects you want replaced before the scene is extended.
The added border and painted areas form one edit region. Strokes remain aligned
with the source while cropping, expanding, zooming or panning. Erase, undo/redo
and Clear painted area affect only the strokes, not the automatically selected border.

**Seam blending (output px)** crossfades the generated result into a narrow strip inside
the original after generation (default 32 pixels, adjustable 0–128). Fibo still
receives a hard grey mask; no spatial blur is applied to either image. Added pixels
are fully generated, never blended with the grey padding. Pixels outside painting
and this overlap stay exact (relative to the downscaled original when canvas scaling
is used). Shrinking resamples the retained photo separately from the grey
border, so grey does not bleed into it. Set 0 for a hard boundary. Crossfading can soften tone
seams, but mismatched geometry or texture may remain visible or look softer in the overlap.

- **Added space:** describe what should continue beyond the photo, then
  **Generate outpaint**. A blank prompt uses a natural scene-extension instruction.
  For Fibo, also describe the complete scene in **Describe the finished image**;
  this can help when an instruction such as "fill the grey area" leaves the
  border unfilled. **Get prompt from metadata** can recover a starting description.
  If the original becomes a picture on a grey wall or floor, especially when
  expanding all four sides, describe the actual objects and surfaces that should
  continue to each edge. A vague caption or "without grey areas" is less specific.
  Automatic scene-continuation guidance helps, but does not guarantee a fill.
  The whole canvas supplies context; added pixels, painting and the seam overlap
  are composited in. Other source pixels remain exact, or match the downscaled
  original when shrinking. Resolution controls inference detail, not
  the final canvas dimensions. Optional additional references guide the new content;
  painted feathering and default global Fibo curves do not apply.
- **Painting without expansion:** Generate edit applies the painting, optionally
  with a crop. Setting all edges to zero still allows a painted edit.
- **Crop only, without painting:** **Apply crop** saves the exact retained pixels without model
  inference, resampling, a prompt or a valid edit-model selection. Batch count
  does not produce duplicate crops.
- **Shrink only, without painting or expansion:** **Apply shrink** saves a smaller
  copy without running the model. Crop and shrink can also be combined.

Both use Forge's native img2img save path and metadata controls. Recipes record
the signed edges, retained source rectangle and output dimensions. **Use result
as source** resets only the edge values, so edges are not accidentally applied twice.
Recipe imports likewise do not recrop or expand an already-edited image.
Curves after outpainting default to its saved border/painting/overlap selection. The model
still determines the generated continuation; exact source preservation does not
guarantee a seamless join. Large extensions are often easier in smaller stages.

### Contrast drift and fine texture

For Fibo, try **Shift** and **RoPE adjustment**, or open the result’s **Curves**
for manual tonal corrections. The auto-correction checkbox has been removed;
importing an older PNG does not re-enable it. Neither sampling control guarantees
that an edit will preserve the original contrast or texture.

Qwen 2.1's stock VAE has a documented fine checkerboard artifact. The optional
[texture-fix VAE](MODELS.md#qwen-21-texture-fix-vae) addresses that decoder artifact;
it is not a Fibo VAE. This decoder does not guarantee original
fine-detail preservation. Whole-image edits can regenerate texture even when the
instruction names only one object. For exact preservation elsewhere, **paint an
edit area** and work from the original instead of repeatedly editing the output.

### Live curves and levels

Click the edited result to enlarge it, then **Curves**. The side panel provides
a master RGB curve, separate red/green/blue curves, a histogram, precise point
coordinates, and input black/midtone/white plus output-level controls. Click to
add points, drag to adjust, or use the graph's arrow keys. Delete removes an
interior point. Preview, Undo/Redo, Reset channel and Reset all are available.
Black and white endpoints move horizontally as well as vertically, by dragging,
arrow keys or precise Input/Output entry. Moving the black point right clips lower
inputs to its output level; moving the white point left clips higher inputs.

- **Restrict to mask:** on by default when the result has a saved edit selection.
  Curves use that result's mask, including painted/outpaint/overlap areas. Uncheck
  for whole-image correction. Repainting the source later does not change this mask.
- **Feather mask (px):** 0–64, default 0. Softens the correction inward along the
  saved mask; it does not blur image pixels or spread into unpainted areas. Preview
  and full-resolution export use the same mask calculation. Undo/Redo includes
  restriction and feather changes. The original selection is retained after saving,
  even after an unrestricted correction, so feathering is not repeatedly baked into it.
- **No saved mask for this result:** the controls remain visible but disabled;
  correction applies to the whole image. A mask from another edit is never borrowed.
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

**Get prompt from metadata** reads the source's original positive prompt, including
original metadata preserved through earlier Image Edit operations. For Fibo it fills
**Describe the finished image** and leaves **Edit instruction** unchanged; for Qwen
it fills **Edit instruction**. Adjust the recovered text to describe the desired result.
Forge/A1111 PNG and EXIF infotext and common ComfyUI saved prompt graphs are supported.
ComfyUI positive conditioning is followed through standard samplers, guiders and
text encoders; negative and disconnected prompts are excluded. Multiple positive
texts appear as separate choices. Missing metadata, workflow-only files and
unsupported custom processing cannot always recover the original text; no graph is
executed, and an unsuccessful lookup leaves existing text unchanged.

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
