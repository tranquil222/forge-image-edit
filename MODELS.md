# Optional model sets

Install only the model(s) you want. Turbo and Dev are separate checkpoints;
Fibo Dev is not downloaded when you choose Turbo. Fibo variants share their
encoder and VAE; Qwen variants share their own encoder and VAE.

| Family | Checkpoint | Text / vision encoder | VAE | UI preset |
| --- | --- | --- | --- | --- |
| Qwen 2.1 | `qwen_image_2.1_int8_convrot.safetensors` | `qwen3vl_8b_int8_convrot.safetensors` | `qwen_image_2.1_vae_bf16.safetensors` | `qwen21` |
| Qwen 2.1 Turbo | `qwen_image_2.1_turbo_int8_convrot.safetensors` | same Qwen 8B | same Qwen 2.1 VAE | `qwen21` |
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

The Hugging Face CLI is another option: `hf download Comfy-Org/Fibo-2.0`
with individual filenames. Do not download a whole repository unless you want
all its variants. `models.json` records the exact tested files and hashes.

The repack repositories link to the applicable weight licenses. These licenses
are separate from the extension code license; no weights are redistributed here.
