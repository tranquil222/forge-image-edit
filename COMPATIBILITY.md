# Backend compatibility

The editing UI is an extension. Qwen 2.1 and Fibo model implementations also need
native Forge backend support. The URL installer adds this support when the
affected files match a verified patch. Compatible existing backends are kept.

Normal use has no compatibility popups. If setup is incomplete, Image Edit shows
one actionable setup message and disables generation. Other Forge tabs are not
disabled. Technical details stay in the console and this guide.

## `fibo2` is missing from UI Preset, or “Backend setup required”

The **Image Edit tab** and **native model support** are separate parts of setup.
The tab can install successfully while the backend patch is skipped. “Latest” in
Extensions means the extension is up to date, not that native support was installed.
Moving the checkpoint cannot add the missing `fibo2` preset.

1. Confirm you are using **Forge Neo**, the **`neo` branch** of
   [Haoming02/sd-webui-forge-classic](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo).
   A fresh installation of a different Forge fork is not the same backend.
2. In **Extensions → Installed**, check for updates, select Image Edit and apply
   the update. **0.5.24 repairs verified partial backend installations**, including
   a missing `fibo2` preset after a Forge update. This also restores the Qwen
   editing hooks required by Image Edit; Qwen 2.1 Turbo is supported.
3. **Fully stop Forge**, including its console/process, then start it with your
   normal launcher. Closing the browser, refreshing, or **Reload UI** is not a
   full restart. The installer runs during startup unless installation is skipped.
4. Check **UI Preset** for `fibo2`. Choose the checkpoint in the top model bar,
   select its encoder/VAE and use **Image Edit → Check model setup**. Checkpoints belong in
   `models/Stable-diffusion`; encoders in `models/text_encoder`; VAEs in `models/VAE`.
5. If the message remains, **stop Forge again**, open PowerShell in the Forge
   folder containing `launch.py`, and run the check below. It does not change files:

```powershell
.\venv\Scripts\python.exe .\extensions\forge-image-edit\tools\backend_support.py --forge-root .
```

Use the actual extension folder shown in **Extensions → Installed**. Older
installations may call it `forge-qwen-edit`; substitute that name in the command.
For a portable install without `venv`, use the Python executable used by its
launcher, not an unrelated system Python. On Linux use `./venv/bin/python`.

| Check result | What to do |
| --- | --- |
| `Compatible backend files; patch check passed` | With Forge stopped, run the apply command below, then relaunch. |
| `Verified partial backend installation` | Some files are already patched and others need repair. With Forge stopped, run the apply command below, then relaunch. |
| `backend registrations and model-bar support found` | Native support is on disk. Fully restart the same Forge installation. If the preset is still missing, send the check output and startup log. |
| `Backend setup required for this Forge build`, `Customized or unsupported file`, or `Partial backend integration` | Do not keep reinstalling weights or restarting. Send the check output, including the commit and mismatched files, plus the repository/branch commands below. A reviewed patch is needed; do not force an older patch. |
| Python/script not found | Check the Forge root, extension folder name and Python path used by your launcher. |

Apply **only after the compatible check passes**, while Forge is stopped:

```powershell
.\venv\Scripts\python.exe .\extensions\forge-image-edit\tools\backend_support.py --forge-root . --apply
```

For a setup report, copy the check output and these command results. No model
files or full image-generation history are needed:

```powershell
git remote get-url origin
git branch --show-current
git rev-parse HEAD
```

If automatic setup never ran, check your launcher for `--skip-install` or
`--skip-prepare-environment`, and for `FORGE_IMAGE_EDIT_SKIP_BACKEND=1`.
The explicit check/apply commands above bypass those startup skips.

Adding a checkpoint file alone cannot remove the `fibo2` preset. A Forge update
can replace its registration files while leaving added backend modules behind.
The repair accepts only exact original/patched file combinations and restores
the missing pieces. A stale running process instead needs a full restart after
the on-disk installation is complete; Reload UI does not reload the backend.

## How the check works

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
- Verified partial installation: the same checks accept each file only at its
  exact original or patched hash; apply changes only the still-original files.
- Customized/mismatched affected files or unknown partial integration: skips automatic
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
| `6b3a78d7384a46ccea43129b7af808b8d621eb44` | Current Neo: affected files match the MOSS-enabled signature below; clean install and partial repair verified. |
| `2c24de162d08a70829cd56bf6cd4bb4f60258b68` | MOSS-enabled Neo: adds Fibo without replacing MOSS/Qwen3.5 support; registers `fibo2` separately from `moss`. |
| `dc0145513e4fe9274e71bc3fd3ea2cb97a5bd8c9` | Pre-MOSS Neo: Fibo support, Qwen editing engine/cache and model-bar integration; keeps the newer upstream VAE, LLM, latent definitions and refresh callbacks. |
| `41359cd4b8b89212b3dbad8c9af719160a12ed63` | Older public Forge: includes the Qwen 2.1 backend in addition to Fibo and model-bar support. |

All patches include separate/fused Qwen MLP validation. File lists and
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
