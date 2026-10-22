# Data dictionary

Source of truth: `db.py` (schema) + `library.db` (data). Assertion codes are fixed; everything
else is data and can grow without code changes.

## business_cycles
| Column | Meaning |
|---|---|
| id | PK, e.g. `CYC-REV` |
| name | Unique cycle name |
| description | Scope of the cycle |
| review_status | Draft / Under review / Verified / Retired |

Cycles: Revenue and receivables (CYC-REV), Purchases and payables (CYC-PUR), Inventory (CYC-INV),
Payroll (CYC-PAY), Cash and bank (CYC-CSH), Property, plant and equipment (CYC-PPE),
Investments (CYC-INVST), Borrowings (CYC-BOR), Provisions and contingencies (CYC-PROV),
Financial reporting and closing (CYC-FRP), Taxation (CYC-TAX).

## assertions (fixed library, 16 rows)
Codes: `TRN-*` transactions and events (Occurrence, Completeness, Accuracy, Cut-off,
Classification); `BAL-*` account balances (Existence, Rights and obligations, Completeness,
Accuracy valuation and allocation, Classification, Presentation); `DIS-*` presentation and
disclosure (Occurrence and rights and obligations, Completeness, Classification and
understandability, Accuracy and valuation). Terminology follows ISA 315 (Revised); no
paragraph numbers are cited anywhere in the library (see REFERENCES.md).

## business_factors
id (`F-<CYC>-NNN`), name, description, cycle_id -> business_cycles, risk_category
(Inherent/Fraud/Control risk), conditions_relevant, warning_signs, source_reference, review_status.

## risk_events
id (`R-...`), title, description, causes, potential_consequences, cycle_id, inherent_risk_notes,
source_reference, review_status.

## factor_risk (explicit reviewer-defined mapping)
factor_id + risk_id (composite PK), trigger_condition, applicability (incl. when irrelevant),
explanation (causal reasoning), additional_info_needed, confidence_basis, source_reference,
reviewer, review_status.

## risk_assertion
risk_id + assertion_id (PK), why_relevant (per-assertion rationale - required),
conditions (when the assertion applies).

## controls
id (`C-...`), description, objective, preventive_detective, manual_automated, frequency,
responsible_role, evidence_of_operation, limitations, source_reference, review_status.

## risk_control
risk_id + control_id (PK), explanation.

## audit_procedures
id (`P-...`), title, objective, steps (numbered text), procedure_type (11 supported types),
test_type (Test of controls / Substantive procedure / Dual-purpose), population,
sampling_notes, expected_result, exception_criteria, follow_up, source_reference, review_status.

## risk_procedure
risk_id + procedure_id (PK), reason (why this procedure addresses this risk).

## procedure_assertion
procedure_id + assertion_id (PK).

## evidence
id (`E-...`), name, description, source (Internal/External/Auditor-generated),
reliability_notes (required), limitations, expected_characteristics,
contradictory_evidence, source_reference, review_status.

## procedure_evidence
procedure_id + evidence_id (PK), notes.

## rules
id (`RULE-...`), name, version, priority, effective_date, status (Active/Superseded/Retired),
definition (canonical JSON: when{all,any,exclude} / then{risk_ids, assertion_ids, control_ids,
procedure_ids, missing_information, note}), rationale, source_reference, reviewed_by, review_status.
UNIQUE(id, version). See RULE_ENGINE.md.

## rule_history
Archives superseded rule versions: id, version, definition, superseded_at, superseded_by.

## standards
id, standard_name, issuing_organisation, paragraph, publication_date, jurisdiction, url,
verification_status (Verified/Unverified), notes.

## rule_standard
rule_id + standard_id (PK).

## library_builds
Audit trail of builds: build_id, built_at, note.

## industries
id (`IND-*`), name (unique), description, review_status. Seeded for Telecommunications (IND-TEL),
Manufacturing (IND-MFG), Retail (IND-RTL), Banking and financial services (IND-BNK).

## industry_factor
industry_id + factor_id (PK), explanation (why the factor is characteristic of the industry).
`RuleEngine.assess(..., industry_ids=[...])` auto-adds linked factors to the assessment.

## analytical_procedures
id (`AP-<AREA>-NNN`), area (e.g. Revenue, Inventory, Trade payables), title, detail (how to perform),
expected_relationship (the plausible relationship tested), investigation_threshold,
follow_up, cycle_id, source_reference, review_status.

## control_objectives
id (`OBJ-NNN`), objective (one-line statement), description, review_status.

## control_objective
control_id + objective_id (PK), explanation (how the control achieves the objective).
Powers the bidirectional Control explorer: objective -> controls and control -> objectives.

## Extended columns
- `business_factors.fraud_triangle`: Incentive or pressure / Opportunity / Rationalization (nullable).
- `risk_events.significance`: 'Significant risk' (ISA 315) or 'Other' (default).
- `audit_procedures.fraud_focus`: 1 = specifically responsive to fraud risks.
- `audit_procedures.response_level`: 'Standard' or 'Extended'.

## ID conventions
`CYC-` cycles, `F-` factors, `R-` risks, `C-` controls, `P-` procedures, `E-` evidence,
`RULE-` rules. The middle segment is the cycle prefix (REV, PUR, INV, PAY, CSH, PPE, FRP...).

## Validation (`db.validate_db`)
Foreign-key integrity; every Verified risk has >=1 Verified procedure and >=1 assertion link;
every Verified procedure has >=1 Verified evidence; every Verified record has a source reference;
every Active rule has valid JSON, >=1 outcome, and references only existing ids.
