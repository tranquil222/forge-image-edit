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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forge-root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="Apply only to the exact supported base with matching files; default is check-only.")
    args = parser.parse_args()
    root = args.forge_root.resolve()
    if not (root / "launch.py").is_file():
        raise SystemExit("Not a Forge checkout: launch.py is missing.")
    support = Path(__file__).resolve().parents[1] / "backend-support"
    backend = root / "backend/nn/qwen21.py"
    fibo = root / "backend/nn/fibo2.py"
    detector = root / "modules_forge/packages/huggingface_guess/detection.py"
    if backend.is_file() and fibo.is_file():
        if 'dit_config["fused_mlp"]' not in detector.read_text(encoding="utf-8"):
            raise SystemExit("A Qwen backend exists, but the separate/fused MLP loader fix was not found. No files changed. Review COMPATIBILITY.md; do not overwrite a customized installation.")
        required = {"backend/loader.py": "Fibo2Transformer2DModel", "backend/args.py": "fibo2: bool",
                    "modules_forge/presets.py": "fibo2 =", "modules_forge/main_entry.py": "layout_only"}
        if all((root / name).is_file() and marker in (root / name).read_text(encoding="utf-8") for name, marker in required.items()):
            print("Qwen 2.1 and Fibo 2.0 backend registrations and model-bar support found. No files changed. Run a generation to verify your environment.")
            return
        raise SystemExit("Partial backend integration found. No files changed. Review COMPATIBILITY.md for manual integration.")
    revision = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    print(f"Forge revision: {revision}")
    manifests = [(path, json.loads(path.read_text())) for path in sorted(support.glob("manifest*.json"))]
    match = next(((path, data) for path, data in manifests if data["base_commit"] == revision), None)
    if match is None:
        # README-only or unrelated upstream changes need no new patch. The
        # complete affected-file signature, not the version label, determines safety.
        match = next(((path, data) for path, data in manifests
                      if all((root / item["path"]).resolve().is_relative_to(root)
                             and digest(root / item["path"]) == item["before_sha256"]
                             for item in data["files"])), None)
    if match is None:
        closest, differences = min(((data, [item["path"] for item in data["files"]
            if digest(root / item["path"]) != item["before_sha256"]]) for _, data in manifests), key=lambda pair: len(pair[1]))
        print(f"Closest supported base: {closest['base_commit']}")
        print("Affected files that do not match:\n" + "\n".join(f"  {name}" for name in differences))
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
    for item in manifest["files"]:
        target = (root / item["path"]).resolve()
        if not target.is_relative_to(root):
            raise SystemExit("Invalid backend path. No files changed.")
        if digest(target) != item["before_sha256"]:
            raise SystemExit(f"Customized or unsupported file: {item['path']}. No files changed; manual integration is required.")
    # Some upstream files store CRLF in Git itself. Exact normalized file hashes
    # above already checked the content; tolerate line endings in patch context.
    apply_command = ["git", "-C", str(root), "apply", "--ignore-space-change"]
    subprocess.run([*apply_command, "--check", str(patch)], check=True)
    if not args.apply:
        print("Compatible backend files; patch check passed. Add --apply to install the backend. No files changed.")
        return
    backup = root / "image-edit-backups" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(manifest_path, backup / "manifest.json")
    for item in manifest["files"]:
        path = root / item["path"]
        if path.is_file():
            saved = backup / item["path"]
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, saved)
    subprocess.run([*apply_command, str(patch)], check=True)
    for item in manifest["files"]:
        if digest(root / item["path"]) != item["after_sha256"]:
            raise SystemExit(f"Installed hash mismatch: {item['path']}. Backup: {backup}. Do not start Forge until this is resolved.")
    print(f"Backend installed without pulling/updating Forge. Backup: {backup}. Fully restart Forge.")


if __name__ == "__main__":
    main()
