"""Integration check for disposable Forge checkouts AFTER applying our patch."""
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from backend_support import digest

extension = Path(__file__).resolve().parents[1]
root = Path(sys.argv[1]).resolve()
manifest = next(json.loads(path.read_text()) for path in (extension / "backend-support").glob("manifest*.json")
                if all(digest(root / item["path"]) == item["after_sha256"]
                       for item in json.loads(path.read_text())["files"]))
command = [sys.executable, str(extension / "tools/backend_support.py"), "--forge-root", str(root)]
repair_paths = {"backend/args.py", "modules_forge/presets.py"}
tracked_paths = {item['path'] for item in manifest['files'] if item['before_sha256'] is not None}
originals = {name: (root / name).read_bytes() for name in tracked_paths}

def run(*extra, succeeds=True):
    result = subprocess.run([*command, *extra], text=True, capture_output=True)
    assert (result.returncode == 0) == succeeds, result.stdout + result.stderr
    return result.stdout + result.stderr

def state():
    return {item["path"]: digest(root / item["path"]) for item in manifest["files"]}

try:
    for name in repair_paths:
        # Reproduce an update restoring upstream registration files but leaving
        # the added native model files and the rest of the patch installed.
        (root / name).write_bytes(subprocess.check_output(["git", "-C", str(root), "show", f"HEAD:{name}"]))
    partial = state()
    assert "Verified partial backend installation" in run()
    assert state() == partial, "Check-only changed files"
    assert "Backend repaired" in run("--apply")
    assert all(digest(root / item["path"]) == item["after_sha256"] for item in manifest["files"])
    backups = sorted((root / "image-edit-backups").iterdir())
    saved = json.loads((backups[-1] / "manifest.json").read_text())
    assert {item["path"] for item in saved["files"]} == repair_paths
    assert "No files changed" in run("--apply")
    assert sorted((root / "image-edit-backups").iterdir()) == backups
    # Also cover an update restoring ALL upstream-tracked files while keeping
    # our added model modules: this is not a clean installation either.
    for name in tracked_paths:
        (root / name).write_bytes(subprocess.check_output(["git", "-C", str(root), "show", f"HEAD:{name}"]))
    assert "Verified partial backend installation" in run()
    assert "Backend repaired" in run("--apply")
    assert all(digest(root / item["path"]) == item["after_sha256"] for item in manifest["files"])
    # A customized registration file must never be force-repaired.
    target = root / "backend/args.py"
    target.write_bytes(originals["backend/args.py"] + b"\n# user customization\n")
    before = state()
    assert "No files changed" in run("--apply")
    assert state() == before
    # A complete customized backend is retained; missing registration plus
    # customization is rejected and must leave every file untouched.
    target.write_text("# incomplete personal registration\n", encoding="utf-8")
    before = state()
    assert "No files changed" in run("--apply", succeeds=False)
    assert state() == before
    print("PASS verified partial repair, exact final hashes, scoped backup, idempotency and custom-file protection")
finally:
    for name, data in originals.items():
        (root / name).write_bytes(data)
