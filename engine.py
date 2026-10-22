"""
Deterministic rule engine for the Audit Risk and Evidence Library.

Pure stdlib. No AI, no network, no randomness. Given the same database
version and the same inputs, the engine always returns the same results:
rules are evaluated in (priority, id, version) order and every merge is
order-stable.

Rule definition format (canonical JSON, editable in data/rules/*.json)::

    {
      "rule_id": "RULE-INV-001",
      "when": {
        "all":     [ {"type": "factor_selected", "factor_id": "F-INV-001"} ],
        "any":     [ {"type": "cycle_selected",  "cycle_id":  "CYC-INV"} ],
        "exclude": [ {"type": "factor_selected", "factor_id": "F-INV-009"} ]
      },
      "then": {
        "risk_ids":      ["R-INV-001"],
        "assertion_ids": ["BAL-EXI"],
        "control_ids":   ["C-INV-001"],
        "procedure_ids": ["P-INV-001"],
        "missing_information": ["Whether the warehouse has CCTV..."],
        "note": "free-text rationale shown to the auditor"
      }
    }

Semantics:
  * "all"  - every condition must hold
  * "any"  - at least one condition must hold (ignored when empty)
  * "exclude" - if ANY condition holds, the rule does not fire
  * Condition types: factor_selected, cycle_selected
"""

import json
import sqlite3
import threading
from pathlib import Path

from db import BASE_DIR, connect


def load_rule_definitions(rules_dir=None):
    """Read editable rule JSON files from data/rules/. Returns {rule_id: dict}."""
    rules_dir = Path(rules_dir) if rules_dir else BASE_DIR / "data" / "rules"
    out = {}
    for path in sorted(rules_dir.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Rule file {path.name}: invalid JSON ({exc})")
        rules = doc if isinstance(doc, list) else [doc]
        for rule in rules:
            rid = rule.get("rule_id") or path.stem
            out[rid] = rule
    return out


class RuleEngine:
    def __init__(self, db_path=None):
        self.conn = connect(db_path)
        self.conn.row_factory = sqlite3.Row
        # Serialises all database access: the host app may call the engine
        # from different threads (e.g. Streamlit script runs).
        self._lock = threading.RLock()

    def query(self, sql, params=()):
        """Thread-safe read helper for callers that need raw rows."""
        with self._lock:
            return self.conn.execute(sql, params).fetchall()

    # ------------------------------------------------------------------ API
    def assess(self, selected_factor_ids, cycle_ids=None, industry_ids=None):
        """Run the full assessment.

        Returns a dict with triggered rules and a consolidated, deduplicated
        risk-and-testing plan. Deterministic: identical inputs + database
        always produce identical output.
        """
        with self._lock:
            return self._assess_locked(selected_factor_ids, cycle_ids, industry_ids)

    def _assess_locked(self, selected_factor_ids, cycle_ids=None, industry_ids=None):
        selected = sorted(set(selected_factor_ids or []))
        cycles = sorted(set(cycle_ids or []))
        industries = sorted(set(industry_ids or []))
        industry_added = []
        for ind in industries:
            for r in self.conn.execute(
                    "SELECT factor_id FROM industry_factor WHERE industry_id = ?", (ind,)):
                if r["factor_id"] not in selected:
                    selected.append(r["factor_id"])
                    industry_added.append({"industry_id": ind, "factor_id": r["factor_id"]})
        selected = sorted(selected)
        rules = self._active_rules()

        triggered = []
        for rule in rules:
            matched, missing = self._evaluate(rule["definition"], selected, cycles)
            if matched:
                triggered.append({
                    "rule_id": rule["id"],
                    "rule_name": rule["name"],
                    "version": rule["version"],
                    "priority": rule["priority"],
                    "effective_date": rule["effective_date"],
                    "rationale": rule["rationale"],
                    "source_reference": rule["source_reference"],
                    "review_status": rule["review_status"],
                    "missing_information": rule["definition"].get("then", {}).get("missing_information", []),
                    "unmet_conditions": missing,
                })

        plan = self._build_plan(triggered, selected)
        plan["selected_factor_ids"] = selected
        plan["cycle_ids"] = cycles
        plan["industry_ids"] = industries
        plan["industry_added_factors"] = industry_added
        plan["triggered_rules"] = triggered
        return plan

    # ------------------------------------------------------------- internals
    def _active_rules(self):
        rows = self.conn.execute(
            "SELECT id, name, version, priority, effective_date, definition,"
            "       rationale, source_reference, review_status"
            " FROM rules WHERE status = 'Active'"
            " ORDER BY priority ASC, id ASC, version DESC"
        ).fetchall()
        rules = []
        for r in rows:
            try:
                definition = json.loads(r["definition"])
            except json.JSONDecodeError:
                continue  # flagged by validate_db; never silently applied
            rules.append({
                "id": r["id"], "name": r["name"], "version": r["version"],
                "priority": r["priority"], "effective_date": r["effective_date"],
                "definition": definition, "rationale": r["rationale"],
                "source_reference": r["source_reference"],
                "review_status": r["review_status"],
            })
        return rules

    def _condition_holds(self, cond, selected, cycles):
        ctype = cond.get("type")
        if ctype == "factor_selected":
            return cond.get("factor_id") in selected
        if ctype == "cycle_selected":
            return cond.get("cycle_id") in cycles
        return False  # unknown condition types never match (fail closed)

    def _describe_condition(self, cond):
        ctype = cond.get("type")
        if ctype == "factor_selected":
            return f"business factor {cond.get('factor_id')} selected"
        if ctype == "cycle_selected":
            return f"business cycle {cond.get('cycle_id')} selected"
        return f"unknown condition {cond}"

    def _evaluate(self, definition, selected, cycles):
        """Return (matched: bool, missing: [str]) for one rule definition."""
        when = definition.get("when", {}) or {}
        then = definition.get("then", {}) or {}
        all_conds = when.get("all", []) or []
        any_conds = when.get("any", []) or []
        exclude_conds = when.get("exclude", []) or []

        missing = []
        for cond in all_conds:
            if not self._condition_holds(cond, selected, cycles):
                missing.append(self._describe_condition(cond))
        any_ok = True
        if any_conds:
            any_ok = any(self._condition_holds(c, selected, cycles) for c in any_conds)
            if not any_ok:
                missing.append("none of the alternative conditions held: "
                               + "; ".join(self._describe_condition(c) for c in any_conds))
        excluded = any(self._condition_holds(c, selected, cycles) for c in exclude_conds)

        matched = not missing and any_ok and not excluded
        # A rule with no outcomes can never "fire" usefully.
        if matched and not any(then.get(k) for k in
                               ("risk_ids", "procedure_ids", "control_ids", "assertion_ids")):
            matched = False
        return matched, missing

    def _row(self, table, rid):
        return self.conn.execute(f"SELECT * FROM {table} WHERE id = ?", (rid,)).fetchone()

    def _build_plan(self, triggered, selected):
        risk_ids, proc_ids, ctrl_ids, assert_ids = [], [], [], []
        rule_for = {}   # (bucket, id) -> set of rule ids that surfaced it
        missing_info = []

        for t in triggered:
            then = json.loads(self._rule_definition(t["rule_id"])).get("then", {})
            for bucket, seen in (("risk_ids", risk_ids), ("procedure_ids", proc_ids),
                                 ("control_ids", ctrl_ids), ("assertion_ids", assert_ids)):
                for nid in then.get(bucket, []):
                    if nid not in seen:
                        seen.append(nid)
                    rule_for.setdefault((bucket, nid), set()).add(t["rule_id"])
            for mi in t["missing_information"]:
                if mi not in missing_info:
                    missing_info.append(mi)

        risks = []
        for rid in risk_ids:
            r = self._row("risk_events", rid)
            if r is None or r["review_status"] != "Verified":
                continue
            risks.append({
                "id": r["id"], "title": r["title"], "description": r["description"],
                "causes": r["causes"], "potential_consequences": r["potential_consequences"],
                "cycle_id": r["cycle_id"], "inherent_risk_notes": r["inherent_risk_notes"],
                "source_reference": r["source_reference"],
                "significance": r["significance"] or "Other",
                "triggered_by_rules": sorted(rule_for.get(("risk_ids", rid), [])),
                "assertions": self._risk_assertions(rid),
                "controls": self._risk_controls(rid),
                "procedures": self._risk_procedures(rid, rule_for),
            })

        # Plan-level consolidation: one procedure may address several risks.
        # Present each procedure once, annotated with the risks it addresses.
        consolidated = []
        seen_proc = {}
        for risk in risks:
            for p in risk["procedures"]:
                if p["id"] not in seen_proc:
                    entry = dict(p)
                    entry["risk_ids"] = []
                    seen_proc[p["id"]] = entry
                    consolidated.append(entry)
                if risk["id"] not in seen_proc[p["id"]]["risk_ids"]:
                    seen_proc[p["id"]]["risk_ids"].append(risk["id"])

        fraud_responses = [p for p in consolidated if p.get("fraud_focus")]
        significant_risks = [r for r in risks if r.get("significance") == "Significant risk"]

        return {
            "risks": risks,
            "procedures": consolidated,
            "procedure_ids": [p["id"] for p in consolidated],
            "fraud_responses": fraud_responses,
            "significant_risks": [r["id"] for r in significant_risks],
            "control_ids": ctrl_ids,
            "assertion_ids": assert_ids,
            "missing_information": missing_info,
            "counts": {
                "rules_triggered": len(triggered),
                "risks": len(risks),
                "procedures": len(consolidated),
                "controls": len(ctrl_ids),
                "assertions": len(assert_ids),
                "fraud_responses": len(fraud_responses),
                "significant_risks": len(significant_risks),
            },
        }

    def _rule_definition(self, rule_id):
        row = self.conn.execute(
            "SELECT definition FROM rules WHERE id = ? AND status = 'Active'"
            " ORDER BY version DESC LIMIT 1", (rule_id,)).fetchone()
        return row["definition"]

    def _risk_assertions(self, risk_id):
        rows = self.conn.execute(
            "SELECT a.id, a.category, a.name, a.description, ra.why_relevant, ra.conditions"
            " FROM risk_assertion ra JOIN assertions a ON a.id = ra.assertion_id"
            " WHERE ra.risk_id = ? ORDER BY a.id", (risk_id,)).fetchall()
        return [dict(r) for r in rows]

    def _risk_controls(self, risk_id):
        rows = self.conn.execute(
            "SELECT c.*, rc.explanation AS link_explanation"
            " FROM risk_control rc JOIN controls c ON c.id = rc.control_id"
            " WHERE rc.risk_id = ? AND c.review_status = 'Verified' ORDER BY c.id", (risk_id,)).fetchall()
        return [dict(r) for r in rows]

    def _risk_procedures(self, risk_id, rule_for):
        rows = self.conn.execute(
            "SELECT p.*, rp.reason AS link_reason"
            " FROM risk_procedure rp JOIN audit_procedures p ON p.id = rp.procedure_id"
            " WHERE rp.risk_id = ? AND p.review_status = 'Verified' ORDER BY p.id", (risk_id,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["triggered_by_rules"] = sorted(rule_for.get(("procedure_ids", r["id"]), []))
            d["evidence"] = self._procedure_evidence(r["id"])
            d["assertions"] = [a["id"] for a in self.conn.execute(
                "SELECT assertion_id AS id FROM procedure_assertion WHERE procedure_id = ?"
                " ORDER BY assertion_id", (r["id"],)).fetchall()]
            out.append(d)
        return out

    def _procedure_evidence(self, procedure_id):
        rows = self.conn.execute(
            "SELECT e.*, pe.notes AS link_notes"
            " FROM procedure_evidence pe JOIN evidence e ON e.id = pe.evidence_id"
            " WHERE pe.procedure_id = ? AND e.review_status = 'Verified' ORDER BY e.id",
            (procedure_id,)).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------- search (FTS-free)
    def search(self, query, limit=50):
        """Simple offline substring search across the library (no FTS needed
        for the current dataset size; kept dependency-free)."""
        with self._lock:
            return self._search_locked(query, limit)

    # ------------------------------------------- industries / fraud / analytics
    def industries(self):
        with self._lock:
            return [dict(r) for r in self.conn.execute(
                "SELECT * FROM industries ORDER BY name").fetchall()]

    def industry_factors(self, industry_id):
        with self._lock:
            rows = self.conn.execute(
                "SELECT f.*, if_.explanation AS industry_explanation"
                " FROM industry_factor if_ JOIN business_factors f ON f.id = if_.factor_id"
                " WHERE if_.industry_id = ? AND f.review_status = 'Verified' ORDER BY f.id",
                (industry_id,)).fetchall()
            return [dict(r) for r in rows]

    def fraud_indicators(self):
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM business_factors"
                " WHERE risk_category = 'Fraud risk' AND review_status = 'Verified'"
                " ORDER BY id").fetchall()
            return [dict(r) for r in rows]

    def analytical_areas(self):
        with self._lock:
            return [r["area"] for r in self.conn.execute(
                "SELECT DISTINCT area FROM analytical_procedures"
                " WHERE review_status = 'Verified' ORDER BY area").fetchall()]

    def analytical_procedures(self, area=None):
        with self._lock:
            if area:
                rows = self.conn.execute(
                    "SELECT * FROM analytical_procedures"
                    " WHERE area = ? AND review_status = 'Verified' ORDER BY id", (area,)).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT * FROM analytical_procedures"
                    " WHERE review_status = 'Verified' ORDER BY area, id").fetchall()
            return [dict(r) for r in rows]

    def control_objectives(self):
        with self._lock:
            return [dict(r) for r in self.conn.execute(
                "SELECT * FROM control_objectives WHERE review_status = 'Verified'"
                " ORDER BY id").fetchall()]

    def controls_for_objective(self, objective_id):
        with self._lock:
            rows = self.conn.execute(
                "SELECT c.*, co.explanation AS link_explanation"
                " FROM control_objective co JOIN controls c ON c.id = co.control_id"
                " WHERE co.objective_id = ? AND c.review_status = 'Verified' ORDER BY c.id",
                (objective_id,)).fetchall()
            return [dict(r) for r in rows]

    def objectives_for_control(self, control_id):
        with self._lock:
            rows = self.conn.execute(
                "SELECT o.*, co.explanation AS link_explanation"
                " FROM control_objective co JOIN control_objectives o ON o.id = co.objective_id"
                " WHERE co.control_id = ? AND o.review_status = 'Verified' ORDER BY o.id",
                (control_id,)).fetchall()
            return [dict(r) for r in rows]

    def verified_controls(self):
        with self._lock:
            return [dict(r) for r in self.conn.execute(
                "SELECT * FROM controls WHERE review_status = 'Verified' ORDER BY id").fetchall()]


    def _search_locked(self, query, limit=50):
        q = f"%{query.strip().lower()}%"
        results = []

        def grab(sql, kind, label, n_params=2):
            for r in self.conn.execute(sql, (q,) * n_params).fetchmany(limit):
                results.append({"kind": kind, "id": r["id"], "label": label.format(**r)})

        grab("SELECT id, name FROM business_factors WHERE review_status='Verified'"
             " AND (LOWER(name) LIKE ? OR LOWER(description) LIKE ?) ORDER BY id",
             "factor", "Factor {id}: {name}")
        grab("SELECT id, title AS name FROM risk_events WHERE review_status='Verified'"
             " AND (LOWER(title) LIKE ? OR LOWER(description) LIKE ?) ORDER BY id",
             "risk", "Risk {id}: {name}")
        grab("SELECT id, title AS name FROM audit_procedures WHERE review_status='Verified'"
             " AND (LOWER(title) LIKE ? OR LOWER(steps) LIKE ?) ORDER BY id",
             "procedure", "Procedure {id}: {name}")
        grab("SELECT id, name FROM evidence WHERE review_status='Verified'"
             " AND (LOWER(name) LIKE ? OR LOWER(description) LIKE ?) ORDER BY id",
             "evidence", "Evidence {id}: {name}")
        grab("SELECT id, description AS name FROM controls WHERE review_status='Verified'"
             " AND (LOWER(description) LIKE ?) ORDER BY id",
             "control", "Control {id}", 1)
        return results[:limit]
