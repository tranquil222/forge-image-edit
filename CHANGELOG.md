# Changelog

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
