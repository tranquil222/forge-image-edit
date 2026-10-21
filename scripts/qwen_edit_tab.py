import importlib
import sys

# Forge's Reload UI reloads scripts, but not imported extension packages.
for name in ("forge_qwen_edit", "forge_qwen_edit.workflow", "forge_qwen_edit.adapters", "forge_qwen_edit.selection", "forge_qwen_edit.metadata", "forge_qwen_edit.masking", "forge_qwen_edit.canvas", "forge_qwen_edit.native", "forge_qwen_edit.model_bar", "forge_qwen_edit.ui"):
    if name in sys.modules:
        importlib.reload(sys.modules[name])

from forge_qwen_edit.ui import register

register()
