# Changelog

## 0.5.15 — beta

- Make outpaint guidance scene-focused: continue the visible content across the
  full canvas instead of presenting the original as a separate photograph,
  poster or framed object on a new background. Explicitly discourage an outline,
  drop shadow, blank surround or new vignette at the old boundary.
- Retain Fibo's neutral-grey mask and painted-area replacement guidance. Do not
  add noise, blur the source or enlarge the editable area.
- Clarify the finished-image description hint: describe the scene and what
  continues into added space, including objects, setting, colors and surfaces.

## 0.5.14 — beta

- Switch Crop / outpaint controls immediately in the browser, keeping the toggle
  above both sections. Preserve the selected edit mode and its tip while hidden.
- Remove Gradio's temporary Markdown minimum height and fading in Image Edit,
  which caused blank gaps and repeated layout jumps during feedback updates.
- Shorten the heading to Image Edit. Show the exact selected checkpoint, encoder
  and VAE filenames beside a compact matching-components button. Show required
  component filenames when the selection is incomplete or incompatible.
- Remove the unrelated Qwen texture-fix compatibility warning from Fibo's header.

## 0.5.13 — beta

- Add a fallback tip to Expression transfer: describe the expression in words,
  remove additional references, switch modes and paint the face. Include a short
  example and an optional image-capable LLM suggestion. Name the fallback mode
  for the current model and painted/unpainted state.
- Clarify that Expression transfer adds prompt guidance; it does not enforce
  expression-only use of the reference.

## 0.5.12 — beta

- Add an Expression transfer edit preset: use the first additional reference only
  for facial expression, with guidance to retain the base identity, appearance and
  scene. Support whole-image edits and painting; painted expression edits send the
  clean source face and use the selection for final compositing. Save the preset
  and expanded instruction in the PNG recipe.
- Show the clean `<image_1>` source beside reference Curves & levels for color
  comparison. Follow source uploads, replacement, clearing and result reuse without
  including brush/outpaint overlays or applying reference adjustments to the source.
- Open one reference editor at a time in a full-width comparison workspace.
  Switching or closing editors retains both references' independent adjustments.
  Stack the source comparison above the curves on narrow screens.

## 0.5.11 — beta

- Add compact `<image_1>`, `<image_2>` and `<image_3>` insertion buttons beside
  Edit instruction and Describe the finished image. Insert at the cursor or replace
  the selection in that field without changing the other prompt.
- Add an Edit button under each additional reference. Expand the shared RGB/channel
  curves and levels controls, with preview comparison, undo/redo and resets.
- Keep uploaded originals unchanged. Apply each reference's current adjustment at
  full resolution before model preparation, for global edits, painting and outpaint.
  Closing the controls keeps the adjustment; replacing or clearing an image resets
  only that reference. Bind adjustments to the upload hash to reject stale settings.
- Record reference tone adjustments in the generated PNG recipe. Reference controls
  do not alter result curves, global defaults or the source image.

## 0.5.10 — beta

- Allow additional references during painted edits and outpaint. Keep the masked
  source first, add reference-role guidance, and preserve the normal final selection.
  Fibo masked + multi-reference guidance is experimental; its documented masked
  pipeline is single-image, while this combines a grey source with multi-image conditioning.
- Add explicit Restrict to mask and Feather mask (0–64 px) controls to Curves.
  Feather adjustment strength inward, not image pixels. Preview and saved PNGs
  match; scope/feather are undoable. Keep the original selection after every save.
- Unlock curve endpoints horizontally for shadow/highlight clipping. Both drag
  and Input values work; values beyond endpoints clip to their respective output levels.

## 0.5.9 — beta

- Add compact Shrink by control to Crop / outpaint: 1× off, 1.5×, 2×, 3× or 4×.
  Reduce the entire planned canvas before generation and save at the smaller size,
  without changing the loaded source. Painting and seam blending follow the new size.
- Show final output and model-image dimensions. Resolution remains an independent
  inference limit, but never enlarges an explicitly shrunk canvas.
- Resize retained content separately from grey borders to avoid grey-edge bleed.
  Unpainted pixels are preserved relative to the downscaled original. Shrink-only
  and crop/shrink saves need no model. 1× preserves existing behavior.
- Generation API adds shrink factor immediately before batch count; crop API adds
  it as the final optional argument. Recipes record original canvas and output sizes.

## 0.5.8 — beta

- Painting remains available during crop/outpaint. The generated region combines
  the added border with source-space brush strokes; edge objects can be covered
  before extending the scene. Brush alignment, zoom/pan, erase and undo are retained.
- Add adjustable seam blending (0–128 pixels, default 32). Crossfade after generation
  into a narrow original-image overlap, without blurring the photo or softening
  Fibo's grey input mask. Added pixels never blend against grey padding. Pixels
  outside painting and the overlap remain exact. Zero disables seam blending.
- Painted edits also work with crop-only or zero edge changes. Without painting,
  pure crops still save without running a model. Curves use the combined selection.
- Generation API adds seam-blending pixels immediately before batch count;
  the crop endpoint now also reads the foreground to prevent silently ignoring painting.

## 0.5.7 — beta

- Crop / outpaint is disabled without a source and stays selected across uploads,
  IIB transfers, clearing/reloading and result reuse until manually unchecked.
  Each new source resets only the edge values; all four sliders center zero.
- Get prompt from metadata recovers the original positive prompt from Forge/A1111
  infotext, EXIF or common ComfyUI prompt graphs. Fibo fills the finished-image
  description without replacing the edit instruction; Qwen fills Edit instruction.
  Multiple ComfyUI positives are selectable; missing prompts leave existing text alone.
- Fibo outpaint help recommends describing the complete expanded scene.
- The download area explains that images are also saved to the native img2img
  output folder (or the user's configured override).
- Clearing the canvas also clears the server-side source on older Forge builds.

## 0.5.6 — beta

- Crop / outpaint toggle keeps signed Left/Right/Top/Bottom controls hidden
  until needed. Positive expands, negative crops; the persistent green outline
  and live dimensions preview the exact final canvas without changing the source.
- Fibo receives a neutral-grey added border; Qwen uses its own replacement guide.
  Generation uses full-canvas context, composites only added pixels, and preserves
  the retained original exactly. The green preview outline is never model input.
- Crop-only changes save without model inference or resampling. Crops/outpaints
  use native img2img saves, preserve optional metadata and record their canvas plan.
- New sources reset the edges. Existing strokes survive toggling outpaint off;
  additional references, feathering and global Fibo curves do not affect outpaints.
- Generation API adds the canvas-enabled flag and four signed edge values before
  the final batch-count input. Pure crops also have an `image_edit_crop` endpoint.

## 0.5.5 — beta

- Fix non-square reference stretching: preserve proportions, edge-pad for the
  model grid and remove only that padding afterward. Native-size mode retains
  original pixels. Applies to both Qwen and Fibo; old PNGs are unchanged.
- Curves can save an opt-in default for future unpainted Fibo Turbo/Dev results.
  Qwen and painted edits are excluded; refinements compose without double application.
  Presets persist in Forge's data directory and applied LUTs are recorded in PNGs.
- Generate/Cancel move to the left, Seed/Batch to the right. Narrow layouts keep
  buttons on the next row. Align quality/resolution and replace the empty download
  panel with a compact PNG download button.
- Clarify that automatic tone estimation runs on the next generation, and report
  negligible/skipped/applied correction in the saved-result status.

## 0.5.4 — beta

- Batch count: 1–64 sequential variations from the submitted source/mask, with
  native per-image saves and a selectable result gallery. Cancellation or a
  later failure keeps completed outputs.
- Seed moves beside Generate/Cancel with native-style dice and reuse buttons.
  Reuse copies the selected result's exact seed. Random stays random; fixed
  seeds increment per image. Narrow layouts put the buttons on the next line.
- Camera angle tip explicitly discourages “keep things the same” instructions.
- Gradio generation endpoint adds Batch count as the final input and returns
  gallery/source transport values before the final status HTML.

## 0.5.3 — beta

- Shorter Camera angle guidance emphasizes redrawing visible surfaces and
  foreground objects, rather than preserving the input projection.
- Camera-only tip explains how to describe the reframed view and optionally ask
  an image-capable LLM for help. No new controls, model downloads or LLM integration.
- Standard mode and painted editing are unchanged.

## 0.4.0 — beta

- Shared Image Edit workspace for Qwen 2.1 base/Turbo and Fibo 2.0 Turbo/Dev.
- Forge's main model bar is authoritative; strict component checks and an
  installed-component correction button replace hidden model selections.
- Model-specific presets, guidance, negative prompt and reference-cache controls.
- Fibo neutral-grey masks and optional structured result descriptions.
- Native img2img output path, naming and save hooks.
- Optional original metadata preservation with appended edit history and recipes.
- Image browser handoff loads edit recipes; visible action is Send to Image Edit.
- Public-base compatibility patch, check-first installation, optional pinned
  model downloads, tests and GitHub CI definition.
- No bundled weights, settings, sample photos, credentials or absolute local paths.

Older internal package/tab IDs remain for compatibility. Avoid installing this
alongside a second copy named forge-qwen-edit.
