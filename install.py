"""Forge's URL installer: verified backend patches only, no model/dependency downloads."""
from pathlib import Path
import os
import subprocess
import sys


def main():
    extension = Path(__file__).resolve().parent
    # Forge runs extension installers with PYTHONPATH pointing at its root.
    candidates = [Path.cwd(), extension.parent.parent]
    candidates.extend(Path(p) for p in os.environ.get('PYTHONPATH', '').split(os.pathsep) if p)
    root = next((p.resolve() for p in candidates if (p/'launch.py').is_file() and (p/'modules').is_dir()), None)
    if root is None:
        print('Image Edit: Forge root was not found. Run tools/backend_support.py --forge-root <Forge directory> to check setup.')
        return
    if os.environ.get('FORGE_IMAGE_EDIT_SKIP_BACKEND') == '1':
        print('Image Edit: automatic backend setup disabled by FORGE_IMAGE_EDIT_SKIP_BACKEND=1.')
        return
    command = [sys.executable, str(extension/'tools/backend_support.py'), '--forge-root', str(root)]
    checked = subprocess.run(command, capture_output=True, text=True)
    if checked.stdout:
        print(checked.stdout.strip(), flush=True)
    if checked.returncode:
        if checked.stderr:
            print(checked.stderr.strip())
        print('Image Edit: backend setup required. The tab can be installed, but generation stays disabled until setup is compatible. No backend files changed. See COMPATIBILITY.md.')
        return
    result = subprocess.run([*command, '--apply'])
    if result.returncode:
        print('Image Edit: backend setup was not completed. Read COMPATIBILITY.md. Unsupported/customized files were not overwritten.')
        raise SystemExit(result.returncode)
    print('Image Edit: fully close and relaunch Forge after installation. Model weights are separate; see MODELS.md.')


if __name__ == '__main__':
    main()
