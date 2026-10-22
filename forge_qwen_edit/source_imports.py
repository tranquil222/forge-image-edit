"""Find saved source images without depending on an in-memory Forge gallery."""
import os
import json
import random
import time
from bisect import bisect_left
from collections import OrderedDict
from pathlib import Path
from threading import RLock

from PIL import Image


_catalogs = OrderedDict()
_catalog_lock = RLock()
_catalog_seconds = 30
_catalog_limit = 4


def _scan_images(root):
    """Reuse directory-entry metadata instead of stat-ing every Windows file twice."""
    extensions = {extension.lower() for extension in Image.registered_extensions()}
    candidates, pending = [], [(root, '')]
    while pending:
        directory, prefix = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    try:
                        name = prefix + entry.name
                        if entry.is_dir(follow_symlinks=False):
                            if not getattr(entry, 'is_junction', lambda: False)():
                                pending.append((entry.path, name + '/'))
                        elif os.path.splitext(entry.name)[1].lower() in extensions and entry.is_file(follow_symlinks=False):
                            stat = entry.stat(follow_symlinks=False)
                            if stat.st_size:
                                candidates.append((stat.st_mtime_ns, name, stat.st_size))
                    except OSError:
                        continue  # A file may have moved since the directory scan.
        except OSError:
            continue
    return tuple(sorted(candidates))


def image_candidates(folder, refresh=False):
    root = Path(folder).resolve()
    if not root.is_dir():
        raise ValueError("No saved images found in the txt2img output folder yet.")
    with _catalog_lock:
        cached = _catalogs.get(root)
        if refresh or cached is None or time.monotonic() - cached[0] >= _catalog_seconds:
            candidates = _scan_images(root)
            _catalogs[root] = (time.monotonic(), candidates)
        else:
            candidates = cached[1]
        _catalogs.move_to_end(root)
        while len(_catalogs) > _catalog_limit:
            _catalogs.popitem(last=False)
        return root, candidates


def readable_image(root, candidate):
    modified, name, size = candidate
    filename = root / name
    try:
        with Image.open(filename) as image:
            image.verify()
        stat = filename.stat()
        return (stat.st_mtime_ns, stat.st_size) == (modified, size)
    except (OSError, ValueError, SyntaxError):
        return False


def recent_image(folder, before=""):
    """Page backward by modification time/name; cursor paths are never opened."""
    root = Path(folder).resolve()
    boundary = None
    if before:
        try:
            cursor = json.loads(before)
            if cursor["folder"] == str(root):
                if not isinstance(cursor["name"], str):
                    raise ValueError()
                boundary = (int(cursor["modified"]), cursor["name"])
        except (ValueError, TypeError, KeyError):
            raise ValueError("Saved-image history could not be read. Refresh the page to start again.") from None
    # Starting a sequence always sees the latest saves; subsequent presses reuse
    # the sorted catalog. Its bounded lifetime also refreshes Random imports.
    root, candidates = image_candidates(root, refresh=boundary is None)
    end = len(candidates) if boundary is None else bisect_left(candidates, boundary)
    for index in range(end - 1, -1, -1):
        candidate = candidates[index]
        modified, name, _ = candidate
        filename = root / name
        if readable_image(root, candidate):
            cursor = json.dumps(dict(folder=str(root), modified=str(modified), name=name))
            return filename, cursor
    if boundary is not None:
        raise ValueError("No older saved images in the txt2img output folder.")
    raise ValueError("No readable saved images found in the txt2img output folder yet.")


def random_image(folder):
    root, candidates = image_candidates(folder)
    candidates = list(candidates)  # Never shuffle the shared sorted catalog.
    random.shuffle(candidates)
    for candidate in candidates:
        if readable_image(root, candidate):
            return root / candidate[1]
    raise ValueError("No readable saved images found in the txt2img output folder yet.")
