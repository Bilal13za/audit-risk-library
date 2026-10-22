# Audit Risk and Evidence Library

An offline, deterministic audit knowledge system. Select the business conditions observed at a
client and get a traceable chain:

**business factor -> risk event -> potential misstatement -> affected accounts/assertions ->
relevant controls -> audit procedures -> required evidence -> expected results ->
exception conditions -> follow-up procedures.**

No AI, no LLM, no cloud, no paid APIs. Structured data + explicit rules + SQLite queries.

## Quick start (Windows)
1. Extract the ZIP, double-click **`run_windows.bat`** (installs Python + packages on first run).
2. The app opens at http://localhost:8502. Fully offline after setup.

## Quick start (any OS with Python 3.10+)
```bash
pip install -r requirements.txt
python seed.py          # builds library.db from data/seed/*.json
streamlit run app.py
pytest tests/           # automated test suite
```

## Project layout
| Path | Purpose |
|---|---|
| `app.py` | Streamlit UI: search, interactive risk assessment, library browser, backup |
| `engine.py` | Deterministic rule engine (no AI, no network) |
| `db.py` | SQLite schema + fixed assertion/cycle data + `validate_db()` |
| `seed.py` | Seed loader; `--check` validates a seed file; full run rebuilds `library.db` |
| `export.py` | CSV + formatted Excel workpaper export |
| `data/seed/*.json` | Editable audit content (factors, risks, procedures, evidence, rules) |
| `data/rules/*.json` | Editable rule definitions (mirrored into the DB by `seed.py`) |
| `library.db` | The built SQLite database (generated, not hand-edited) |
| `docs/` | Data dictionary, rule-engine docs, references register, roadmap, Windows install guide |
| `tests/` | Pytest suite covering the 12 testing requirements + inventory acceptance test |
| `sample_workpapers/` | Example CSV/Excel workpapers generated from the library |
| `backups/` | Database snapshots |

## The chain, traced
Every recommendation shows its reasoning: which rule fired (id, version, priority, rationale),
why each assertion is relevant, why each procedure addresses the risk, what evidence is needed
and how reliable it is, what result is expected, what counts as an exception, and what to do
if a test fails. Missing information is reported, not assumed.

## Concepts kept distinct
Risk factor / identified risk / potential misstatement / control deficiency / exception /
confirmed misstatement / suspected fraud indicator - never treated as interchangeable.
A failed control test does not prove misstatement; a passed one does not prove correctness.
The system supports professional judgment; it does not replace it.

## References
No ISA/IFRS paragraph numbers are fabricated. See `docs/REFERENCES.md` for the
verified/unverified register.

## Status
v1.2 library: 49 factors, 45 risks, 128 procedures, 121 evidence items, 80 controls, 50 rules across 10 seed files:
- 29 core scenarios across 6 business cycles (revenue, purchases, inventory, payroll, cash, PPE, financial reporting)
- 12 industry inherent-risk scenarios (telecom incl. tower decommissioning, manufacturing, retail, banking)
- 8 fraud indicators (fraud-triangle mapped) + 4 significant fraud risks + 6 fraud-focused procedures
- 21 analytical procedures across 7 audit areas; 12 control objectives bidirectionally linked to controls
All `Verified` on a professional-practice basis with standards references unverified. 22/22 pytest pass. See `docs/ROADMAP.md` for expansion plans.


## Run on any device (in your browser)

The Windows download above is the full offline version. To open this app on
your phone, tablet, or any computer without installing anything, host it free
on **Streamlit Community Cloud**:

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
2. **New app** → pick this repository (`Bilal13za/audit-risk-library`), branch `main`,
   main file `app.py`.
3. **Deploy** — after a minute or two you get a link like
   `https://audit-risk-library.streamlit.app` that works on any device.

Two honest caveats: anything you save in the cloud copy is temporary (it
resets when the app sleeps from inactivity), and the Windows version
remains the full, keep-everything version.
