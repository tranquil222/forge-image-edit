# Optional model sets

Install only the model(s) you want. Turbo and Dev are separate checkpoints;
Fibo Dev is not downloaded when you choose Turbo. Fibo variants share their
encoder and VAE; Qwen variants share their own encoder and VAE.

| Family | Checkpoint | Text / vision encoder | VAE | UI preset |
| --- | --- | --- | --- | --- |
| Qwen 2.1 | `qwen_image_2.1_int8_convrot.safetensors` | `qwen3vl_8b_int8_convrot.safetensors` | `qwen_image_2.1_vae_bf16.safetensors` | `qwen21` |
| Qwen 2.1 Turbo | `qwen_image_2.1_turbo_int8_convrot.safetensors` | same Qwen 8B | same Qwen 2.1 VAE | `qwen21` |
| Qwen 2.1 Turbo, smaller set | `qwen_image_2.1_turbo_Q4_K_M.gguf` | `qwen3vl_8b_w4a8.safetensors` | same Qwen 2.1 VAE | `qwen21` |
| Fibo Edit Turbo | `fibo2_edit_turbo_int8_convrot.safetensors` | `qwen3vl_4b_int8_convrot.safetensors` | `flux2-vae.safetensors` | `fibo2` |
| Fibo Dev | `fibo2_dev_int8_convrot.safetensors` | same Fibo 4B | same FLUX.2 VAE | `fibo2` |

Do not substitute Krea's Qwen image VAE for Fibo's FLUX.2 VAE, or Qwen's older
2509/2511 components for Qwen 2.1. Compatible BF16 component variants may also
be selected; keep publisher filenames. Tested quantization/hardware is listed
in VALIDATION.json, not implied by a filename match.

## Obtain files

- [Qwen 2.1 and Turbo files](https://huggingface.co/Comfy-Org/Qwen-Image-2.1/tree/main)
- [Fibo Dev and Edit Turbo files](https://huggingface.co/Comfy-Org/Fibo-2.0/tree/main)
- [Fibo Turbo reference](https://huggingface.co/briaai/Fibo-2.0-edit-turbo)
- [Fibo Dev reference: 50 steps, CFG 5](https://huggingface.co/briaai/Fibo-2.0-dev)

Place diffusion weights in `models/Stable-diffusion`, encoders in
`models/text_encoder`, and VAEs in `models/VAE`. Forge's custom model directories
are supported by the UI. Use the top Refresh button after adding files.

Alternatively, from the Forge root, check a pinned model set without downloading:

```powershell
.\venv\Scripts\python.exe extensions\forge-image-edit\tools\models.py --forge-root . --model fibo2-turbo
```

Add `--download` to explicitly install it, or `--verify` to hash installed files.
Other model choices: `fibo2-dev`, `qwen21`, `qwen21-turbo`. The helper pins the
publisher revision, checks size and SHA-256, reuses matching files, and refuses
to overwrite different files. Custom directories can be passed with
`--checkpoint-dir`, `--encoder-dir`, and `--vae-dir`. Downloads use the Hugging
Face cache, so allow disk space for both the cache and installed weights.
Authentication or publisher terms, if required, are handled through Hugging Face.

### Smaller Qwen download

The optional `--model qwen21-turbo-q4` set uses these files:

- [Abiray Q4_K_M Turbo checkpoint, 4.19 GB](https://huggingface.co/Abiray/Qwen-Image-2.1-Turbo-GGUF/blob/main/qwen_image_2.1_turbo_Q4_K_M.gguf) → `models/Stable-diffusion/`
- [Comfy-Org Qwen3-VL 8B W4A8 encoder, 6.31 GB](https://huggingface.co/Comfy-Org/Qwen-Image-2.1/blob/main/text_encoders/qwen3vl_8b_w4a8.safetensors) → `models/text_encoder/`
- [Qwen Image 2.1 VAE](https://huggingface.co/Comfy-Org/Qwen-Image-2.1/blob/main/vae/qwen_image_2.1_vae_bf16.safetensors) → `models/VAE/` (reuse your existing copy).

Sizes above are downloads, not VRAM requirements. You may keep the Qwen3-VL 8B
INT8 encoder instead of downloading W4A8. Select only one encoder and one VAE;
**Use matching encoder / VAE** preserves an already-selected compatible encoder.
When neither is selected, explicitly pick W4A8 if both variants are installed.
Keep **Diffusion in Low Bits: Automatic** and the Turbo 8-step official preset.
Smaller weights can change output quality and do not necessarily run faster.
GGUF edits automatically offload the encoder after conditioning, leaving room
for the diffusion model's temporary dequantization workspace. No extra toggle
or launch flag is needed for this.

Use the linked single-file multimodal encoder, not a language-only chat GGUF
and separate mmproj. Fibo still needs its own Qwen3-VL **4B** encoder and FLUX.2
VAE; Qwen's smaller **8B** encoder is not a substitute for it. Fibo's official
repack currently supplies BF16 and INT8 checkpoints, not a Q4 set.

### 12 GB and 16 GB VRAM

Start at **512–768 resolution on 12 GB**, or **768–1024 on 16 GB**, with one
source image. Leave Forge's normal automatic CPU offloading enabled. Offloading
uses system RAM; model file sizes do not all need to fit in VRAM simultaneously.

For Qwen, after choosing the quality preset, open **Sampling settings** and
turn off **Cache reference attention between steps**. Changing the preset can
enable it again. Fibo does not use that cache. Reduce resolution to 512 if needed.

See [VALIDATION.json](VALIDATION.json) for exact combinations and measured peaks.
Memory-limited runs on an RTX 3090 are not physical 12/16 GB GPU certification;
other cards, drivers, references and resolutions can behave differently. Other
quantizations/publishers are not automatically covered by those tests.

The Hugging Face CLI is another option: `hf download Comfy-Org/Fibo-2.0`
with individual filenames. Do not download a whole repository unless you want
all its variants. `models.json` records the exact tested files and hashes.

The repack repositories link to the applicable weight licenses. These licenses
are separate from the extension code license; no weights are redistributed here.
