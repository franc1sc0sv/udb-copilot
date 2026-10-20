---
name: udb-drive
description: Uploads, replaces, downloads or trashes files in Google Drive, streamed from disk with an MD5 check. Use it to share deliverables.
---

# /udb-drive

`udb drive upload <folder-id> <file>... [--as-doc]`, `udb drive replace <file-id> <file>`,
`udb drive download <dest> <file-id>...`, `udb drive trash <file-id>...`.
Never pass file content through the chat as base64: it gets corrupted silently.
