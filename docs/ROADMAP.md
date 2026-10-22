# Roadmap for expanding the library

## Content gaps (priority order)
1. **Verify references** - trace seeded content to official ISA/IFRS paragraphs one standard at a time (see REFERENCES.md).
2. **Empty cycles** - Investments (CYC-INVST), Borrowings (CYC-BOR), Taxation (CYC-TAX) have cycle rows but no content.
3. **Provisions and contingencies (CYC-PROV)** - no factors seeded yet (estimation uncertainty, legal claims, warranties).
4. **Industry overlays** - manufacturing vs retail vs services variants of the same factors (e.g. consignment stock, long-term contracts).
5. **Fraud brainstorming prompts** - structured per-cycle fraud risk factors with mandatory "do not auto-conclude" handling.

## Feature gaps
- Full-text search (SQLite FTS5) once the library exceeds a few hundred records; current substring search is dependency-free.
- Risk significance rating + filters (business cycle, risk category, assertion, procedure type, source verification status) in the UI.
- Workpaper customisation: engagement name, materiality, preparer/reviewer sign-off fields in exports.
- Rule simulator: "what fires if..." preview when editing a rule file.
- Import/export of rule packs (JSON) for sharing reviewed rule sets between firms.
- Multi-user review workflow: draft -> under review -> verified with reviewer sign-off recorded in the database.
- Automated scheduled backups (currently manual via the app sidebar + pre-seed backup).

## Non-goals
AI-assisted drafting inside the product, cloud sync, user accounts, telemetry - the library stays
offline, deterministic and local-first by design.
