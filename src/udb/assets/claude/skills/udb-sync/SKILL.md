---
name: udb-sync
description: Downloads new Moodle material and indexes it. Use it at the start of the week or when a teacher uploads files.
---

# /udb-sync

1. No token yet: the student runs `udb moodle login` locally (it asks for the password and
   stores only a token). Cloud sessions read the token from an environment variable.
2. `udb moodle courses` shows course ids for `config/subjects.yaml`.
3. `udb sync <SUBJECT>`. Then assign new sources to classes (`class` in the registry) if needed.
Never read or print the token.
