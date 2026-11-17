# pi meeting documents: a designed PDF and PowerPoint after the meeting

Part of PMB (`pi-meeting-brain.md`). Branch `pi/meeting-deliverables`. Migration `0071_pi_meeting_documents`.
Status: built and tested locally; not merged, not deployed.

## What it does

After a meeting a person approves findings on the Review tab. Then, on the same tab, **Documents** can make:

1. **Summary PDF** (A4): title, date, who was there, summary, then sections: what is going wrong, what is needed,
   decisions and commitments, actions and next steps (owner and deadline only when stated in the meeting),
   open questions and risks. Lines pi only inferred say so ("pi's reading").
2. **Deck (PowerPoint)**: title slide, summary, one slide per section (long ones continue), an actions table.
   Real, editable PowerPoint text, 16:9.

A new document is a **draft**. A person with `pi.meetings.approve` approves it; a draft can be deleted, an approved
one cannot (it goes when the meeting or customer is erased). Asking again for identical approved content returns the
same draft instead of a new one. At most 20 documents per meeting.

## Rules in code (`pi_meetings/deliverables/content.py`)

- Built ONLY from insights with `review_status` approved or edited. Pending and rejected are never read, and the
  raw transcript is not used.
- Every line is redacted again (`memory_ledger.redacted`: phone, card, ID, e-mail). A line with a price
  (`insight_rules.PRICE`) is left out and counted ("lines left out"): pi does not price, the quote does.
- Owner and deadline appear only for `basis == 'stated'` insights.
- Branding is Workzap only. The PDF footer says it was prepared by pi, an AI assistant, from what the team approved.
- A draw that would leave Urdu text out (font or shaping package missing) is refused (503
  `MEETING_DOCUMENT_FONT_MISSING`), never delivered with a gap.
- Audit entries (`pi.meeting_document_created`, `_approved`, `_deleted`) carry ids, kind and counts, never words.

## Urdu

The PDF uses ReportLab (pure Python). Urdu, Arabic and Persian lines are shaped with `arabic_reshaper`, put in visual
order with `python-bidi`, split into runs by script and drawn with the Noto Naskh font already bundled in
`app/modules/pi/fonts/` (the same one the problem-map picture uses). Latin text uses Helvetica. In the deck, Urdu
paragraphs are set right-to-left with a complex-script font and PowerPoint shapes the letters. No system library and
no Dockerfile change are needed (an earlier idea, WeasyPrint, was dropped for that reason).

## Code

`pi_meetings/deliverables/{content,pdf_report,deck}.py` · `deliverable_routes.py`
(`POST/GET /pi/meeting-intel/{id}/documents`, `GET .../{doc}/download`, `POST .../{doc}/approve`,
`DELETE .../{doc}`) · model `PiMeetingDocument` (`data` is a deferred column; the file is at most 4 MB) · erase:
`erase.py` now also removes documents AND `pi_meeting_bots` (a gap in the bot work: a bot row would have blocked a
meeting delete or a customer erase through its foreign key) · web `workspace/meeting-documents.tsx`.
Tests: `tests/unit/test_pi_meeting_deliverables.py`, `tests/integration/test_pi_meeting_documents.py`.

Dependencies added to `pyproject.toml` and both hashed lock files: `reportlab`, `python-pptx` (with `lxml`,
`xlsxwriter`). The lock also gained `arabic-reshaper` and `python-bidi`, which `pyproject.toml` already listed but the
lock did not: until now a production build had no Urdu shaping for the problem-map picture, so that picture fell
back to text. After this deploys, Urdu problem-map pictures will be drawn.

## Not built yet

- Sending an approved document to the customer on WhatsApp (needs the inbox's document message path; the summary text
  can already be sent from the Review tab).
- A solution/proposal deck (the existing solution document and quote pipeline stays as it is).
- Document images (the problem map picture inside the deck) and brand logo assets.
- Memory in the meeting job and the video-room work: see the plan `PMB-5`.
