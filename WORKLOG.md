# Local work log

Updated: 2026-10-22. This file is the handoff record for ongoing local work.

## Current update — 0.5.23

- Base is published 0.5.22 commit `daa420063d7e8b53121d03212c68a63aec519aca`.
  Its 150 Python tests, 31 JavaScript tests and all five GitHub CI jobs passed.
- User explicitly authorized pushing this next update immediately after testing.
  Scope includes unrestricted sampler/scheduler fields and all follow-up import
  changes below. Separate Krea plugin and future requests remain out of scope.
- Every supported edit family now uses live Forge sampler/scheduler registries.
  Existing defaults and Speed / quality presets are unchanged. Runtime and PNG
  import checks require installed choices, not model-family allowlists. Custom
  steps/samplers can also use the official Turbo grid. Qwen's special Shift
  transform remains limited to the two fixed grids, avoiding missing inner-model
  arguments or an Automatic scheduler with no function.
- Txt2img imports selected gallery image first; repeated presses walk the saved
  folder newest to oldest. Empty gallery starts with newest. Selection/folder
  changes reset history. A stable modification-time/name cursor avoids repeats
  if newer files arrive or earlier files disappear. Failed transfers do not
  advance the cursor; exhaustion leaves the source unchanged.
- Import random uses readable images from the same folder tree and does not
  advance/reset history. IIB is unchanged: its current open lightbox image only,
  even on repeated presses. Original file bytes and embedded metadata are kept.
- A collapsed Advanced section below PNG settings import supplies an optional
  txt2img import-folder override; blank uses Forge's configured output directory.
  Both saved-history and random imports include subfolders, skipping incomplete
  or corrupt files. This does not change Forge's output setting or IIB's folder.
- Import buttons are 28px tall (previously 34px), with one succinct shared help
  tooltip for crop/outpaint and all three import actions. Feedback stays out of
  normal layout; the row does not grow on success or errors.
- Pre-change backup: `C:/CODEX/forge-image-edit-backups/20261022-122724-sampling-latest-import`.
- Validation: 161 Python tests and 35 JavaScript tests passed; compileall and
  whitespace checks passed. Live headless Edge checks on port 7860 confirmed
  selected-image priority, newest-to-oldest imports, exact original bytes and
  metadata extraction, random/history isolation, custom folder, end-of-history
  source preservation, and selectable Heun/Beta (80 samplers, 23 schedules in
  this install). No GPU generation or global model change was submitted.
- Layout checks: one shared tooltip, 28px row, aligned centers, feedback adds
  no height, and no overflow at an 800px viewport. Artifacts are in
  `C:/CODEX/image-edit-browser-qa/artifacts/sampling-imports-0523/`.
- Installed while Forge was idle, with backup
  `C:/CODEX/forge-image-edit-backups/20261022-124012-cumulative-0522`.
- User reported Generate disabled in a tab still showing the old import row
  after the UI reload. Stale source-readiness/session state is suspected, not
  confirmed; direct Canary inspection was unavailable. User will refresh and
  report if it recurs. No speculative button-state change is included in 0.5.23.
- User reconfirmed finishing and pushing this update after that report.
- Follow-up before publication: user reported multi-second txt2img imports,
  including repeated clicks. Measured 31,954 image files: old full scan took
  3.537s; API requests took 3.746s and 3.588s. Replaced per-file double stats
  with scandir metadata, a sorted 30-second/four-folder cache, and binary cursor
  lookup. New local lookup measured 0.1893s initially and 0.0018/0.0022s for the
  next images, excluding transfer/rendering. New sequences force a fresh scan;
  Random never mutates the sorted history index. Added cache reuse, freshness,
  expiry and eviction coverage; all 161 Python tests pass after this change.
- Live API after the performance fix: 0.2441s first import, then 0.0145s and
  0.0143s, excluding browser transfer/display. Installed idle backup:
  `C:/CODEX/forge-image-edit-backups/20261022-125316-cumulative-0522`.

## Publication rule — current user instruction

Separate local project added 2026-10-22: **Krea 2 Style Reference** lives at
`C:/CODEX/forge-krea-style-reference`, installed as `extensions/forge-krea-style-reference`.
Its own `WORKLOG.md` records implementation and testing. It has Ostris LoRA and
experimental no-LoRA modes, not an Image Edit feature or a published release.
Keep the projects and their publication scope separate.

**Do not push, tag, publish a release, or update GitHub after each turn.**
Keep subsequent changes local. The user will explicitly request a cumulative
update containing everything since the last published update. Do not treat prior
publication authorization as authorization for another push.

Exception explicitly authorized on 2026-10-21: user requested the installation
fix be pushed immediately. Only that hotfix was published; this does not authorize
publishing subsequent local work without another request.

Explicit cumulative publication authorization on 2026-10-22: user asked to push
all Image Edit changes since the previous update, including zero-edge fallback,
then confirmed "yes goo ahead". Version **0.5.22 beta** collects those changes.
This authorization does not include the separate Krea plugin or future updates.

Previous published version: **0.5.21 beta**, tag `v0.5.21-beta.1`.
Previous published commit: `4b0d3979dde9caaee6628bb009a4d9763af60378`.
The sections below retain the local development and validation history included
in the 0.5.22 cumulative update; earlier "local only" labels describe that stage.

## Cumulative update — 0.5.22 scope

- Completed locally: Qwen Shift / RoPE controls and Qwen green-border outpaint
  prompt fix (details and validation below).
- Completed locally: checkpoint/preset synchronization, read-only named-file
  diagnostics, optional custom encoder/VAE filename override, and reliable
  result-to-source transfer (validation below).
- Updated locally, requested 2026-10-22: **Import from Infinite Image Browser**
  in Image Edit replaces the earlier automatic IIB-menu injection. Read the open
  lightbox after switching tabs, preserving original bytes / edit recipes.
  Also add **Import from txt2img**, following the selected batch result. Neither
  action generates. Existing custom Send to Image Edit actions remain supported.
- Support older and current upstream IIB and the Forge Neo XL fork using shared
  capabilities rather than version gating. No compatibility-warning UI. Verify
  actual supported old/new browser builds; do not promise every future version.
- Do not update or overwrite the user's customized IIB installation as part of
  this work. Its XL base is `ced0394` (2026-08-30); the other installed IIB base is
  `f586aaa` (2026-03-18). Both have local changes. Current remote heads checked
  2026-10-22: XL `6da2c1a` (2026-10-19), upstream `f183e32` (2026-10-20).
  Clean latest snapshots are under `C:/CODEX/image-edit-iib-compat/20261022`.
- The published optional `integrations/iib-menu.patch` is not automatically
  applied. The user's existing menu is a local IIB customization; the public
  0.5.21 extension supplies the handoff function but not an automatic menu. The
  local cumulative update now supplies a pull/import button in Image Edit.
- User has now authorized publishing the complete Image Edit queue, including
  the zero-edge normal-edit fallback below. The 0.5.21 installation hotfix remains
  the release base. Future changes stay local until separately authorized.

### Zero-edge normal-edit fallback — 2026-10-22

- Supersedes the previous requested no-op guard: when Crop / outpaint is checked
  but no edge, size or painted change exists, Generate edit remains available
  and runs the same whole-image edit as with the toggle off.
- Notice below the edge controls: "No crop or outpaint changes. Generate edit
  will apply your prompt to the whole image." The size summary now reports the
  actual normal-edit dimensions rather than a preserved canvas size.
- Dispatch omits the empty canvas mask completely, so compositing cannot erase
  the generated edit. Prompt, model, sampling, custom-size and batch settings
  follow normal editing. The source image's originating model is irrelevant.
- Actual outpaint and painted edits still use the canvas path; crop/resize-only
  operations remain model-free. Invalid geometry and incomplete model setups
  still block generation.
- Regression coverage compares checked versus unchecked dispatch across all
  three model families and legacy/current request shapes, including custom
  sizing, Qwen controls and custom components. Python suite: 150 passed;
  JavaScript suite: 31 passed. Compile and whitespace checks passed.
- Pre-change backup: `C:/CODEX/forge-image-edit-backups/20261022-zero-edge-normal-edit`.
- Installed on idle port 7860 with a backed-up UI reload. Live headless Edge
  verified enabled zero-edge generation, the notice and output dimensions,
  expansion labeling, Reset edges, crop-only routing and invalid-geometry
  disabling. No generation submitted; no Canary tab or model selections changed.
  Artifacts: `C:/CODEX/image-edit-browser-qa/artifacts/zero-edge-0522`.
  Installed backup: `C:/CODEX/forge-image-edit-backups/20261022-121249-cumulative-0522`.

### Previous IIB menu implementation validation — superseded by pull imports

- New `javascript/image_edit_iib.js` supplies the automatic menu. Original files
  and recipes use the existing handoff; native/legacy buttons are not duplicated.
- Four actual bundled frontends tested in Edge: older/current upstream IIB and
  older/current Neo XL. Each passed five original-resolution transfers, including
  context menu, fullscreen and hover menu; Unicode paths, keyboard, retry,
  deduplication, non-image exclusions and iframe reload were checked.
- Results: `C:/CODEX/image-edit-iib-compat/20261022/results/results.json`.
- Actual latest-IIB menu -> live Forge Image Edit source handoff passed at
  1018 x 1018 using a separate browser page, with no generation started.
- Node suite: 20 tests passed; `git diff --check` passed. IIB installed files
  were not changed. New standalone JS enters Forge's script list on Reload UI.

### Source import buttons — 2026-10-22, local only

- User preferred a less invasive workflow: open an IIB lightbox, leave it open,
  switch to Image Edit and import. Removed automatic menu injection; integration
  now reads public DOM/file URLs only when the button is pressed.
- Added txt2img import using its selected thumbnail/large preview, scoped to
  that gallery even when the Image Edit tab is active. Do not guess the first
  image of an unselected batch or use another tab's modal/live-preview image.
- Both actions pass original bytes into the existing metadata-preserving source
  and recipe handoff. Prompt extraction remains explicit via Get prompt from
  metadata. IIB thumbnail URLs are resolved to original files before download.
- Both buttons and question-mark instructions sit to the right of Crop / outpaint
  under Generate / Cancel, bounded by the left column. Fixed 34px controls and
  zero checkbox/button margins align their centers. Long success text no longer
  consumes space: the button briefly says Imported ✓, with filename on hover.
  Errors are temporary anchored popovers, not extra layout rows.
- No clipboard-path import: user explicitly canceled that idea. Explorer drag
  and drop is unchanged. No GitHub push or change to IIB's installed files.
- Backup before implementation: `C:/CODEX/forge-image-edit-backups/20261022-iib-pull-import`.
  Installed-file backups: `20261022-060449-source-imports-local` and
  `20261022-060922-source-imports-local` under the same backup root.
- Python suite: 145 tests passed; Node suite: 31 tests passed. Focused import
  tests rerun after changing feedback behavior: 11 passed. Compile and diff
  checks passed. Browser validation and final layout checks recorded below.
- Headless Edge: older/current upstream IIB and older/current Forge Neo XL all
  passed importing after hiding the host tab, next-image selection, exact
  original-file length, download failure/retry and closed-lightbox rejection.
  No IIB menu elements were injected.
- Live Forge page: a real Gradio gallery populated with three synthetic fixture
  images imported the selected third image, not the first. The original bytes
  matched exactly (including custom PNG metadata); Get prompt from metadata
  recovered its saved prompt. Replacing it via a current IIB lightbox after
  switching tabs passed the same byte-exact and prompt-extraction checks.
  No generation was submitted and no private user images were used in QA.
- Final layout check measured a **34px row** and **0px centerline spread** across
  crop checkbox/help and both import buttons/help. Row and prompt positions
  stayed identical while loading, showing Imported ✓, restoring labels and
  showing an error. Long filenames did not expand layout; 800px viewport had
  no overflow beyond the Cancel button's column.
- QA harnesses: `C:/CODEX/image-edit-browser-qa/source-imports-qa.cjs` and
  `source-imports-layout.cjs`. Fixtures, screenshots, `compat-results.json`,
  `results.json` and `layout-results.json` are in
  `C:/CODEX/image-edit-browser-qa/artifacts/source-imports`.
- New controls were installed with an idle UI reload. Subsequent JS/CSS changes
  need only a browser refresh. The user's Canary page was not controlled;
  validation used separate headless Edge sessions.

### Model selection UX — completed locally 2026-10-22

- User reported selecting Fibo while the Qwen UI preset remained selected, then
  changing UI Preset to Fibo restored a Qwen checkpoint and disabled Generate.
- Confirmed config had the Qwen checkpoint saved under `forge_checkpoint_fibo2`
  and the Fibo checkpoint under `forge_checkpoint_qwen21`. Forge's checkpoint
  input saved into the currently displayed layout regardless of model family.
- Latest user decision: one Image Edit workspace detects supported checkpoints;
  top fields are authoritative. Replace the mutating matching-components button
  with read-only **Check model setup**, keep eligibility independent of layout,
  sync layout on manual checkpoint input and prevent crossed-family preset saves.
- Implemented in extension callbacks, without rewriting Forge core or adding a
  global Image Edit preset. Selecting a checkpoint saves it under its real family;
  changing layouts cannot restore a checkpoint from the other family. Reloads
  preserve a manually chosen component pair, including custom/incomplete choices.
- **Check model setup** refreshes detection and reports readiness without changing
  checkpoint, encoder or VAE. A missing selection now names the expected file,
  for example `Missing VAE: flux2-vae.safetensors`, in persistent status and a
  check-button notification. Files absent from disk are named separately.
- Latest user decision: allow users to bypass filename matching for renamed,
  fine-tuned or fixed encoder/VAE weights if they choose. Added **Extras → Allow
  custom encoder / VAE filenames** and **Which selected file is the VAE?**.
  The other selected file is the encoder. It starts off; enabled mode requires
  two distinct existing files and a selected role. It does not bypass checkpoint
  architecture/backend support or guarantee that arbitrary weights will load.
- Preserve roles and the opt-in in PNG recipes. Legacy recipes turn the override
  off. The setting is not saved as a global default. Generation revalidates the
  submitted files; the checkbox is not just a UI-only unlock.

### Result-to-source transfer — completed locally 2026-10-22

- User reported intermittent failure in their open Canary tab. Available browser
  inventory did not expose that tab, so its exact failure was not reproduced.
  A separate fresh local integration session passed the original first transfer.
- Replaced the queued server image round trip with a direct full-PNG fetch from
  the displayed result into the source canvas. Keep metadata bytes and current
  prompt/model settings; don't import a recipe or trigger generation on reuse.
- Decode before replacing source/paint, show loading feedback, ignore overlapping
  clicks, and report fetch/decode errors without erasing the current source.
- Reproduced a distinct repeated-reuse bug in live UI: identical image bytes skip
  Gradio's source-change event, leaving old crop-number values even though the
  preview and painting reset. Force the canvas reload and reset the four edge
  inputs explicitly, including on identical result bytes.
- Latest local runtime backup:
  `C:/CODEX/forge-image-edit-backups/20261022-024603-model-switch-iib-local`.
  UI reload was requested only while port 7860 was idle. No model downloads,
  other-extension edits, port 7861 changes, commits, tags or GitHub push.

### Model setup and reuse validation — 2026-10-22

- **145 Python tests passed**; **24 Node tests passed** (the four reuse tests
  also passed again after adding explicit stale-edge regression assertions).
  Python compilation and `git diff --check` passed.
- Tests cover crossed preset entries, no selector mutation on setup checks,
  exact missing filenames, custom opt-in/roles/existing files, old caller
  compatibility, generation dispatch, saved metadata and 35-output recipe import.
  Custom-role generation/save was tested for both Qwen and Fibo using CPU model
  stand-ins; no claim of compatibility with arbitrary custom weights.
- Final live Edge run passed: manually selecting Qwen while Fibo is active
  keeps the user's component selections and synchronizes UI Preset; switching
  presets returns the correct checkpoint and pair. Read-only checks leave fields
  unchanged. Removing FLUX VAE shows its exact name in status and notification.
- Custom mode starts off, enables with a complete selection, honors explicit
  VAE/encoder roles rather than guessing them back, and returns to normal
  validation when unchecked. Tested without loading deliberately reversed roles.
- A model-free crop supplied a real saved PNG. First reuse and identical reuse
  passed, including source dimensions, exact full-PNG bytes, cleared painting and
  all crop edges, unchanged model settings and prompt. Simulated HTTP 404 leaves
  source intact, displays an error and permits a successful retry.
- Browser test/artifacts:
  `C:/CODEX/image-edit-browser-qa/model-switch-local.cjs` and
  `C:/CODEX/image-edit-browser-qa/artifacts/model-switch-local/results.json`.
  Earlier failed attempts were test-selector/reload-readiness issues; the final
  complete run passed. Captured unrelated existing errors from Dynamic Prompts,
  Scramble Prompts, openOutpaint and Forge `script.js`; none from Image Edit.
- Tests used a separate headless Edge session and the public robot fixture, not
  the user's Canary tab or private image. No GPU generation was started. Final
  global selection was restored to Fibo. Refresh the user's existing browser tab
  to load the new controls and scripts.
- Include the new `model_switch.py`, `image_edit_iib.js`, new Python/Node tests and
  this log in the eventual cumulative release. Leave version/release manifests
  describing published 0.5.21 until the user explicitly requests publication.

## Repositories and running application

- The publication checkout is the source of truth; the installed extension is a
  separate copy. Apply and verify changes in both when updating the running UI.
- Running Image Edit uses the existing Forge application on port **7860**.
  Do not alter the other Forge instance on port 7861.
- Back up installed files before replacing them. Check that generation is idle
  before reloading UI; do not discard a user's in-progress generation unnecessarily.
- Reload UI is needed for Python layout changes; browser refresh loads new JS/CSS.
- Gradio regenerates `canvas.pyi` during startup, so its runtime hash can differ
  from the release manifest without a source-code change.

## Current interface decisions

- Main heading: **Image Edit**, with exact checkpoint/encoder/VAE guidance.
- Source on the left, result on the right. **Generate / Cancel** directly below source.
- **Crop / outpaint** remains outside all Settings/Extras accordions, between
  Generate/Cancel and the settings row. Its four edge controls expand immediately
  under the checkbox, followed by canvas summary, seam blending and Reset edges.
- **Settings** contains Seed/Batch, Speed/quality, Resolution, output summary and
  shared Custom output size → Resize to / Resize by controls.
- **Extras** contains Edit mode, Shift and RoPE. Settings and Extras start collapsed,
  have left-side arrows, and share a vertically aligned header row on wide screens.
  They stack on narrow screens. Prompts follow directly below them.
- Closing sections must preserve their values and must not move Generate down.
- Long explanations belong in small **?** tooltips. Avoid adding vertical prose.
- One shared sizing UI serves whole-image and crop/outpaint modes. No separate
  outpaint Shrink by / percentage dropdown. Within Settings the size controls stay
  visible even when Custom output size is unchecked; editing a size enables it.
- Width/height link immediately in the browser. For outpaint they use the full
  planned canvas ratio, including signed edges. Submission captures latest values.
- Resize by 0.5 halves both dimensions; 2 doubles both. Custom output is actual
  working/saved size, not just an output upscale. Extra references use Resolution.
- Ordinary painted edits keep their source canvas size. Canvas painting can combine
  cropping, expansion and custom sizing.
- Unchanged/unpainted outpaint disables generation with an actionable message.
  Crop-only/resize-only uses Apply crop / Apply resize without model inference.
- Retired auto-correct global brightness/contrast UI stays removed, including when
  importing older recipes. Its hidden API slot is retained for compatibility.

## Existing editing features and rationale

- Whole-image, painted and crop/outpaint edits for Qwen Image 2.1 and Fibo 2.0.
- Painting remains available during outpaint to remove unwanted edge objects.
- Seam blending crossfades generated pixels inside the retained image after
  inference; it does not spatially blur the image or feed a soft grey mask.
- Extra references can guide painted and expanded regions. Original pixels outside
  painting/seam support are preserved (relative to the resized original if sizing).
- Fibo result-description field is a structured finished-image caption in addition
  to the edit instruction. Metadata prompt extraction provides a starting caption.
- Prompt image-tag buttons insert image_1/image_2/image_3 references. Filled reference
  slots determine numbering; models can still borrow unwanted identity/scene traits.
- Expression-transfer preset supplies expression-only guidance, not a guarantee.
  If the reference takes over: describe the expression in words, remove references,
  use Standard/appropriate painted mode and paint the face to contain the change.
- Reference curves are non-destructive: originals remain; adjusted pixels go to the
  model. Source image_1 is available as a color comparison alongside reference curves.
- Result curves support selection restriction/softening and movable black/white
  endpoints. Curve application preserves the previous saved result.
- Fibo Shift and experimental RoPE are independent of output resizing and work with
  global, painted and outpaint edits. Fibo manual Shift default is 1.15; current
  experimental spatial RoPE scaling is X 0.85 / Y 0.80.
- Outpaint scene-continuation guidance was strengthened for borders interpreted as
  a framed picture on a grey wall. It helps but does not guarantee successful filling.
- Automatic native output saving, metadata/recipes, batch selection, IIB handoff,
  cancellation and model/component validation remain in place.

## Last completed local/published checks

### 0.5.19 — shared sizing and help

- One sizing UI for whole-image and outpaint; full-canvas aspect-ratio linking.
- Outpaint custom dimensions reach model input and saved result.
- Tooltips replace long explanatory paragraphs; help clicks do not toggle checkboxes.
- 123 Python tests and 16 JavaScript tests passed. Production-path CPU tests cover
  resize/paint/seam/reference/metadata routing. Live Edge checks at 1800px and 650px.

### 0.5.20 — collapsed Settings / Extras

- Layout-only change. No inference, sizing or default-value changes.
- Verified empty/loaded source, aligned left-arrow headers, elevated prompt,
  external outpaint controls, keyboard toggle, retained Seed/Shift/RoPE/custom sizes,
  and narrow layout without horizontal overflow.
- All GitHub CI jobs passed before the final authorized release.
- Local validation details are in `VALIDATION.json`; changelog in `CHANGELOG.md`.

## 0.5.21 installation hotfix — published by explicit request

- Reddit reports: fresh installs show Image Edit but no `fibo2` preset, with a
  vague Backend setup required message. The latest extension alone did not help.
- Reproduced against current Neo `2c24de162d08a70829cd56bf6cd4bb4f60258b68`.
  Upstream MOSS support changed five files covered by the old installer signature.
  The old helper declined safely; it did not install native Fibo support.
- Added a reviewed 18-file patch preserving all MOSS/Qwen3.5 additions. MOSS stays
  preset enum 14; Fibo uses 15. Old supported patches remain available.
- Improved missing-files vs unloaded-registration UI guidance, revision/mismatched
  file diagnostics, and exact check/apply/full-restart steps in COMPATIBILITY.md.
- Verified install.py on another clean checkout, every installed hash, six relevant
  Fibo CPU tests, and fresh UI startup on temporary port 7862 with both presets and
  Image Edit present. Test server stopped afterward; 7860/7861 untouched.
- Release tests: 125 Python + 16 JavaScript. All five GitHub CI jobs passed:
  Windows/Linux extension tests and all three backend base check/apply jobs.
- Published main commit above and v0.5.21-beta.1 with a manifest-verified ZIP.
  Release: https://github.com/tranquil222/forge-image-edit/releases/tag/v0.5.21-beta.1
- Used an isolated release worktree so Qwen Shift/RoPE did not enter this hotfix.
  Main checkout fast-forwarded; pending work restored with only a changelog merge
  needed. A named stash and file backup retain the pre-merge pending changes.
- User-facing update: Extensions → Installed → Check for updates → apply Image
  Edit; fully close the Forge console/process and relaunch. Browser refresh or
  Reload UI alone cannot load newly installed backend registration.
- Their exact Forge revision was not supplied; the fresh-current-Neo failure is
  confirmed, but a different fork/build still needs the documented setup check.

## Completed locally — Qwen Shift / RoPE (not published)

- Added Qwen **Shift mode / Shift / RoPE adjustment** to Extras, using the same
  labels and arrangement as Fibo. Model-specific groups remain internally
  conditional, but both supported families now have the same controls.
- Separate values prevent Fibo defaults leaking into Qwen when switching models.
  Qwen starts at **Manual 0.69**, RoPE off. Fibo stays at Manual 1.15, RoPE off.
- Qwen Image-size adjusted matches the local backend's working-grid formula:
  256–8192 image tokens map to 0.5–0.9, clamped to that range.
- Qwen Simple uses predictor Shift. CyberZit Quality and official Turbo have
  fixed sigma grids, so nondefault Shift applies a log-SNR delta relative to 0.69.
  At Manual 0.69, the existing schedule is used without any transformation.
- Qwen RoPE scales image XY positions by X 0.85 / Y 0.80. Qwen interleaves text,
  references and output; exact image spans are derived from that layout. Text
  positions and image-plane/order positions remain untouched.
- Qwen hooks use `pe_embedder`, not Fibo's `rope_embedder`. Hooks are job-scoped,
  removed in `finally`, and prefix caches clear at both boundaries. Unsupported
  backends fail explicitly rather than silently ignoring the setting.
- Both controls work independently of resizing, including painted and outpaint
  jobs. This is an experimental adaptation, not an established quality fix or a
  claim that the Fibo workflow transfers identically to Qwen.
- Qwen settings are recorded in PNG recipes and restored on import. Old Qwen
  recipes restore Manual 0.69 / RoPE off. Importing one family leaves the other
  family's controls alone. Existing API input slots stay unchanged; three Qwen
  fields are appended. Older direct callers still use the defaults.
- Updated canonical checkout and installed extension after backing up runtime
  files. Reloaded the idle UI. No Forge core files or model weights changed.
- Updated README / local Unreleased changelog. **Qwen edits remain uncommitted and
  unpublished.** These edits await a requested cumulative release; only the
  separate installation hotfix above was authorized and published.

### Validation completed

- **129 Python tests passed**, including fixed-grid/default scheduling, invalid
  values, exact image-only RoPE spans, cleanup on errors, metadata and model/input
  dispatch for whole-image, painted and outpaint jobs.
- **16 JavaScript tests passed**; submission test now covers the appended Qwen
  controls without moving existing image/curve/resize inputs.
- Live Edge: collapsed Extras, Qwen defaults, Manual/automatic Shift interactivity,
  Qwen → Fibo → Qwen with independent retained values, RoPE available in outpaint,
  aligned Settings/Extras and narrow layout. Original Qwen checkpoint restored.
- Live PNG import: baseline, changed Shift, RoPE-on, and a legacy Qwen recipe.
  Values restored correctly; inactive Fibo controls were left untouched.
- Four controlled GPU jobs: Qwen Q8_0, Qwen VAE, 8B encoder, 512×512, seed 42,
  4 Euler / CyberZit Quality steps, public robot fixture. Baseline 0.69/off,
  Shift 1.15/off, RoPE 0.69/on, then baseline 0.69/off again.
- Shift and RoPE each produced different pixels. Final baseline matched the first
  baseline **exactly**, showing no observed RoPE/cache carryover for this case.
  These were wiring/isolation tests, not a quality benchmark.
- Local QA artifacts: `image-edit-browser-qa/artifacts/qwen-sampling-local`
  contains output PNGs, GPU results, UI screenshots/results and recipe results.
  Runtime backup: `forge-image-edit-backups/20261021-qwen-sampling-local`.

### Historical publication checklist — superseded by 0.5.22 authorization

Prepare the cumulative release from the last published commit above. Include all
local changes, update version/validation/package manifests as appropriate, and run
release checks before publishing. Do not run publication tooling merely to finish
this local task. For the now-authorized 0.5.22 update, `VALIDATION.json` and
`RELEASE_FILES.json` are updated with the cumulative checks and file manifest.

## Completed locally — Qwen green outpaint borders (not published)

- Reported output: `00426-2523287606581937943.png`, Qwen Image 2.1 Q8_0,
  12 Res Multistep / CyberZit Quality steps, resolution 768, seed
  `2523287606581937943`, left 377 / right 280 / top 0 / bottom 0. Final canvas
  1681 × 1024. Shift was the normal 0.69 and RoPE was off.
- Both saved borders were almost pure green. The input path deliberately paints
  Qwen's replacement guide green; the final compositor cannot introduce that
  colour because its underlying canvas is grey.
- Compared the old automatic prompt and shorter instructions at the same seed
  and settings. Used a 1024 × 1024 retained crop recovered from the saved failure;
  its seam strips may differ from the original upload. Every comparison used
  this same recovered source. No claim of exact original-upload reproduction.
- Old prompt + green input reproduced the green borders. Old prompt + grey input
  likewise retained grey borders. Short direct replacement instructions filled
  both colours. A generic short instruction also filled both green borders.
  Near-fill fraction in added regions: old green 100%, old grey 100%; short green,
  short grey and generic green each 0%. Outputs were also visually inspected.
- Changed only Qwen's automatic outpaint guidance to lead with replacing the
  green areas and continuing the visible scene. Preserve the user's instruction;
  painted-plus-outpaint also requests the inner painted edit and preserves only
  unmasked content. No hardcoded description of this particular scene.
- Kept Qwen's green guide, Fibo's grey mask, the grey canvas preview, generation
  settings, reference ordering and final compositing unchanged. Fibo's generated
  prompts remain byte-for-byte identical for blank/plain/structured prompts,
  with and without painting. Ordinary Qwen painted edits are unchanged.
- **132 Python tests passed** and `git diff --check` passed. Added coverage for
  Qwen prompt dispatch, preservation of user instructions, painted-area handling,
  extra references and saved effective prompt metadata.
- Backed up and synced canonical changes into the installed extension; reloaded
  the idle production UI. Full production outpaint/save at the failing seed now
  fills the borders. Verified 1681 × 1024 output, new effective prompt, default
  Shift/RoPE, no green border fill, and exact source pixels outside seam blending.
- A user's separate job started after this check. The QA script detected it and
  stopped before submitting the planned second-seed / four-edge checks. Those
  extra cases were **not run**, and the user's job was not interrupted.
- QA: `C:/CODEX/image-edit-browser-qa/artifacts/qwen-outpaint`, including
  `probe-results.json`, `production-results.json`, inputs and generated PNGs.
  Runtime backup: `C:/CODEX/forge-image-edit-backups/20261021-qwen-outpaint-local`.
- No Forge core changes, model downloads, commits, tags, releases or GitHub push.
  This fix and the earlier Qwen controls await the user's cumulative release.

## Handoff rules

- Follow the newest user steering; do not restart already completed layout work.
- Keep messages plain, direct and concise. Ask only for genuinely missing details.
- Do not add cloud services, send messages to others, or launch another model service.
- Do not regenerate user images merely to verify a layout-only change. For sampling
  changes, use appropriate CPU tests and a small controlled live check when needed.
- Do not claim new GPU quality improvement from control wiring or CPU tests alone.
