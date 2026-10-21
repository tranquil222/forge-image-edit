# Backend compatibility

The editing UI is an extension. Qwen 2.1 and Fibo model implementations also need
native Forge backend support. The URL installer adds this support when the
affected files match a verified patch. Compatible existing backends are kept.

Normal use has no compatibility popups. If setup is incomplete, Image Edit shows
one actionable setup message and disables generation. Other Forge tabs are not
disabled. Technical details stay in the console and this guide.

## Check first

The URL installer performs these checks automatically. For a manual check,
or when automatic setup was skipped, use the commands below. Set the environment
variable `FORGE_IMAGE_EDIT_SKIP_BACKEND=1` to install only the extension UI.

Close Forge before applying a backend patch. From your Forge root on Windows:

```powershell
.\venv\Scripts\python.exe extensions\forge-image-edit\tools\backend_support.py --forge-root .
```

On Linux use `./venv/bin/python` and forward slashes. If you retained the old
extension directory name, substitute `forge-qwen-edit` in these commands.

- Existing backend registrations, Qwen MLP detection fix, and model-bar support:
  reports the features found; writes nothing. Runtime validation is still needed.
- Supported backend file set: verifies every affected file, patch checksum,
  and `git apply --check`; writes nothing by default.
- Customized/mismatched affected files or partial integration: skips automatic
  patching. Unrelated customizations and README-only updates do not prevent setup
  when all affected files still match a verified signature.

For a compatible clean base, add `--apply` to the same command. The helper backs
up affected files under `image-edit-backups/`, applies the focused patch, checks
all resulting hashes, and asks for a full restart. It never pulls, changes your
branch, or upgrades dependencies.

## Supported clean bases

Repository: https://github.com/Haoming02/sd-webui-forge-classic

| Public commit | Patch |
| --- | --- |
| `dc0145513e4fe9274e71bc3fd3ea2cb97a5bd8c9` | Current public Forge: Fibo support, Qwen editing engine/cache and model-bar integration; keeps the newer upstream VAE, LLM, latent definitions and refresh callbacks. |
| `41359cd4b8b89212b3dbad8c9af719160a12ed63` | Older public Forge: includes the Qwen 2.1 backend in addition to Fibo and model-bar support. |

Both patches include separate/fused Qwen MLP validation. File lists and
before/after SHA-256 hashes are in `backend-support/manifest*.json`. A different
commit is accepted when every affected file matches one of these signatures.
Unrelated local inpainting, image-browser, scheduler and personal-settings
changes are not shipped. No automatic downgrade or update of Forge occurs.

For maintainers targeting another revision: review and port the patch, then run
backend and UI tests. File presence alone is not proof of numerical parity or
compatibility. Current validation is documented in `VALIDATION.json`.

## Recovery

To undo a backend patch, close Forge and inspect the backup manifest. Restore
only the files it backed up and remove only the files listed as previously
absent. Do not overwrite later custom changes with a whole old tree. The UI
extension can be removed independently; outputs and shared model files remain.

## Dependencies

Use the dependencies required by the compatible Forge build. This extension
adds no runtime pip requirements. Its installer only checks/applies a matching
backend patch. Its model
helper uses Forge's installed `huggingface_hub` only when `--download` is passed.
Weights are not included. See MODELS.md for publisher links and component sets.
