"""
Seed loader for the Audit Risk and Evidence Library.

Reads structured seed files from data/seed/*.json and rule definitions from
data/rules/*.json, validates them, and loads them into library.db.

Each rule is also written out to data/rules/<RULE-ID>.json so rules remain
editable without touching application code; the database copy is what the
engine evaluates.

Usage:
    python seed.py                 # full rebuild (drops library tables, re-seeds)
    python seed.py --check FILE    # validate a seed file's structure only
"""

import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path

from db import BASE_DIR, REVIEW_STATUSES, connect, init_db, validate_db

SEED_DIR = BASE_DIR / "data" / "seed"
RULES_DIR = BASE_DIR / "data" / "rules"

PROCEDURE_TYPES = (
    "Inspection", "Observation", "Inquiry", "External confirmation",
    "Recalculation", "Reperformance", "Analytical procedures",
    "Vouching", "Tracing", "Cut-off testing", "Physical verification",
)
TEST_TYPES = ("Test of controls", "Substantive procedure", "Dual-purpose")


def check_seed_file(path):
    """Structural check of a seed file. Returns list of error strings."""
    errors = []
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"cannot parse: {exc}"]

    def need(items, keys, label):
        for i, it in enumerate(items or []):
            for k in keys:
                if k not in it or it[k] in (None, ""):
                    errors.append(f"{label}[{i}] missing/empty '{k}' (id={it.get('id', it.get('rule_id', '?'))})")

    need(doc.get("factors"), ["id", "name", "description", "cycle_id", "risk_category"], "factor")
    need(doc.get("risks"), ["id", "title", "description", "cycle_id"], "risk")
    need(doc.get("factor_risk"), ["factor_id", "risk_id", "explanation"], "factor_risk")
    need(doc.get("risk_assertions"), ["risk_id", "assertion_id", "why_relevant"], "risk_assertion")
    need(doc.get("controls"), ["id", "description"], "control")
    need(doc.get("procedures"),
         ["id", "title", "objective", "steps", "procedure_type", "test_type",
          "expected_result", "exception_criteria", "follow_up"], "procedure")
    need(doc.get("risk_procedures"), ["risk_id", "procedure_id"], "risk_procedure")
    need(doc.get("evidence"), ["id", "name", "description", "reliability_notes"], "evidence")
    need(doc.get("procedure_evidence"), ["procedure_id", "evidence_id"], "procedure_evidence")
    need(doc.get("rules"), ["rule_id", "name", "when", "then"], "rule")

    for p in doc.get("procedures", []):
        if p.get("procedure_type") not in PROCEDURE_TYPES:
            errors.append(f"procedure {p.get('id')}: unknown procedure_type '{p.get('procedure_type')}'")
        if p.get("test_type") not in TEST_TYPES:
            errors.append(f"procedure {p.get('id')}: unknown test_type '{p.get('test_type')}'")
        if isinstance(p.get("steps"), list) and not p["steps"]:
            errors.append(f"procedure {p.get('id')}: steps list is empty")

    for tab in ("factors", "risks", "controls", "procedures", "evidence"):
        for it in doc.get(tab, []):
            if it.get("review_status") and it["review_status"] not in REVIEW_STATUSES:
                errors.append(f"{tab} {it.get('id')}: bad review_status '{it.get('review_status')}'")

    for f in doc.get("factors", []):
        if f.get("fraud_triangle") and f["fraud_triangle"] not in (
                "Incentive or pressure", "Opportunity", "Rationalization"):
            errors.append(f"factor {f.get('id')}: bad fraud_triangle '{f.get('fraud_triangle')}'")
    for r in doc.get("risks", []):
        if r.get("significance") and r["significance"] not in ("Significant risk", "Other"):
            errors.append(f"risk {r.get('id')}: bad significance '{r.get('significance')}'")
    for p in doc.get("procedures", []):
        if p.get("response_level") and p["response_level"] not in ("Standard", "Extended"):
            errors.append(f"procedure {p.get('id')}: bad response_level '{p.get('response_level')}'")
        if "fraud_focus" in p and p["fraud_focus"] not in (0, 1, True, False):
            errors.append(f"procedure {p.get('id')}: fraud_focus must be 0/1")

    need(doc.get("industry_factors"), ["industry_id", "factor_id"], "industry_factor")
    need(doc.get("analytical_procedures"), ["id", "area", "title", "detail"], "analytical_procedure")
    need(doc.get("control_objectives"), ["id", "objective"], "control_objective")
    need(doc.get("control_objective_links"), ["control_id", "objective_id"], "control_objective_link")

    # id uniqueness within the file
    for tab, key in (("factors", "id"), ("risks", "id"), ("controls", "id"),
                     ("procedures", "id"), ("evidence", "id")):
        ids = [it[key] for it in doc.get(tab, [])]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            errors.append(f"{tab}: duplicate ids {sorted(dupes)}")
    return errors


def load_seed_file(conn, doc, source_name, rules_dir=None):
    # Deferred integrity: link tables may reference entities from seed files
    # loaded later (files load alphabetically). validate_db() checks FKs after.
    conn.execute("PRAGMA foreign_keys = OFF")
    cur = conn.cursor()
    rules_dir = Path(rules_dir) if rules_dir else RULES_DIR
    for f in doc.get("factors", []):
        cur.execute(
            """INSERT OR REPLACE INTO business_factors
               (id, name, description, cycle_id, risk_category, conditions_relevant,
                warning_signs, source_reference, review_status, fraud_triangle)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (f["id"], f["name"], f["description"], f["cycle_id"], f["risk_category"],
             f.get("conditions_relevant"), f.get("warning_signs"),
             f.get("source_reference"), f.get("review_status", "Draft"),
             f.get("fraud_triangle")),
        )
    for r in doc.get("risks", []):
        cur.execute(
            """INSERT OR REPLACE INTO risk_events
               (id, title, description, causes, potential_consequences, cycle_id,
                inherent_risk_notes, source_reference, review_status, significance)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (r["id"], r["title"], r["description"], r.get("causes"),
             r.get("potential_consequences"), r["cycle_id"], r.get("inherent_risk_notes"),
             r.get("source_reference"), r.get("review_status", "Draft"),
             r.get("significance", "Other")),
        )
    for m in doc.get("factor_risk", []):
        cur.execute(
            """INSERT OR REPLACE INTO factor_risk
               (factor_id, risk_id, trigger_condition, applicability, explanation,
                additional_info_needed, confidence_basis, source_reference, reviewer, review_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (m["factor_id"], m["risk_id"], m.get("trigger_condition"), m.get("applicability"),
             m["explanation"], m.get("additional_info_needed"), m.get("confidence_basis"),
             m.get("source_reference"), m.get("reviewer"), m.get("review_status", "Draft")),
        )
    for ra in doc.get("risk_assertions", []):
        cur.execute(
            "INSERT OR REPLACE INTO risk_assertion (risk_id, assertion_id, why_relevant, conditions)"
            " VALUES (?, ?, ?, ?)",
            (ra["risk_id"], ra["assertion_id"], ra["why_relevant"], ra.get("conditions")),
        )
    for c in doc.get("controls", []):
        cur.execute(
            """INSERT OR REPLACE INTO controls
               (id, description, objective, preventive_detective, manual_automated, frequency,
                responsible_role, evidence_of_operation, limitations, source_reference, review_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (c["id"], c["description"], c.get("objective"), c.get("preventive_detective"),
             c.get("manual_automated"), c.get("frequency"), c.get("responsible_role"),
             c.get("evidence_of_operation"), c.get("limitations"),
             c.get("source_reference"), c.get("review_status", "Draft")),
        )
    for rc in doc.get("risk_controls", []):
        cur.execute(
            "INSERT OR REPLACE INTO risk_control (risk_id, control_id, explanation) VALUES (?, ?, ?)",
            (rc["risk_id"], rc["control_id"], rc.get("explanation")),
        )
    for p in doc.get("procedures", []):
        steps = p["steps"]
        if isinstance(steps, list):
            steps = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps))
        cur.execute(
            """INSERT OR REPLACE INTO audit_procedures
               (id, title, objective, steps, procedure_type, test_type, population,
                sampling_notes, expected_result, exception_criteria, follow_up,
                source_reference, review_status, fraud_focus, response_level)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (p["id"], p["title"], p["objective"], steps, p["procedure_type"], p["test_type"],
             p.get("population"), p.get("sampling_notes"), p["expected_result"],
             p["exception_criteria"], p["follow_up"],
             p.get("source_reference"), p.get("review_status", "Draft"),
             int(bool(p.get("fraud_focus", 0))), p.get("response_level", "Standard")),
        )
    for rp in doc.get("risk_procedures", []):
        cur.execute(
            "INSERT OR REPLACE INTO risk_procedure (risk_id, procedure_id, reason) VALUES (?, ?, ?)",
            (rp["risk_id"], rp["procedure_id"], rp.get("reason")),
        )
    for pa in doc.get("procedure_assertions", []):
        cur.execute(
            "INSERT OR IGNORE INTO procedure_assertion (procedure_id, assertion_id) VALUES (?, ?)",
            (pa["procedure_id"], pa["assertion_id"]),
        )
    for e in doc.get("evidence", []):
        cur.execute(
            """INSERT OR REPLACE INTO evidence
               (id, name, description, source, reliability_notes, limitations,
                expected_characteristics, contradictory_evidence, source_reference, review_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (e["id"], e["name"], e["description"], e.get("source"), e["reliability_notes"],
             e.get("limitations"), e.get("expected_characteristics"),
             e.get("contradictory_evidence"), e.get("source_reference"),
             e.get("review_status", "Draft")),
        )
    for pe in doc.get("procedure_evidence", []):
        cur.execute(
            "INSERT OR REPLACE INTO procedure_evidence (procedure_id, evidence_id, notes)"
            " VALUES (?, ?, ?)",
            (pe["procedure_id"], pe["evidence_id"], pe.get("notes")),
        )

    for im in doc.get("industry_factors", []):
        cur.execute(
            "INSERT OR REPLACE INTO industry_factor (industry_id, factor_id, explanation)"
            " VALUES (?, ?, ?)",
            (im["industry_id"], im["factor_id"], im.get("explanation")),
        )
    for ap in doc.get("analytical_procedures", []):
        cur.execute(
            """INSERT OR REPLACE INTO analytical_procedures
               (id, area, title, detail, expected_relationship, investigation_threshold,
                follow_up, cycle_id, source_reference, review_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ap["id"], ap["area"], ap["title"], ap["detail"],
             ap.get("expected_relationship"), ap.get("investigation_threshold"),
             ap.get("follow_up"), ap.get("cycle_id"),
             ap.get("source_reference"), ap.get("review_status", "Draft")),
        )
    for o in doc.get("control_objectives", []):
        cur.execute(
            "INSERT OR REPLACE INTO control_objectives (id, objective, description, review_status)"
            " VALUES (?, ?, ?, ?)",
            (o["id"], o["objective"], o.get("description"), o.get("review_status", "Draft")),
        )
    for link in doc.get("control_objective_links", []):
        cur.execute(
            "INSERT OR REPLACE INTO control_objective (control_id, objective_id, explanation)"
            " VALUES (?, ?, ?)",
            (link["control_id"], link["objective_id"], link.get("explanation")),
        )
    for upd in doc.get("risk_updates", []):
        if upd.get("significance") not in ("Significant risk", "Other"):
            raise ValueError(f"risk_updates {upd.get('id')}: bad significance")
        cur.execute("UPDATE risk_events SET significance = ? WHERE id = ?",
                    (upd["significance"], upd["id"]))

    # rules: preserve history on version bump, mirror to editable JSON files
    for rule in doc.get("rules", []):
        rid = rule["rule_id"]
        definition = {"rule_id": rid, "when": rule.get("when", {}), "then": rule.get("then", {})}
        definition_json = json.dumps(definition, indent=2, sort_keys=True)
        existing = cur.execute(
            "SELECT version, definition FROM rules WHERE id = ? ORDER BY version DESC LIMIT 1",
            (rid,),
        ).fetchone()
        version = rule.get("version", 1)
        if existing and existing["version"] != version:
            cur.execute(
                "INSERT OR REPLACE INTO rule_history (id, version, definition, superseded_at, superseded_by)"
                " VALUES (?, ?, ?, ?, ?)",
                (rid, existing["version"], existing["definition"],
                 time.strftime("%Y-%m-%d %H:%M:%S"), version),
            )
            cur.execute("UPDATE rules SET status = 'Superseded' WHERE id = ? AND version = ?",
                        (rid, existing["version"]))
        cur.execute(
            """INSERT OR REPLACE INTO rules
               (id, name, version, priority, effective_date, status, definition,
                rationale, source_reference, reviewed_by, review_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rid, rule["name"], version, rule.get("priority", 100),
             rule.get("effective_date"), rule.get("status", "Active"), definition_json,
             rule.get("rationale"), rule.get("source_reference"),
             rule.get("reviewed_by"), rule.get("review_status", "Draft")),
        )
        RULES_DIR.mkdir(parents=True, exist_ok=True)
        (rules_dir / f"{rid}.json").write_text(
            json.dumps({**rule, "definition": definition}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--check":
        errs = check_seed_file(sys.argv[2])
        print("OK - no structural errors" if not errs else "\n".join(errs))
        sys.exit(1 if errs else 0)

    # full rebuild
    db_path = BASE_DIR / "library.db"
    if db_path.exists():
        backup = BASE_DIR / "backups" / f"library-pre-seed-{time.strftime('%Y%m%d-%H%M%S')}.db"
        backup.parent.mkdir(exist_ok=True)
        shutil.copy2(db_path, backup)
        print(f"backed up previous db -> {backup}")
    if db_path.exists():
        db_path.unlink()
    conn = init_db(db_path)
    # Deferred integrity: seed files are loaded alphabetically but link tables
    # may reference entities from files loaded later. FKs stay logically
    # enforced - validate_db() runs PRAGMA foreign_key_check after the load.
    conn.execute("PRAGMA foreign_keys = OFF")

    seed_files = sorted(SEED_DIR.glob("*.json"))
    if not seed_files:
        print("no seed files found in", SEED_DIR)
    total_errors = []
    for path in seed_files:
        errs = check_seed_file(path)
        if errs:
            print(f"== {path.name}: structural errors, skipped ==")
            print("\n".join(errs))
            total_errors.extend(errs)
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        load_seed_file(conn, doc, path.name)
        print(f"loaded {path.name}")
    conn.execute(
        "INSERT INTO library_builds (built_at, note) VALUES (?, ?)",
        (time.strftime("%Y-%m-%d %H:%M:%S"),
         f"seeded from {len(seed_files)} files"),
    )
    conn.commit()

    validation_errors = validate_db(conn)
    if validation_errors:
        print("== validation errors ==")
        print("\n".join(validation_errors))
    else:
        print("validation: OK")
    conn.close()
    sys.exit(1 if (total_errors or validation_errors) else 0)


if __name__ == "__main__":
    main()
