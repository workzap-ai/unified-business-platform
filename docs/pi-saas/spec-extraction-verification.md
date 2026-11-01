# Spec extraction verification

Independent-style check: every figure below comes from a **fresh pypdf read of the PDF**, not from the stored text, using seed `20261031` (`extract_specs.py --verify-samples`, results in `spec-text-v2/verification-sample.json`). It proves the text layer was captured faithfully. It does not prove that the text layer itself is right, and it cannot see anything pypdf cannot read.

## 1. Page counts

| PDF | pypdf pages | markers in .txt | baseline (coordinator) | match | pages with empty/low text | empty |
|---|---|---|---|---|---|---|
| pi-brain-v3 | 448 | 448 | 448 | yes | 0 (none) | none |
| pi-industry-solutions | 467 | 467 | 467 | yes | 4 (1, 17, 50, 77) | 50 |
| pi-platform-spec | 141 | 141 | 141 | yes | 2 (1, 141) | none |
| pi-platform-spec-1 | 189 | 189 | 189 | yes | 1 (1) | none |
| pi-platform-spec-v1.4-2026-10-27 | 224 | 224 | 224 | yes | 1 (224) | none |
| pi-platform-spec-v1.5-2026-10-28 | 238 | 238 | 238 | yes | 0 (none) | none |
| pi-platform-spec-v1.6-2026-10-30 | 253 | 253 | 253 | yes | 0 (none) | none |

`extract_specs.py --verify` also re-checks that markers run 1..N in order with the right total, that raw and normalised markers agree, that no private-use glyph remains, and that CSV/JSON/summary rule counts agree.

## 2. Rule ids re-found on their recorded page (50 per PDF, fixed seed)

A sampled id (kind `rule_id`) counts as found when its letters and digits (hyphens and spacing ignored) occur in a fresh read of its recorded page. `pi-industry-solutions` has only 24 id-and-page pairs, so all of them were checked.

| PDF | id-and-page pairs available | sampled | found | not found |
|---|---|---|---|---|
| pi-brain-v3 | 206 | 50 | 50 | 0  |
| pi-industry-solutions | 24 | 24 | 24 | 0  |
| pi-platform-spec | 305 | 50 | 50 | 0  |
| pi-platform-spec-1 | 307 | 50 | 50 | 0  |
| pi-platform-spec-v1.4-2026-10-27 | 311 | 50 | 50 | 0  |
| pi-platform-spec-v1.5-2026-10-28 | 312 | 50 | 50 | 0  |
| pi-platform-spec-v1.6-2026-10-30 | 311 | 50 | 50 | 0  |

## 3. Table-like regions (20 pages per PDF)

Pages flagged table-like (20 or more drawn rectangles, or tab/pipe/box rows) were drawn at random and compared word-for-word (whitespace-insensitive) between a fresh extraction-plus-normalisation and the stored page. This proves the stored text matches the PDF text layer; it does **not** prove the table's column structure, which pypdf flattens to reading order. Column reading was done only by eye on the quoted precedence tables in SPEC-INDEX-v2.md.

| PDF | table-like pages | sampled | identical | mismatching |
|---|---|---|---|---|
| pi-brain-v3 | 41 | 20 | 20 | 0 |
| pi-industry-solutions | 13 | 13 | 13 | 0 |
| pi-platform-spec | 102 | 20 | 20 | 0 |
| pi-platform-spec-1 | 146 | 20 | 20 | 0 |
| pi-platform-spec-v1.4-2026-10-27 | 175 | 20 | 20 | 0 |
| pi-platform-spec-v1.5-2026-10-28 | 188 | 20 | 20 | 0 |
| pi-platform-spec-v1.6-2026-10-30 | 203 | 20 | 20 | 0 |

Sampled pages:

- pi-brain-v3: 10-11, 17-20, 22, 31, 33, 35, 423, 431-433, 436-440, 442
- pi-industry-solutions: 8-9, 11-15, 18-19, 22-24, 119
- pi-platform-spec: 4-5, 7, 21, 58, 62-63, 70, 72, 83, 87-89, 91, 108-109, 115-117, 124
- pi-platform-spec-1: 14, 19, 22, 33, 35, 65, 74, 98, 116, 121, 124, 129, 131, 141, 149, 153, 160, 173, 182, 189
- pi-platform-spec-v1.4-2026-10-27: 31, 33, 53, 58, 72, 101, 106, 112, 139, 153, 157, 171, 183, 189, 202, 204, 206, 208, 211, 214
- pi-platform-spec-v1.5-2026-10-28: 37, 45, 49, 51, 68, 75, 99, 112, 126, 129, 133, 180, 194, 198-199, 203, 212, 223, 230-231
- pi-platform-spec-v1.6-2026-10-30: 12, 28, 50, 53, 67, 73, 109, 116, 118, 121, 130, 139, 166, 168, 173, 180, 198-199, 212, 247

## 4. Examples (up to 10 per PDF)

Example lines are lines that start with Example, Sample reply, Sample, Worked example, Bad:, Good: or Instead: . Each sampled line was searched for in a fresh read of its page. Examples that are not introduced by those words (for instance chat transcripts) are not sampled.

| PDF | example lines found | sampled | found on page | mismatching |
|---|---|---|---|---|
| pi-brain-v3 | 7 | 7 | 7 | 0 |
| pi-industry-solutions | 212 | 10 | 10 | 0 |
| pi-platform-spec | 6 | 6 | 6 | 0 |
| pi-platform-spec-1 | 8 | 8 | 8 | 0 |
| pi-platform-spec-v1.4-2026-10-27 | 9 | 9 | 9 | 0 |
| pi-platform-spec-v1.5-2026-10-28 | 10 | 10 | 10 | 0 |
| pi-platform-spec-v1.6-2026-10-30 | 11 | 10 | 10 | 0 |

Sampled lines:

**pi-brain-v3**

- p28: Example plain description
- p9: Example conversations are
- p427: Example promotion / retirement
- p24: Example
- p14: Example (Illustrative)
- p428: Example bank
- p443: Example file

**pi-industry-solutions**

- p176: Sample solution reply (Illustrative):
- p435: Sample solution reply (Illustrative):
- p355: Sample solution reply (Illustrative):
- p228: Sample solution reply (Illustrative):
- p115: Sample solution reply (Illustrative):
- p179: Sample solution reply (Illustrative):
- p172: Sample solution reply (Illustrative):
- p145: Sample solution reply (Illustrative):
- p287: Sample solution reply (Illustrative):
- p62: Sample solution reply (Illustrative):

**pi-platform-spec**

- p61: Example promotion / retirement Low Daily auto
- p83: Example file rule-auditor.md:
- p11: Example conversations are Illustrative, matching Workzap’s own rule that every made-up conversation
- p7: Example bank, retrieved
- p123: Sample solution reply Seeds the example bank (v3 Part 8.4.3) for that industry
- p63: Example bank Browse active examples by situation; see which ones pi uses

**pi-platform-spec-1**

- p12: Example conversations are Illustrative, matching Workzap’s own rule that every made-up conversation
- p123: Sample solution reply Seeds the example bank (v3 Part 8.4.3) for that industry
- p188: Sample replies ending “Workzap …
- p63: Example bank Browse active examples by situation; see which ones pi uses
- p7: Example bank, retrieved
- p153: Sample problem map (Illustrative). Four problems, three links, one root cluster. A dashed arrow is p
- p83: Example file rule-auditor.md:
- p61: Example promotion / retirement Low Daily auto

**pi-platform-spec-v1.4-2026-10-27**

- p92: Example file rule-auditor.md:
- p197: Sample replies ending “Workzap …
- p71: Example promotion / retirement Low Daily auto
- p162: Sample problem map (Illustrative). Four problems, three links, one root cluster. A dashed arrow is p
- p15: Example bank, retrieved
- p73: Example bank Browse active examples by situation; see which ones pi
- p132: Sample solution reply Seeds the example bank (v3 Part 8.4.3) for that industry
- p210: Example (locksmith, Illustrative). After the two free ideas, a Workzap line such as: “Workzap could 
- p19: Example conversations are Illustrative, matching Workzap’s own rule that every made-up

**pi-platform-spec-v1.5-2026-10-28**

- p15: Example bank, retrieved
- p71: Example promotion / retirement Low Daily auto
- p19: Example conversations are Illustrative, matching Workzap’s own rule that every made-up
- p211: Example (locksmith, Illustrative). After the two free ideas, a Workzap line such as: “Workzap could 
- p199: Sample replies ending “Workzap …
- p73: Example bank Browse active examples by situation; see which ones pi
- p163: Sample problem map (Illustrative). Four problems, three links, one root cluster. A dashed arrow is p
- p92: Example file rule-auditor.md:
- p132: Sample solution reply Seeds the example bank (v3 Part 8.4.3) for that industry
- p217: Example (Illustrative). To “Hello” and “My friend shared your number”:

**pi-platform-spec-v1.6-2026-10-30**

- p93: Example file rule-auditor.md:
- p133: Sample solution reply Seeds the example bank (v3 Part 8.4.3) for that industry
- p219: Example (Illustrative). To “Hello” and “My friend shared your number”:
- p200: Sample replies ending “Workzap …
- p212: Example (locksmith, Illustrative). After the two free ideas, a Workzap line such as: “Workzap could 
- p72: Example promotion / retirement Low Daily auto
- p226: Example. The owner says referrals are the only source (11:23) and “Zero” paid jobs from them in thre
- p74: Example bank Browse active examples by situation; see which ones pi
- p16: Example bank, retrieved
- p164: Sample problem map (Illustrative). Four problems, three links, one root cluster. A dashed arrow is p

## 5. Sampled rule ids (for reproducibility)

- **pi-brain-v3**: RASK01@10, RDISC01@10, RNOTE01@10, ROFFER01@10, ROFFER03@10, RPAY01@10, RPRIV01@10, RPROM01@10, RQUOTE01@10, RLANG01@11, RROUTE01@11, RPAY01@12, RPAY04@12, RPRIV02@12, RPROM01@12, RADV02@13, RBRAND01@13, REMER04@13, RPRIV08@13, RVOICE06@15, RVOICE08@15, RVOICE09@15, RLANG01@16, RVOICE14@16, RLANG03@17, RLANG05@17, RLANG08@17, RMETA01@17, RASK03@20, RCORR03@22, RCORR04@22, RFUP02@22, RDOC05@27, RQUOTE02@28, RQUOTE03@28, RQUOTE05@28, RQUOTE06@28, RDEC01@29, RKICK01@29, RKICK03@29, RDISC02@30, RPAY07@31, RLANG07@33, RSELL03@419, RLANG02@424, RASK01@431, RPAY02@431, RSELL01@431, RVOICE01@431, RPRIV05@437
- **pi-industry-solutions**: RVAL01@9, RVAL02@9, RVAL03@9, RVAL04@9, RVAL05@9, RVAL06@9, RVAL02@10, RVAL07@10, RSOL01@11, RVAL01@11, RVAL07@11, RBUILD01@12, RBUILD02@12, RBUILD03@12, RBUILD04@12, RBUILD05@12, RBUILD06@12, RVAL06@12, RBUILD01@14, RVAL01@15, RBUILD01@16, RVAL01@16, RVAL01@22, RVAL07@22
- **pi-platform-spec**: RLANG09@5, RSELL01@5, RDISC01@11, RNOTE03@12, RLANG01@13, RMETA01@13, RQUOTE01@13, RPAY03@15, RSELL02@15, RSELL05@15, RADV05@16, RPAY05@16, REMER03@17, REMER04@17, RVOICE07@20, RVOICE11@20, RASK06@27, RMEM02@27, ROFFER03@28, RDOC04@37, RDOC06@37, RDOC07@37, RDISC03@40, RKICK01@40, RCOMPL01@45, RROUTE01@45, ROFFER06@51, RSELL03@52, REMER04@53, RLANG02@58, RDISC03@67, RPRIV05@75, RDISC01@83, RANS01@92, RASK07@92, RECHO01@92, RLANG09@92, RSOL02@92, RSELL01@95, RANS03@96, RSOL01@96, RSOL04@96, RLANG09@108, RANS03@109, RVAL04@117, RVAL07@117, RBUILD03@119, RBUILD01@122, RANS03@132, RSOL01@133
- **pi-platform-spec-1**: RDISC01@11, RCONV01@12, ROFFER01@13, RPRIV01@13, RILLU01@14, RLANG01@14, RHONEST01@15, RADV03@16, RPAY02@16, RPRIV03@16, REMER02@17, RDISC01@19, RVOICE04@20, RVOICE08@20, RLANG05@23, RLANG08@23, RASK03@27, ROFFER04@28, ROFFER05@28, RMEM02@30, RMEM04@30, RMEM05@30, RADV01@33, RDOC07@37, RDOC09@37, RQUOTE04@38, RQUOTE08@38, RDEC03@39, RDEC05@40, RPAY03@41, RPRIV02@43, RDOC02@52, RLANG02@58, RHONEST01@67, RSELL01@67, RDISC01@68, ROFFER05@73, RPRIV05@75, RSOL02@92, RSOL02@96, RSOL07@96, RECHO02@108, RTONE02@108, RTONE03@108, RSELL01@114, RVAL04@117, RVAL01@122, RANS01@132, ROFFER01@132, RSELL04@188
- **pi-platform-spec-v1.4-2026-10-27**: RDISC01@19, RCONV01@20, RNOTE03@20, ROFFER03@20, RSELL01@20, RADV01@21, RCANT01@21, RDEC04@21, RILLU01@21, RDISC01@22, RDISC02@22, RSELL01@23, RSELL04@23, RMETA01@25, RVOICE09@28, RVOICE12@28, RVOICE14@28, RLANG07@31, RASK02@35, RMEM02@35, RCORR01@38, RFUP03@38, RSELL01@43, RDOC04@46, RQUOTE02@47, RQUOTE04@47, RQUOTE06@47, RDEC05@49, RPAY03@51, RCOMPL03@54, RROUTE01@54, REMER04@63, RLANG02@67, RASK01@77, RDEC01@77, RPAY05@77, RSELL04@100, RSELL02@105, RSELL03@105, RSOL04@110, RSOL08@110, RTONE01@117, REMER04@122, RVAL01@128, RBUILD02@129, RBUILD01@133, RVAL07@137, RGEN01@141, RVAL06@141, RANS01@142
- **pi-platform-spec-v1.5-2026-10-28**: RLANG09@5, RNOTE03@20, RDISC01@23, RDISC05@23, RHONEST01@23, RPROM01@23, RSELL05@23, RPRIV08@24, REMER03@25, RDISC01@27, RLANG02@31, ROFFER06@37, RCORR02@38, RMEM04@38, RADV01@42, RDOC03@46, RPROM01@46, RVOICE03@46, RQUOTE01@47, RDEC05@49, RDISC02@49, RDISC03@49, RKICK01@49, RHONEST01@50, RPAY07@51, RCOMPL03@54, RDISC04@54, RASK05@68, RBRAND01@77, RDISC01@77, RLANG01@77, RPRIV05@84, RDISC01@101, RSOL02@101, RASK01@104, RSELL01@105, RSOL10@105, RANS03@110, RSOL04@110, RECHO03@117, RASK07@123, RVAL02@126, RVAL01@128, RBUILD01@133, ROFFER01@141, ROFFER03@141, RSOL01@141, RMEM02@142, RSOL01@142, RSELL02@199
- **pi-platform-spec-v1.6-2026-10-30**: RCORR01@22, RKICK01@22, RNOTE03@22, RQUOTE01@22, RSELL01@22, RLANG01@23, RPROM02@24, RSELL02@24, RPAY02@25, REMER01@26, RDISC02@28, RVOICE03@29, RVOICE10@29, RLANG01@30, RCORR04@39, RFUP05@39, RMEM03@39, RMEM04@39, RMEM05@39, RADV01@43, RSELL01@44, RDOC05@47, RPROM01@47, RVOICE03@47, RQUOTE02@48, RQUOTE06@48, RQUOTE08@48, RQUOTE09@48, RDISC03@50, RKICK03@50, RHONEST01@51, RPAY04@52, RVOICE09@78, RSELL01@101, RECHO01@102, RSELL01@103, RSELL04@106, RSELL05@106, RSOL07@106, ROFFER03@107, RSOL04@111, RSOL08@111, RASK07@118, RVAL01@129, RBUILD03@130, RBUILD04@130, RVAL06@130, RVAL01@134, RANS01@142, RSELL04@200

## 6. What could NOT be verified

- **Diagrams, drawn boxes, arrows, images, colour, layout.** pypdf has no access to them. Pages with box characters (a diagram drawn as text) are listed in SPEC-INDEX-v2.md section 6; other vector drawings leave no trace at all.
- **Table column structure.** Cells are in reading order; the mapping of cells to columns was not machine-checked.
- **Arabic / Urdu script.** Presentation-form letters are normalised to base letters but the order and some marks are lost (glyphs with no Unicode value are shown as U+FFFD). The Urdu example text on the pages listed as Arabic-script must be read in the PDF.
- **Private-use glyph mapping.** Proved by reading the rendered glyph outlines and by context in many places, and checked to be identical across the six PDFs that contain them; it was not compared glyph-by-glyph against a full render of every page.
- **Completeness of the rule index.** The patterns find every token of the shapes listed; a rule written in a shape not listed (or an id split across lines) would be missed. The sample check shows the index has no false ids in the sample; it cannot show there are no missing ones. Counting `R-WORD-NN` across versions (the five platform specs agree to within a few ids) is a consistency signal, not a proof.
- **Brain v3 and Industry Solutions word spacing.** A few words are split by a stray space inside the PDF text layer; searches should tolerate that.
- **Scanned pages / OCR.** No page has an image, so OCR was not needed; `pi-industry-solutions` page 50 is a genuinely blank page (no content stream).
