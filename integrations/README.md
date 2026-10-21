# Optional Infinite Image Browsing integration

`window.imageEditLoadImage(url, filename)` transfers original image bytes into
Image Edit and imports its latest edit recipe when present. The legacy
`qwenEditLoadImage` alias is retained. Only same-origin image URLs are accepted.
Ordinary images keep the current generation settings; sending never generates.
Original metadata remains available to the Keep original metadata option.

The included `iib-menu.patch` adds **Send to Image Edit** to thumbnail and
full-screen menus in the sd-forge_neo-infinite-image-browsing-xl source tree.
It is optional: without it, users can upload the image and use the PNG importer.
It is not silently installed or applied to another extension.

Maintainers: run `git apply --check /path/to/iib-menu.patch` in the image-browser
repository before applying it. Other revisions may require adapting the small
menu/handler changes. Rebuild that browser with its documented frontend build
command and regenerate its javascript/index.js wrapper. Do not distribute this
user's complete customized IIB tree or replace somebody else's built bundle.

The internal menu key remains `send2qwenedit` for compatibility; all visible
labels/errors say **Image Edit**. Image Edit recipes use `image_edit`; legacy
`qwen_edit` recipes are also supported. Missing weights are reported rather than
silently substituting another checkpoint. Painted masks must be repainted.
