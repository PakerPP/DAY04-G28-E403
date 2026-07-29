---
name: save_note
track: core
kind: local_file_write
provider: none
requires_env: []
inputs: [items, note, filename]
outputs: [path, items_saved]
side_effect: local_file_write
---
# save_note

Appends already-collected items (and/or a free-text note) as a new dated
section to a local markdown file under `research_notes/`. Use when the user
asks to save, bookmark, or keep a note about items already collected in this
conversation — do not call this to fetch new data; combine it with results
already returned by `lookup`/`fetch`/`get_twitter`/`social_search`. Purely
local: no external API call, nothing leaves the machine, no confirmation
needed (append-only, reversible by editing the file).
