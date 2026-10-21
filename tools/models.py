"""List/check optional weights; --download explicitly installs a pinned model set."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile


def digest(path):
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def main():
    catalog = json.loads((Path(__file__).resolve().parents[1] / "models.json").read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=catalog, required=True)
    parser.add_argument("--forge-root", type=Path, required=True)
    parser.add_argument("--download", action="store_true", help="Download only this model set; reuse matching installed files.")
    parser.add_argument("--verify", action="store_true", help="Hash already installed files (slower).")
    for name in ("checkpoint", "encoder", "vae"):
        parser.add_argument(f"--{name}-dir", type=Path, help="Override the standard Forge model directory.")
    args = parser.parse_args()
    root = args.forge_root.resolve()
    if not (root / "launch.py").is_file():
        raise SystemExit("Not a Forge root: launch.py is missing.")
    directories = dict(checkpoint=args.checkpoint_dir or root / "models/Stable-diffusion",
                       encoder=args.encoder_dir or root / "models/text_encoder", vae=args.vae_dir or root / "models/VAE")
    model = catalog[args.model]
    print("Publisher's files and weight license: " + model["model_card"])
    print("Pinned revision: " + model["revision"])
    for item in model["files"]:
        repository = item.get("repository", model["repository"])
        revision = item.get("revision", model["revision"])
        if repository != model["repository"] or revision != model["revision"]:
            print(f"Component source: https://huggingface.co/{repository}/tree/{revision}")
        target = directories[item["kind"]].resolve() / Path(item["source"]).name
        if target.exists():
            if target.stat().st_size != item["bytes"] or ((args.verify or args.download) and digest(target) != item["sha256"]):
                raise SystemExit(f"Existing file differs from the pinned weights; refusing to overwrite: {target}")
            print(f"Installed: {target}")
            continue
        print(f"Missing: {target} ({item['bytes'] / 1e9:.2f} GB)")
        if not args.download:
            continue
        from huggingface_hub import hf_hub_download
        cached = Path(hf_hub_download(repo_id=repository, filename=item["source"], revision=revision))
        if cached.stat().st_size != item["bytes"] or digest(cached) != item["sha256"]:
            raise SystemExit("Downloaded file failed size/SHA-256 verification; nothing installed.")
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".image-edit-", suffix=".partial", dir=target.parent)
        try:
            with os.fdopen(descriptor, "wb") as output, cached.open("rb") as source:
                shutil.copyfileobj(source, output, length=8 * 1024 * 1024)
            # Same-directory hard link publishes the complete file atomically and
            # refuses to overwrite a destination that appeared mid-download.
            os.link(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
        print(f"Installed and verified: {target.name}")
    if not args.download:
        print("Check only. Add --download to install missing files. No model is downloaded on Forge startup.")


if __name__ == "__main__":
    main()
