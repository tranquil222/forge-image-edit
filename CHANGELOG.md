# Changelog

## 0.5.25 beta — camera-photo metadata saving fix

- Fix `TypeError: Object of type IFDRational is not JSON serializable` when
  editing camera JPEG/TIFF images. Convert EXIF-derived DPI values to plain
  numbers before writing PNG history; preserve original EXIF and ICC data.
- Ignore malformed optional DPI values rather than losing a completed edit.
  Metadata preservation on/off and repeated edit history remain supported.
- Clarify why a backend repair performed during startup can require one more
  full restart: Forge imports its backend settings before extension installers.
- No model inference changes. Pending reference-editor work is not included.

## 0.5.24 beta — repair partial backend installations

- Repair verified mixtures of original and already-patched backend files after
  a Forge update, restoring missing `fibo2` registration and Qwen editing hooks.
  Only exact known file hashes are accepted; customized files are not overwritten.
- Keep already-patched files intact and back up only files changed by a repair.
  Check-only remains read-only; applying again is a no-op.
- Distinguish incomplete files on disk from a fully patched backend awaiting a
  process restart. Avoid telling users that repeated restarts fix missing setup.
- Verify installation/repair against current Neo `6b3a78d` as well as the three
  earlier supported bases. Qwen 2.1 Turbo remains supported with its 8-step preset.
- This is an installation-only hotfix; pending reference-editor work is excluded.

## 0.5.23 beta — sampling choices and saved-image imports

- Show all registered Forge samplers and schedules for every supported edit model.
  Keep existing quality-preset defaults; preserve custom choices in PNG recipes.
  Remove model-family and official-Turbo sampler/step restrictions. Missing
  registered implementations still report an error before generation.
- Keep Qwen's fixed-grid Shift adjustment limited to CyberZit Quality and the
  official Qwen Turbo schedule; other schedules use Forge's normal dispatch.
- Import from txt2img now uses the selected gallery image first, then browses
  saved images newest-to-oldest on repeated clicks. An empty gallery starts with
  the newest saved image, including after a Forge restart.
- Add Import random for saved txt2img images. Preserve metadata, leave history
  unchanged after random/IIB imports, and keep IIB limited to its open lightbox.
- Add Advanced below PNG settings import, with an optional txt2img import-folder
  override. Blank uses Forge's configured output folder. Include subfolders and
  skip unreadable/incomplete images; do not clear the source at the end of history.
- Reduce import buttons to 28px tall and combine crop/import help into one tooltip.
- Speed up large saved-image folders with directory-entry metadata and a short-lived,
  bounded file index. Repeated imports no longer rescan every image; starting a
  new history sequence refreshes the index immediately.

## 0.5.22 beta — cumulative editing and import update

- Treat unchanged, unpainted Crop / outpaint canvases as normal prompt edits.
  Keep Generate edit enabled when the source and model are ready, show a clear
  whole-image-edit notice, and report the actual normal-edit output size.
- Keep Qwen/Fibo checkpoint selections in the correct saved preset; ignore
  crossed-family saved entries and keep an already matching checkpoint selected.
  Manual checkpoint selection synchronizes the layout without changing encoder/VAE.
- Replace the mutating matching-components button with read-only **Check model
  setup**. Image Edit readiness follows the checkpoint and its selected components.
- Name missing encoder/VAE files in the setup status and check-button feedback.
  Add an optional custom-filename override in Extras with explicit VAE selection;
  save and restore the override and component roles in PNG recipes.
- Transfer the full result PNG directly to the source canvas, preserving metadata
  and current settings. Reusing an identical result clears paint and crop edges;
  failed transfers show an error and leave the source intact.
- Add **Import from txt2img** and **Import from Infinite Image Browser** beside
  Crop / outpaint, with question-mark instructions. Follow the selected batch
  result or open IIB lightbox after switching tabs. Preserve original file bytes
  and metadata for prompt extraction. Do not inject controls into IIB.
- Align the crop checkbox, import buttons and help icons. Keep import feedback
  out of layout: brief button confirmation on success, filename on hover, and
  temporary error popovers. No extra vertical gap for status text.
- Give Qwen outpaint a concise, direct border-replacement instruction instead of
  the longer Fibo guidance that could leave the green guide in the result.
  Keep Qwen's green input, Fibo's grey input and original-pixel preservation.
- Add Qwen Shift and experimental RoPE in the same Extras layout as Fibo.
- Keep separate model values, defaults and help. Qwen defaults to Manual 0.69
  with RoPE off; switching models does not carry Fibo's default into Qwen.
- Apply Qwen Shift to fixed Normal/Quality and official Turbo schedules as a
  delta from the unchanged default; Simple uses the model predictor directly.
- Scale only Qwen image RoPE positions, preserving text and image-plane positions.
  Clear prefix caches and remove job-scoped hooks even after cancellation.
- Save and import Qwen controls in PNG recipes, with defaults for older recipes.
- Add a durable work log for cumulative updates and validation history.

## 0.5.21 beta — installation hotfix

- Fix backend installation on MOSS-enabled Forge Neo (`2c24de1`). The previous
  patch correctly refused changed files, but left users with the Image Edit tab
  installed and no `fibo2` UI preset. Preserve upstream MOSS/Qwen3.5 support and
  assign Fibo a distinct preset ID.
- Keep support for both previously verified Neo bases. Add the new base to CI.
- Report the Forge revision and mismatched files when setup cannot proceed.
- Distinguish missing native files from unloaded model registration in the UI.
- Replace vague setup guidance with exact update, full-restart, check/apply and
  report steps. Checkpoint placement does not control preset availability.
- Installation-only hotfix. No sampling, sizing or generation-default changes.

## 0.5.20 beta

- Group Seed / Batch, Speed / quality, Resolution and output sizing inside a
  Settings accordion; group Edit mode, Shift and RoPE inside Extras.
- Start both collapsed to bring the prompts higher. Align their headers in one
  row with arrows on the left; stack them on narrow screens.
- Keep Crop / outpaint and its expanding edge controls outside both sections.
  Closing an accordion retains settings. No inference or sizing changes.

## 0.5.19 beta

- Put Generate / Cancel directly below the source image on the left, followed by
  Crop / outpaint, Seed / Batch and Speed / quality / Resolution. Canvas edge
  controls expand directly under their toggle; Output size stays below quality.
- Move the standalone painting guidance into a source-toolbar tooltip.
- Keep Edit mode, Shift and RoPE on the right below the result actions.
- Let each column flow independently, removing the gap previously reserved under
  the source for the taller result/download section.
- Use one always-visible Resize to / Resize by section for whole-image and
  crop/outpaint edits. Remove the separate canvas percentage dropdown. Dimensions
  stay linked to the complete planned canvas; editing a size enables its override.
- Custom sizing sends and saves the requested size for outpaint too. Resize-only
  canvases use Apply resize without model generation. Existing painted pixels and
  seam masks follow the resized canvas.
- Move lengthy control explanations into keyboard- and touch-accessible ? help.

## 0.5.18 beta

- Group Edit mode, Generate / Cancel, Seed / Batch and Speed / quality / Resolution
  below the result. Optional canvas and sizing controls no longer push Generate down.
- Make RoPE adjustment independent of sizing and available for whole-image, painted
  and crop/outpaint edits. Shift and RoPE retain their existing sampling behavior.
- Consolidate sizing in Output size; canvas Shrink by is now Resize by percentages.
- Remove the auto-correction checkbox; older recipes do not silently restore it.
- Link Width / Height immediately in the browser, avoiding stale server responses
  during fast drags; immediate generation submits the latest linked dimensions.
- Disable generation on unchanged, unpainted canvases with an actionable hint.
  Painting at zero edges remains supported; crop/shrink still work without a model.

## 0.5.17 beta

- Move Fibo Shift into the right-hand space below the result/download buttons;
  describe its effect on contrast and texture.
- Place Custom output size directly below Edit mode and above the output summary.
- Move High-resolution RoPE inside the expanded Custom output size section.
  Preserve generation behavior, defaults and PNG recipe fields.

## 0.5.16 beta

- Add optional exact whole-image output dimensions: linked Width / Height or
  Resize by. Infer at the requested size, edge-pad to the model grid and remove
  only that padding before saving. New sources reset dimensions/scale without
  clearing the checkbox. Painted/canvas edits keep their preservation behavior.
- Add Fibo-only Manual / Image-size adjusted Shift controls under Sampling settings.
  Manual 1.15 remains the default; automatic Shift uses actual model dimensions.
- Add optional High-resolution RoPE matching the linked 2K workflow's X 0.85 / Y 0.80
  spatial scaling. The queued-job hook is removed on success, cancellation or error;
  no core patch, weight modification, hidden resize or contrast postprocessing.
- Save/import both controls and effective Shift in PNG recipes. Old recipes retain
  previous behavior. Qwen, masks, references and existing quality defaults are unchanged.
- Document approximate workflow settings and distinguish this high-resolution
  geometry experiment from a proven contrast or outpainting fix.

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
