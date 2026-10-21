---
name: udb-tidy
description: Brings an old note up to citations v3, one file at a time: one passage per paragraph, Claude's own words in labelled boxes, every source of the class used. Use it when verify reports many-citations, trivial-quote or source-not-used on a note written before v3.
---

# /udb-tidy <file>

One note per run. Show the student the diff before saving.

1. `udb verify --fix --path <file>`: removes repeated anchors and re-anchors quotes
   that drifted after re-extraction. Mechanical; the text does not change.
2. `udb verify --path <file>` and work through the findings, errors first:
   - `many-citations` or several short anchors in one paragraph: `vault_search` the
     idea, then one `vault_quote` (it returns 1-3 whole sentences) that backs the
     whole paragraph. Replace the old anchors with that one.
   - `trivial-quote`: quote the passage the paragraph explains, not a few words.
     A literal definition shown in quotes may stay short (`exact=True`).
   - `weak-support`: the passage is probably the wrong one; search again.
   - Sentences that are Claude's own (no source behind them): move them into
     `> [!model]` (explanation, with a `MODEL` anchor: `reason` and `basis`),
     `> [!example]` or `> [!analogy]`. Keep `[!model]` under 30% of the words.
   - `figure-description-quoted`: describe the drawing in a `[!model]` box instead.
3. Coverage: for `source-not-used` read that source with `vault_search` and add what
   it teaches; for `pages-not-covered` cover those slides or say in one line why
   they add nothing (a title slide, a repeated slide).
4. Do not change what the note says when the source does not change it. Rules 3
   and 4 of CLAUDE.md still apply: plain Spanish, one diagram.
5. Finish with `udb verify --path <file>` (no errors) and, when the agent extra is
   installed, `udb verify --deep --path <file>`. A `deep-partial` or
   `deep-unsupported` warning means a claim goes beyond its passage: fix the
   paragraph or move the claim into a `[!model]` box.
