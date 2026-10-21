"""Recover original positive text from metadata, without executing Comfy graphs."""

import base64
import json
import re

from PIL import Image

from .metadata import HISTORY_KEY


def _object(value):
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    try:
        result = json.loads(value)
        return result if isinstance(result, dict) else {}
    except (ValueError, RecursionError):
        return {}


def _positive_parameters(value):
    if not isinstance(value, str):
        return ""
    # Our history sections are not part of the original generation prompt.
    value = re.split(r"(?m)^--- Image Edit.*---\s*$", value, maxsplit=1)[0]
    value = re.split(r"(?m)^\s*Negative prompt:", value, maxsplit=1)[0]
    lines = value.strip().splitlines()
    if lines and re.match(r"^\s*Steps:\s*\d+\s*,", lines[-1]):
        lines.pop()
    return "\n".join(lines).strip()


def _exif_parameters(info):
    raw = info.get("exif")
    if isinstance(raw, dict) and raw.get("encoding") == "base64":
        try:
            raw = base64.b64decode(raw.get("data", ""), validate=True)
        except ValueError:
            return ""
    if not isinstance(raw, bytes):
        return ""
    try:
        exif = Image.Exif()
        exif.load(raw)
        comment = exif.get_ifd(34665).get(37510, "")
        if isinstance(comment, bytes):
            if comment.startswith(b"UNICODE\x00"):
                data = comment[8:]
                return data.decode("utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-16-be")
            if comment.startswith(b"ASCII\x00\x00\x00"):
                comment = comment[8:]
            return comment.decode("utf-8").rstrip("\x00")
        return comment if isinstance(comment, str) else ""
    except (ValueError, TypeError, KeyError, OSError, UnicodeError):
        return ""


def comfy_positive_prompts(graph):
    """Follow positive conditioning, not unrelated/negative text or model inputs.

    Supports saved API graphs (KSampler, custom guiders, CLIP/SDXL/Flux/Qwen
    encoders and common literal string links). Unknown processing nodes are
    not evaluated. Multiple branches remain separate choices.
    """
    nodes = {str(key): node for key, node in graph.items()
             if isinstance(node, dict) and isinstance(node.get("inputs"), dict)}
    if not nodes:
        return []

    def linked(value):
        return (isinstance(value, list) and len(value) == 2 and
                isinstance(value[0], (str, int)) and isinstance(value[1], int) and str(value[0]) in nodes)

    # Prefer nodes feeding saved images; ignore disconnected prompt experiments.
    outputs = [key for key, node in nodes.items() if node.get("class_type") in ("SaveImage", "PreviewImage", "SaveImageWebsocket")]
    reachable, pending = set(), outputs or list(nodes)
    while pending:
        key = pending.pop()
        if key in reachable:
            continue
        reachable.add(key)
        pending.extend(str(value[0]) for value in nodes[key]["inputs"].values() if linked(value))

    roots = []
    for key, node in nodes.items():
        if key not in reachable:
            continue
        fields = node["inputs"]
        for name in ("positive", "positive_prompt"):
            if name in fields:
                roots.append((fields[name], key, name))
        if node.get("class_type") == "BasicGuider" and "conditioning" in fields:
            roots.append((fields["conditioning"], key, "conditioning"))
    if not roots:
        return []

    found, texts, visited = [], set(), set()
    text_fields = ("text", "prompt", "text_g", "text_l", "t5xxl", "clip_l", "clip_g")
    conditioning_fields = ("conditioning", "conditioning_1", "conditioning_2", "conditioning_to", "conditioning_from", "positive", "positive_prompt", "cond")
    pending = [(value, key, name, False) for value, key, name in roots]
    while pending:
        value, key, name, string_link = pending.pop(0)
        if isinstance(value, str) and value.strip():
            text = value.strip()
            if text not in texts:
                texts.add(text)
                found.append((f"ComfyUI positive · node {key} · {name}", text))
            continue
        if not linked(value):
            continue
        key, slot = str(value[0]), value[1]
        marker = (key, slot, string_link)
        if marker in visited:
            continue
        visited.add(marker)
        node = nodes[key]
        if node.get("class_type") == "ConditioningZeroOut":
            continue
        # Combined Qwen encoders can expose negative conditioning at output 1.
        if slot and not string_link:
            continue
        fields = node["inputs"]
        allowed = (*text_fields, "value", "string") if string_link else text_fields
        for field in allowed:
            if field in fields:
                pending.append((fields[field], key, field, True))
        if not string_link:
            for field in conditioning_fields:
                if field in fields:
                    pending.append((fields[field], key, field, False))
    return found


def original_prompts(source):
    """Return (label, text) choices. An empty result never substitutes edit text."""
    if source is None:
        return []
    info = source.info
    history = _object(info.get(HISTORY_KEY))
    if history.get("version") == 1 and isinstance(history.get("original_metadata"), dict):
        info = history["original_metadata"]
    elif "image_edit" in info or "qwen_edit" in info:
        return []
    prompt = _positive_parameters(info.get("parameters") or _exif_parameters(info))
    if prompt:
        return [("Original generation prompt", prompt)]
    graph = _object(info.get("prompt"))
    return comfy_positive_prompts(graph)
