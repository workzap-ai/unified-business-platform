# Specification index (text extracted from the seven PDFs, 2026-10-30)

The PDFs are the version of record and stay outside git (about 36 MB). This index pins each one by SHA-256, and
`docs/pi-saas/spec-text/<name>.txt` holds its extracted text (one `=== page N ===` marker per page) so rules can be
searched and diffed. Extracted with `pypdf`; page numbers below are PDF page numbers (the same as the `page N of M`
footer). A few stray NUL bytes in the PDF text layer were removed (the counts are in the table); nothing else was edited.

| Name | PDF file | SHA-256 | Bytes | Pages | Text file | Extraction |
|---|---|---|---|---|---|---|
| pi-brain-v3 | `docs/pi-brain-v3.pdf` | `b2948ddcac218e248e6d1d7ab0b584314c047c63db9cf59ea466ba76e73f247d` | 3,688,280 | 448 | `pi-brain-v3.txt` | all pages have text |
| pi-industry-solutions | `docs/pi-industry-solutions.pdf` | `7afa45e08120fe999bf79f3d2e7b2f31346547b02073717fd89ce3ba77d3c53b` | 13,718,035 | 467 | `pi-industry-solutions.txt` | **page 50 has no extractable text** (image or blank); 225 NUL bytes removed |
| pi-platform-spec | `docs/pi-platform-spec.pdf` | `cc4a5c6fbeb01b5cc30ee7e459704d82b3f1734a136cbdae5cc995bef89cb63e` | 3,889,974 | 141 | `pi-platform-spec.txt` | all pages have text; 557 NUL bytes removed |
| pi-platform-spec-1 | `docs/pi-platform-spec-1.pdf` | `df6a5d81b23ee8af83292526d361e14d40c25891370bd4bfce39858612db904a` | 5,029,461 | 189 | `pi-platform-spec-1.txt` | all pages have text; 557 NUL bytes removed |
| pi-platform-spec-v1.4 (27 Oct 2026) | `docs/pi-platform-spec-v1.4-2026-10-27.pdf` | `1a915b1debd3fd211c57ee8dd7547ac6508ea686a0b22bcacd35e11a46d520a4` | 2,578,458 | 224 | `pi-platform-spec-v1.4-2026-10-27.txt` | all pages have text; 558 NUL bytes removed |
| pi-platform-spec-v1.5 (28 Oct 2026) | `docs/pi-platform-spec-v1.5-2026-10-28 (1).pdf` | `0e998fe555ecb48a088a932f75d6fe400eceed70e193d385899e45fba1baf34b` | 2,693,141 | 238 | `pi-platform-spec-v1.5-2026-10-28.txt` | all pages have text; 558 NUL bytes removed |
| pi-platform-spec-v1.6 (30 Oct 2026) | `docs/pi-platform-spec-v1.6-2026-10-30.pdf` | `3c8953f50001eda8c035b17c2b3d75b0a54fc31af3cd852577e61a8baf61cff0` | 2,823,987 | 253 | `pi-platform-spec-v1.6-2026-10-30.txt` | all pages have text; 558 NUL bytes removed |

No PDF is scanned. Only `pi-industry-solutions` page 50 needs a human look. The extracted text keeps PDF line breaks and some
odd glyphs (for example `ˮ` for a closing quote), so search for words, not punctuation. This extraction has not been proofread.

## Precedence (what wins when the specs disagree)

- **The spec's own table decides, topic by topic.** v1.6 page 14, "Which rule wins when books disagree" (the same table is
  on v1.5 page 12, v1.4 page 12 and platform-spec-1 page 5; v1.6 is the newest and adds rows). It says the books were
  written one after another, so some older lines are superseded, and Part A.5 requires superseded lines to be removed
  from the live pi, not left beside the newer one.
- **Rows on v1.6 page 14 (summary, not a quote):** solutions when asked (Book 2 RANS/RSOL over Brain v3 RSELL01);
  ideas per message (Book 3 RVAL: exactly 2 per message and per problem, 4 per conversation before the offer, 2 more
  after a declined offer, over the Addendum 1 samples); how a build is described (Book 3 section 1.9 RBUILD); the ending
  of a reply (Book 3 RVAL06 amended); the offer (Book 4 prompt 5.2, then Book 5 5.4 and 10.9: one Solution Box for the whole
  set, only under R1 to R3 or B1 to B7); language change (Book 4 prompt 5.3 / RLANG09: not a new session); where industry
  ideas come from (Book 3 Part 2, all 211 industries); stages of opening up (Book 5 Part 2: four live dials, over Addendum 3 v1);
  "Book 5 decision 5": 2 per problem, up to 8 per business.
- **General order when no row covers a topic (my reading, not a spec statement):** the later file and the later book win:
  v1.6 over v1.5 over v1.4 over platform-spec over platform-spec-1 over pi-industry-solutions over pi-brain-v3. In the
  repository the instruction in `CLAUDE.md` is: the specification wins over the code; ask before deviating.
- **Cumulative files:** all five platform-spec files share the same Part A, Book 1 and Books 2 to 5 structure and grow
  with each version (141, 189, 224, 238, 253 pages). I did not diff them page by page.

## Where to find things

### pi-platform-spec-v1.6 (253 pages, the newest)
| Section | Pages |
|---|---|
| Contents | 2 to 4 |
| Part A Audit of the existing pi (A.1 to A.8, conflict register, audit report) | 15 to 19 |
| Book 1 The Brain (Parts 0 to 11, Appendices A to D) | 20 to 100 |
| Part 0 What pi is | 21; Part 1 Constitution (L0, immutable) 24; Part 2 Personality and voice 26; Part 3 Conversation engine 34 |
| Part 4 Problem model and taxonomy | 40; Part 5 From sorted problems to a solution 46; Part 6 Safety, privacy, edge cases 50 |
| Part 7 Industry playbooks 57; Part 8 Self-learning brain 65; Part 9 Implementation plan (tools 77, tables 79, milestones 80) 76 |
| Part 10 Golden conversations, red-team, rubric | 81; Part 11 Claude Code playbook 87; Appendices A prompt 98, B rule index 99, C glossary 99, D open decisions 100 |
| Book 2 Solution Mode | 101 to 125 |
| Book 3 Value line, build phrasing, learning of solutions | 126 to 140 |
| Book 4 Live Audit 2 and the fix prompts | 141 to 150 |
| Book 5 The Engagement Engine (dials, thinking moves, map, Solution Box; Parts 16 opening, 17 owner turns and open items, 18 rules checked in code, 19 buying signals, direct questions, what counts as a problem; Part 19 is new in v1.6, contents list on page 10) | 151 to 227 |
| Book 6 Live Audit 4 | 228 to 236 |
| Book 7 Live Audit 5 | 237 to 243 |
| Book 8 Live Audit 6 (the 30 October chat) | 244 to 253 |

### pi-platform-spec-v1.5 / v1.4 / platform-spec-1 / platform-spec
Same shape without the later books. Contents on page 2; the precedence table at v1.5 p12, v1.4 p12, platform-spec-1 p5.
v1.5 has Book 5 from page 150 (with Parts 16 to 18, the rules checked in code) and Books 6 and 7 (Live Audit 5, the 28 October chat, is
Book 7); v1.6 adds Part 19 and Book 8. Page numbers for v1.4, platform-spec-1 and platform-spec were not mapped further.

### pi-brain-v3 (448 pages)
The Brain book that Book 1 of the platform spec reproduces and extends (constitution, voice, state machine, problem model, safety,
industry packs with per-trade ideas, self-learning, implementation plan, golden and red-team tests, rule index). Deletion
and learning rules are on pages 427 to 445 (see `spec-retention-findings.md`); trade playbooks run from about page 38 to 420.

### pi-industry-solutions (467 pages)
The 211 industry solution entries ("Workzap would build ..." and "Where the free part stops"), grouped by sector. Rules for owner ideas
(redacted and generalised) are on page 22. Page 50 has no text layer.

## Limits of this index
- Page numbers for Books and Parts in v1.6 come from a text scan of line starts, not from a visual check of the PDF.
- The cumulative-structure statement is inferred from page counts and shared headings, not from a diff.
- Nothing here changes any rule. If code and spec disagree, the spec wins and the owner is asked.
