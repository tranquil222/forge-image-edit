"""Qwen-scoped adapter for Forge's existing inpainting canvas and image transport."""

import json
import uuid
import base64
from io import BytesIO

import gradio as gr
from gradio.context import Context
from PIL import Image, ImageOps
from PIL.PngImagePlugin import PngInfo

from modules.shared import opts
from modules_forge.forge_canvas.canvas import LogicalImage, canvas_html


class MetadataImage(LogicalImage):
    """Keep source metadata even on Forge versions with a lossy canvas bridge."""
    def preprocess(self, payload):
        if not isinstance(payload, str) or not payload.startswith("data:image/") or ";base64," not in payload:
            return None
        with Image.open(BytesIO(base64.b64decode(payload.split(",", 1)[1]))) as image:
            return ImageOps.exif_transpose(image).convert("RGBA")

    def postprocess(self, value):
        if value is None:
            return None
        buffer = BytesIO()
        pnginfo = PngInfo()
        for key, data in value.info.items():
            if isinstance(key, str) and isinstance(data, str):
                pnginfo.add_text(key, data)
        binary = {key: value.info[key] for key in ("exif", "icc_profile", "dpi") if key in value.info}
        value.save(buffer, format="PNG", pnginfo=pnginfo, **binary)
        return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


class EditCanvas:
    def __init__(self):
        canvas_id = "qwen_" + uuid.uuid4().hex
        # Reuse the installed canvas/toolbar; the selection brush is tab-scoped.
        markup = canvas_html.replace("forge_mixin", canvas_id)
        if opts.forge_canvas_plain:
            markup = markup.replace('class="forge-image-container"', f'class="forge-image-container plain" style="background-color: {opts.forge_canvas_plain_color}"').replace('stroke="white"', "stroke=#444")
        if opts.forge_canvas_toolbar_always:
            markup = markup.replace('class="forge-toolbar"', 'class="forge-toolbar-static"')
        self.block = gr.HTML(markup, elem_id="qwen_edit_source")
        self.background = MetadataImage(visible=False, numpy=False, elem_id=canvas_id, elem_classes=["logical_image_background"])
        self.foreground = LogicalImage(visible=False, numpy=False, elem_id=canvas_id, elem_classes=["logical_image_foreground"])
        consistent = json.dumps(bool(opts.forge_canvas_consistent_brush))
        Context.root_block.load(None, js=f"() => qwenEditInitCanvas('{canvas_id}', {consistent})")
