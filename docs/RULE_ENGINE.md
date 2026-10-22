# Rule engine documentation

## What it is
A deterministic evaluator in `engine.py`. It matches selected business conditions against
predefined rules stored in SQLite (mirrored as editable JSON in `data/rules/`), then follows
the relational links (factor -> risk -> assertion/control/procedure -> evidence) to build a
consolidated audit plan.

## What it is NOT
Not AI. No language model, no embeddings, no probabilistic inference, no external service.
The same inputs + database version always produce the same outputs.

## Rule format (JSON)
```json
{
  "rule_id": "RULE-INV-001",
  "when": {
    "all":     [{"type": "factor_selected", "factor_id": "F-INV-001"}],
    "any":     [],
    "exclude": []
  },
  "then": {
    "risk_ids": ["R-INV-001"],
    "assertion_ids": ["BAL-EXI"],
    "control_ids": ["C-INV-001"],
    "procedure_ids": ["P-INV-001"],
    "missing_information": ["Whether inventory is material..."],
    "note": "free-text rationale"
  }
}
```
- `all`: every condition must hold. `any`: at least one must hold (ignored if empty).
  `exclude`: if ANY holds, the rule does not fire.
- Condition types: `factor_selected` (factor_id), `cycle_selected` (cycle_id).
  Unknown condition types never match (fail closed).
- Rules are evaluated in `(priority ASC, id ASC)` order; lower priority runs first.
  Merging of risks/procedures is deduplicated and order-stable.

## Editing a rule without changing code
1. Edit `data/rules/RULE-XXX.json`.
2. Run `python seed.py` to rebuild the database (previous versions are preserved in `rule_history`).
3. Run `pytest tests/` to verify.

## Versioning
Each rule has `version`, `effective_date`, `status` (Active/Superseded/Retired). Superseded
versions are archived in `rule_history` with a timestamp. The UI shows the rule id, version,
priority, rationale and review status for every triggered rule.

## Missing information
Rules declare what the auditor still needs to establish (`missing_information`); the UI
surfaces it so gaps are explicit rather than silently assumed.

## Guarantees and limits
- Only `Verified` records drive recommendations.
- A rule with no outcomes never fires.
- Invalid rule JSON is rejected by `seed.py --check` and skipped by the engine (flagged by `validate_db`).
- The engine does not conclude fraud, does not quantify misstatements, and does not replace
  professional judgment - see the judgment notice in the UI.
