Rebuild the industry packs from the specification. $ARGUMENTS (path to the PDF, default C:\Users\USER\Downloads\pi-brain-v3.pdf)

From `apps/api`: `../../.venv/Scripts/python.exe scripts/build_industry_packs.py "<pdf>" --out app/modules/pi/packs/industry`
(set `PYTHONIOENCODING=utf-8`; it takes a few minutes). Then validate every problem's category
against `taxonomy.KEYS`, count industries and overlays (expect 211 and 11), and run
`pytest tests/unit/test_pi_industry_packs.py`. Report counts and any validation error. Do not invent
content; show `git diff --stat` of the packs so the user sees what changed.
