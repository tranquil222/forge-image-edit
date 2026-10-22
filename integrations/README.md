# Source imports: txt2img and Infinite Image Browser

Image Edit supplies two buttons beside Crop / outpaint. Select a result in
txt2img, or open an image in IIB's lightbox, then switch to Image Edit and click
the corresponding import button. The txt2img action follows the selected
orange-bordered thumbnail, not the batch's first image. The IIB action reads
the currently open lightbox even though its host tab is now hidden. It does not
fall back to an old selection after the lightbox is closed.

The IIB button is hidden when IIB is absent. Nothing is injected into IIB's menus,
and no IIB files, settings or private component state are modified. Existing
custom Send to Image Edit actions still work through the retained handoff API.

`window.imageEditLoadImage(url, filename)` transfers original image bytes into
Image Edit and imports its latest edit recipe when present. The legacy
`qwenEditLoadImage` alias is retained. Only same-origin image URLs are accepted.
Ordinary images keep the current generation settings; sending never generates.
Original metadata remains available to Get prompt from metadata and Keep original
metadata. Imports do not scrape the displayed prompt or resize the image.

`javascript/image_edit_iib.js` reads the same-origin lightbox image URL at the
moment of import. Preview URLs are converted to IIB's original-file endpoint,
preserving metadata and size. Reading afresh also handles an iframe reload.
`javascript/image_edit_imports.js` handles both import actions and feedback. It
reads txt2img's own gallery, rather than Forge's visible-tab-only selection helper.
No version gates, translated-label matching or hashed bundle filenames are used.
Closed/empty selections and transfer failures produce an actionable, temporary
message. Successful imports briefly show Imported ✓ in the existing button;
feedback does not add vertical space. Question-mark help explains both flows.

The old `iib-menu.patch` is retained as a legacy integration reference. It is not
needed or applied by the extension. Do not replace another extension's files or
distribute a user's customized IIB tree.

Existing `send2qwenedit` actions remain supported; visible labels/errors say
**Image Edit**. Image Edit recipes use `image_edit`; legacy
`qwen_edit` recipes are also supported. Missing weights are reported rather than
silently substituting another checkpoint. Painted masks must be repainted.
