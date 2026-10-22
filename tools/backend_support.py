"""Check or install pinned Qwen 2.1 + Fibo 2.0 support; never update Forge."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from datetime import datetime


def digest(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() if path.is_file() else None


def unknown_files(root, manifest):
    """Only exact original OR exact shipped-patch files are repairable."""
    return [item["path"] for item in manifest["files"]
            if not (root / item["path"]).resolve().is_relative_to(root)
            or digest(root / item["path"]) not in (item["before_sha256"], item["after_sha256"])]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forge-root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="Install or repair only verified backend files; default is check-only.")
    args = parser.parse_args()
    root = args.forge_root.resolve()
    if not (root / "launch.py").is_file():
        raise SystemExit("Not a Forge checkout: launch.py is missing.")
    support = Path(__file__).resolve().parents[1] / "backend-support"
    backend = root / "backend/nn/qwen21.py"
    fibo = root / "backend/nn/fibo2.py"
    revision = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    print(f"Forge revision: {revision}")
    manifests = [(path, json.loads(path.read_text())) for path in sorted(support.glob("manifest*.json"))]
    exact = next(((path, data) for path, data in manifests if data["base_commit"] == revision), None)
    # A Forge update can restore tracked files while leaving added model files.
    # Accept only a complete known before/after signature, never arbitrary edits.
    match = exact if exact and not unknown_files(root, exact[1]) else next(
        ((path, data) for path, data in manifests if not unknown_files(root, data)), None)
    if match is None:
        # Preserve already-integrated customized installations, but do not call
        # them complete merely because one model flag exists.
        required = {"backend/loader.py": ("Fibo2Transformer2DModel",),
                    "backend/args.py": ("fibo2: bool", "qwen21: bool", "qwen21_auto_shift", "qwen21_prefix_cache"),
                    "modules_forge/presets.py": ("fibo2 =", "qwen21 ="),
                    "modules_forge/main_entry.py": ("layout_only",),
                    "modules_forge/packages/huggingface_guess/detection.py": ('dit_config["fused_mlp"]',)}
        if backend.is_file() and fibo.is_file() and all(
                (root / name).is_file() and all(marker in (root / name).read_text(encoding="utf-8") for marker in markers)
                for name, markers in required.items()):
            print("Qwen 2.1 and Fibo 2.0 backend registrations and model-bar support found. No files changed. Run a generation to verify your environment.")
            return
        closest, differences = min(((data, unknown_files(root, data)) for _, data in manifests), key=lambda pair: len(pair[1]))
        print(f"Closest supported base: {closest['base_commit']}")
        print("Affected files that do not match:\n" + "\n".join(f"  {name}" for name in differences))
        if exact:
            raise SystemExit(f"Customized or unsupported file: {unknown_files(root, exact[1])[0]}. No files changed; manual integration is required.")
        raise SystemExit("Backend setup required for this Forge build. No files changed. "
                         "The extension UI is installed, but native model support was not applied. "
                         "This installer targets Haoming02 Forge Neo (neo branch), not every Forge fork. "
                         "Update Image Edit, fully stop and relaunch Forge, then run this check again. "
                         "If it still fails, send this output and your Forge repository/branch; repeated restarts will not fix a file mismatch. "
                         "See COMPATIBILITY.md for exact steps.")
    manifest_path, manifest = match
    patch = support / manifest["patch"]
    if digest(patch) != manifest["patch_sha256"]:
        raise SystemExit("Backend patch checksum mismatch. No files changed.")
    pending = []
    for item in manifest["files"]:
        target = (root / item["path"]).resolve()
        if not target.is_relative_to(root):
            raise SystemExit("Invalid backend path. No files changed.")
        current = digest(target)
        if current == item["after_sha256"]:
            continue
        if current != item["before_sha256"]:
            raise SystemExit(f"Customized or unsupported file: {item['path']}. No files changed; manual integration is required.")
        pending.append(item)
    if not pending:
        print("Qwen 2.1 and Fibo 2.0 backend registrations and model-bar support found. All patched files verified. No files changed.")
        return
    partial = len(pending) < len(manifest["files"])
    if partial:
        print(f"Verified partial backend installation: {len(pending)} file(s) need repair.")
    # Some upstream files store CRLF in Git itself. Exact normalized file hashes
    # above already checked the content; tolerate line endings in patch context.
    apply_command = ["git", "-C", str(root), "apply", "--ignore-space-change",
                     *[f"--include={item['path']}" for item in pending]]
    subprocess.run([*apply_command, "--check", str(patch)], check=True)
    if not args.apply:
        print("Compatible backend files; patch check passed. Add --apply to install or repair the backend. No files changed.")
        return
    backup = root / "image-edit-backups" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup.mkdir(parents=True, exist_ok=False)
    # A repair backup must describe only files it changes, not previously-added
    # model files that recovery could otherwise mistake for newly-created files.
    (backup / "manifest.json").write_text(json.dumps({**manifest, "files": pending}, indent=2) + "\n", encoding="utf-8")
    for item in pending:
        path = root / item["path"]
        if path.is_file():
            saved = backup / item["path"]
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, saved)
    subprocess.run([*apply_command, str(patch)], check=True)
    for item in manifest["files"]:
        if digest(root / item["path"]) != item["after_sha256"]:
            raise SystemExit(f"Installed hash mismatch: {item['path']}. Backup: {backup}. Do not start Forge until this is resolved.")
    print(f"Backend {'repaired' if partial else 'installed'} without pulling/updating Forge. Backup: {backup}. Fully restart Forge.")


if __name__ == "__main__":
    main()
