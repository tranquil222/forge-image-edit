# Source imports: txt2img and Infinite Image Browser

Image Edit supplies three compact buttons beside Crop / outpaint:

- **Import from txt2img** imports the selected orange-bordered thumbnail first,
  not the batch's first image. Further presses import saved images newest to
  oldest. An empty gallery starts with the newest saved image. A new gallery
  selection or folder resets the sequence; reaching the end keeps the current source.
- **Import from Infinite Image Browser** reads only the currently open lightbox,
  even though its host tab is now hidden. Repeated clicks import that same image;
  closing the lightbox does not fall back to an old selection.
- **Import random** chooses a saved txt2img image without advancing history.

Saved imports include subfolders and use file modification time for newest-first
ordering. **Advanced**, below PNG settings import, accepts a txt2img import-folder
override. Blank uses Forge's configured output directory. The override does not
change Forge's save location, selected gallery imports or IIB.
Folder indexes are cached for up to 30 seconds for fast repeated/random imports;
starting a new history sequence always refreshes the index. Each chosen file is
checked before transfer, so deleted or unreadable images are skipped.

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
`javascript/image_edit_imports.js` handles the import actions and feedback. It
reads txt2img's own gallery, rather than Forge's visible-tab-only selection helper.
No version gates, translated-label matching or hashed bundle filenames are used.
Closed IIB lightboxes, empty saved folders and transfer failures produce a temporary
message. Successful imports briefly show Imported ✓ in the existing button;
feedback does not add vertical space. One question-mark tooltip explains crop
and all three import actions.

The old `iib-menu.patch` is retained as a legacy integration reference. It is not
needed or applied by the extension. Do not replace another extension's files or
distribute a user's customized IIB tree.

Existing `send2qwenedit` actions remain supported; visible labels/errors say
**Image Edit**. Image Edit recipes use `image_edit`; legacy
`qwen_edit` recipes are also supported. Missing weights are reported rather than
silently substituting another checkpoint. Painted masks must be repainted.
