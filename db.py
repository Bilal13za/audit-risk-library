"""
Audit Risk and Evidence Library - database layer.

Creates the SQLite schema, seeds the fixed reference data (business cycles,
assertion library), and validates library records before they are accepted.

Design notes
------------
* No network access, no AI, no paid services: pure stdlib + SQLite.
* Data lives in SQLite; rule definitions also ship as editable JSON files in
  data/rules/ and are loaded into the database so the same inputs + database
  version always produce the same results.
* Review statuses: Draft, Under review, Verified, Retired. Only Verified
  records are presented as audit guidance by the rule engine.
"""

import json
import sqlite3
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB = BASE_DIR / "library.db"

REVIEW_STATUSES = ("Draft", "Under review", "Verified", "Retired")

SCHEMA = """
PRAGMA foreign_keys = ON;

-- A. Business cycles -------------------------------------------------------
CREATE TABLE IF NOT EXISTS business_cycles (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,
    description  TEXT NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'Verified'
);

-- E. Financial statement assertions (fixed library) -------------------------
CREATE TABLE IF NOT EXISTS assertions (
    id            TEXT PRIMARY KEY,      -- e.g. TRN-OCC, BAL-EXI, DIS-COM
    category      TEXT NOT NULL,         -- Transactions and events / Account balances / Presentation and disclosure
    name          TEXT NOT NULL,
    description   TEXT NOT NULL,
    framework_note TEXT
);

-- B. Business factors -------------------------------------------------------
CREATE TABLE IF NOT EXISTS business_factors (
    id                 TEXT PRIMARY KEY,  -- e.g. F-INV-001
    name               TEXT NOT NULL,
    description        TEXT NOT NULL,
    cycle_id           TEXT NOT NULL REFERENCES business_cycles(id),
    risk_category      TEXT NOT NULL,     -- Inherent risk / Fraud risk / Control risk / ...
    conditions_relevant TEXT,            -- conditions under which the factor is relevant
    warning_signs      TEXT,
    source_reference   TEXT,
    review_status      TEXT NOT NULL DEFAULT 'Draft'
);

-- C. Risk events ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS risk_events (
    id                      TEXT PRIMARY KEY,  -- e.g. R-INV-001
    title                   TEXT NOT NULL,
    description             TEXT NOT NULL,
    causes                  TEXT,
    potential_consequences  TEXT,
    cycle_id                TEXT NOT NULL REFERENCES business_cycles(id),
    inherent_risk_notes     TEXT,
    source_reference        TEXT,
    review_status           TEXT NOT NULL DEFAULT 'Draft'
);

-- D. Factor-risk mapping (explicit reviewer-defined links) -------------------
CREATE TABLE IF NOT EXISTS factor_risk (
    factor_id            TEXT NOT NULL REFERENCES business_factors(id),
    risk_id              TEXT NOT NULL REFERENCES risk_events(id),
    trigger_condition    TEXT,
    applicability        TEXT,   -- conditions that make the mapping applicable
    explanation          TEXT NOT NULL,
    additional_info_needed TEXT,
    confidence_basis     TEXT,   -- why the reviewer believes the link holds
    source_reference     TEXT,
    reviewer             TEXT,
    review_status        TEXT NOT NULL DEFAULT 'Draft',
    PRIMARY KEY (factor_id, risk_id)
);

-- Risk <-> assertion links (with per-assertion rationale) -------------------
CREATE TABLE IF NOT EXISTS risk_assertion (
    risk_id       TEXT NOT NULL REFERENCES risk_events(id),
    assertion_id  TEXT NOT NULL REFERENCES assertions(id),
    why_relevant  TEXT NOT NULL,  -- why THIS assertion for THIS risk
    conditions    TEXT,           -- under what conditions the assertion is relevant
    PRIMARY KEY (risk_id, assertion_id)
);

-- F. Controls ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS controls (
    id                  TEXT PRIMARY KEY,  -- e.g. C-INV-001
    description         TEXT NOT NULL,
    objective           TEXT,
    preventive_detective TEXT,  -- Preventive / Detective / Both
    manual_automated    TEXT,    -- Manual / Automated / IT-dependent manual
    frequency           TEXT,
    responsible_role    TEXT,
    evidence_of_operation TEXT,
    limitations         TEXT,
    source_reference    TEXT,
    review_status       TEXT NOT NULL DEFAULT 'Draft'
);

CREATE TABLE IF NOT EXISTS risk_control (
    risk_id    TEXT NOT NULL REFERENCES risk_events(id),
    control_id TEXT NOT NULL REFERENCES controls(id),
    explanation TEXT,
    PRIMARY KEY (risk_id, control_id)
);

-- G. Audit procedures -------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_procedures (
    id                TEXT PRIMARY KEY,  -- e.g. P-INV-001
    title             TEXT NOT NULL,
    objective         TEXT NOT NULL,
    steps             TEXT NOT NULL,     -- numbered steps, newline separated
    procedure_type    TEXT NOT NULL,     -- Inspection / Observation / Inquiry / External confirmation /
                                        -- Recalculation / Reperformance / Analytical procedures /
                                        -- Vouching / Tracing / Cut-off testing / Physical verification
    test_type         TEXT NOT NULL,     -- Test of controls / Substantive procedure / Dual-purpose
    population        TEXT,
    sampling_notes    TEXT,
    expected_result   TEXT NOT NULL,
    exception_criteria TEXT NOT NULL,
    follow_up         TEXT NOT NULL,
    source_reference  TEXT,
    review_status     TEXT NOT NULL DEFAULT 'Draft'
);

CREATE TABLE IF NOT EXISTS risk_procedure (
    risk_id      TEXT NOT NULL REFERENCES risk_events(id),
    procedure_id TEXT NOT NULL REFERENCES audit_procedures(id),
    reason       TEXT,   -- why this procedure addresses this risk
    PRIMARY KEY (risk_id, procedure_id)
);

CREATE TABLE IF NOT EXISTS procedure_assertion (
    procedure_id TEXT NOT NULL REFERENCES audit_procedures(id),
    assertion_id TEXT NOT NULL REFERENCES assertions(id),
    PRIMARY KEY (procedure_id, assertion_id)
);

-- H. Evidence library -------------------------------------------------------
CREATE TABLE IF NOT EXISTS evidence (
    id                       TEXT PRIMARY KEY,  -- e.g. E-INV-001
    name                     TEXT NOT NULL,
    description              TEXT NOT NULL,
    source                   TEXT,   -- Internal / External / Auditor-generated
    reliability_notes        TEXT NOT NULL,
    limitations              TEXT,
    expected_characteristics TEXT,
    contradictory_evidence   TEXT,
    source_reference         TEXT,
    review_status            TEXT NOT NULL DEFAULT 'Draft'
);

CREATE TABLE IF NOT EXISTS procedure_evidence (
    procedure_id TEXT NOT NULL REFERENCES audit_procedures(id),
    evidence_id  TEXT NOT NULL REFERENCES evidence(id),
    notes        TEXT,
    PRIMARY KEY (procedure_id, evidence_id)
);

-- I. Rule conditions (deterministic rules) ----------------------------------
-- The canonical definition lives in data/rules/*.json; the DB copy is what the
-- engine evaluates, and rule_history preserves every superseded version.
CREATE TABLE IF NOT EXISTS rules (
    id             TEXT PRIMARY KEY,  -- e.g. RULE-INV-001
    name           TEXT NOT NULL,
    version        INTEGER NOT NULL DEFAULT 1,
    priority       INTEGER NOT NULL DEFAULT 100,  -- lower runs first
    effective_date TEXT,
    status         TEXT NOT NULL DEFAULT 'Active',  -- Active / Superseded / Retired
    definition     TEXT NOT NULL,     -- canonical JSON (see RULE_ENGINE.md)
    rationale      TEXT,
    source_reference TEXT,
    reviewed_by    TEXT,
    review_status  TEXT NOT NULL DEFAULT 'Draft',
    UNIQUE (id, version)
);

CREATE TABLE IF NOT EXISTS rule_history (
    id             TEXT NOT NULL,
    version        INTEGER NOT NULL,
    definition     TEXT NOT NULL,
    superseded_at  TEXT NOT NULL,
    superseded_by  INTEGER,
    PRIMARY KEY (id, version)
);

-- J. Standards and references -----------------------------------------------
CREATE TABLE IF NOT EXISTS standards (
    id                  TEXT PRIMARY KEY,
    standard_name       TEXT NOT NULL,
    issuing_organisation TEXT,
    paragraph           TEXT,
    publication_date    TEXT,
    jurisdiction        TEXT,
    url                 TEXT,
    verification_status TEXT NOT NULL DEFAULT 'Unverified',  -- Verified / Unverified
    notes               TEXT
);

CREATE TABLE IF NOT EXISTS rule_standard (
    rule_id     TEXT NOT NULL REFERENCES rules(id),
    standard_id TEXT NOT NULL REFERENCES standards(id),
    PRIMARY KEY (rule_id, standard_id)
);

-- Audit trail of library builds ---------------------------------------------
CREATE TABLE IF NOT EXISTS library_builds (
    build_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    built_at     TEXT NOT NULL,
    note         TEXT
);

-- Industries ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS industries (
    id            TEXT PRIMARY KEY,   -- e.g. IND-TEL
    name          TEXT NOT NULL UNIQUE,
    description   TEXT NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'Verified'
);

-- Industry <-> factor links: factors characteristic of an industry -----------
CREATE TABLE IF NOT EXISTS industry_factor (
    industry_id TEXT NOT NULL REFERENCES industries(id),
    factor_id   TEXT NOT NULL REFERENCES business_factors(id),
    explanation TEXT,   -- why this factor is characteristic of the industry
    PRIMARY KEY (industry_id, factor_id)
);

-- Analytical procedures library (by audit area) ------------------------------
CREATE TABLE IF NOT EXISTS analytical_procedures (
    id                      TEXT PRIMARY KEY,  -- e.g. AP-REV-001
    area                    TEXT NOT NULL,     -- Revenue / Inventory / Trade payables / ...
    title                   TEXT NOT NULL,
    detail                  TEXT NOT NULL,     -- how to perform it
    expected_relationship   TEXT,              -- the plausible relationship tested
    investigation_threshold TEXT,
    follow_up               TEXT,
    cycle_id                TEXT REFERENCES business_cycles(id),
    source_reference        TEXT,
    review_status           TEXT NOT NULL DEFAULT 'Draft'
);

-- Control objectives (bidirectional with controls) ---------------------------
CREATE TABLE IF NOT EXISTS control_objectives (
    id          TEXT PRIMARY KEY,   -- e.g. OBJ-001
    objective   TEXT NOT NULL,
    description TEXT,
    review_status TEXT NOT NULL DEFAULT 'Draft'
);

CREATE TABLE IF NOT EXISTS control_objective (
    control_id   TEXT NOT NULL REFERENCES controls(id),
    objective_id TEXT NOT NULL REFERENCES control_objectives(id),
    explanation  TEXT,   -- how this control achieves the objective
    PRIMARY KEY (control_id, objective_id)
);
"""

# Fixed assertion library (ISA 315 (Revised) terminology; paragraph numbers
# intentionally NOT cited - see docs/REFERENCES.md)
ASSERTIONS = [
    # Transactions and events
    ("TRN-OCC", "Transactions and events", "Occurrence",
     "Transactions and events that have been recorded have occurred and pertain to the entity.",
     "Assertions about classes of transactions and events."),
    ("TRN-COM", "Transactions and events", "Completeness",
     "All transactions and events that should have been recorded have been recorded.",
     "Assertions about classes of transactions and events."),
    ("TRN-ACC", "Transactions and events", "Accuracy",
     "Amounts and other data relating to recorded transactions and events have been recorded appropriately.",
     "Assertions about classes of transactions and events."),
    ("TRN-CUT", "Transactions and events", "Cut-off",
     "Transactions and events have been recorded in the correct accounting period.",
     "Assertions about classes of transactions and events."),
    ("TRN-CLS", "Transactions and events", "Classification",
     "Transactions and events have been recorded in the proper accounts.",
     "Assertions about classes of transactions and events."),
    # Account balances
    ("BAL-EXI", "Account balances", "Existence",
     "Assets, liabilities and equity interests exist.",
     "Assertions about account balances at period end."),
    ("BAL-RGT", "Account balances", "Rights and obligations",
     "The entity holds or controls the rights to assets, and liabilities are the obligations of the entity.",
     "Assertions about account balances at period end."),
    ("BAL-COM", "Account balances", "Completeness",
     "All assets, liabilities and equity interests that should have been recorded have been recorded.",
     "Assertions about account balances at period end."),
    ("BAL-VAL", "Account balances", "Accuracy, valuation and allocation",
     "Assets, liabilities and equity interests have been included in the financial statements at appropriate amounts and any resulting valuation or allocation adjustments have been appropriately recorded.",
     "Assertions about account balances at period end."),
    ("BAL-CLS", "Account balances", "Classification",
     "Assets, liabilities and equity interests have been recorded in the proper accounts.",
     "Assertions about account balances at period end."),
    ("BAL-PRS", "Account balances", "Presentation",
     "Assets, liabilities and equity interests are appropriately aggregated or disaggregated and clearly described, and related disclosures are relevant and understandable.",
     "Assertions about account balances at period end."),
    # Presentation and disclosure
    ("DIS-OCC", "Presentation and disclosure", "Occurrence and rights and obligations",
     "Disclosed events, transactions and other matters have occurred and pertain to the entity.",
     "Assertions about presentation and disclosure."),
    ("DIS-COM", "Presentation and disclosure", "Completeness",
     "All disclosures that should have been included in the financial statements have been included.",
     "Assertions about presentation and disclosure."),
    ("DIS-CLS", "Presentation and disclosure", "Classification and understandability",
     "Financial information is appropriately presented and described, and disclosures are clearly expressed.",
     "Assertions about presentation and disclosure."),
    ("DIS-VAL", "Presentation and disclosure", "Accuracy and valuation",
     "Financial and other information is disclosed fairly and at appropriate amounts.",
     "Assertions about presentation and disclosure."),
]

CYCLES = [
    ("CYC-REV", "Revenue and receivables",
     "Order to cash: sales orders, dispatch, billing, credit notes, cash collection, trade receivables and related allowances."),
    ("CYC-PUR", "Purchases and payables",
     "Procure to pay: supplier selection, purchase orders, goods receipt, invoice matching, payments, trade payables and accruals."),
    ("CYC-INV", "Inventory",
     "Inventory receipt, storage, movement, counting, valuation (including cost and net realisable value), and obsolescence."),
    ("CYC-PAY", "Payroll",
     "Hiring, timekeeping, payroll calculation, payment, deductions, and related liabilities and disclosures."),
    ("CYC-CSH", "Cash and bank",
     "Cash handling, bank accounts, receipts, payments, transfers, reconciliations and petty cash."),
    ("CYC-PPE", "Property, plant and equipment",
     "Acquisition, capitalisation, depreciation, impairment, disposals and physical safeguarding of fixed assets."),
    ("CYC-INVST", "Investments",
     "Acquisition, valuation, income recognition and disposal of investments. (Library content not yet populated.)"),
    ("CYC-BOR", "Borrowings",
     "Loan origination, drawdown, interest, covenants and repayment. (Library content not yet populated.)"),
    ("CYC-PROV", "Provisions and contingencies",
     "Recognition, measurement and disclosure of provisions, contingent liabilities and contingent assets."),
    ("CYC-FRP", "Financial reporting and closing",
     "Period-end close, journal entries, consolidation, management estimates, related parties and financial statement disclosures."),
    ("CYC-TAX", "Taxation",
     "Current and deferred tax computation, compliance and disclosure. (Library content not yet populated.)"),
]

INDUSTRIES = [
    ("IND-TEL", "Telecommunications",
     "Network operators: towers and network equipment, high-volume billing, multi-element customer contracts, decommissioning obligations for installed infrastructure."),
    ("IND-MFG", "Manufacturing",
     "Production entities: work in progress, standard costing, overhead absorption, warranty provisions, capital-intensive plant."),
    ("IND-RTL", "Retail",
     "High-volume cash and card sales, shrinkage, supplier rebates, gift cards/loyalty programmes, leased store portfolios."),
    ("IND-BNK", "Banking and financial services",
     "Regulated lenders: loan impairment (expected credit losses), interest recognition, regulatory capital and disclosures."),
]


def _migrate(conn):
    """Additive migrations for databases created before these columns/tables existed."""
    migrations = [
        "ALTER TABLE business_factors ADD COLUMN fraud_triangle TEXT",
        "ALTER TABLE risk_events ADD COLUMN significance TEXT NOT NULL DEFAULT 'Other'",
        "ALTER TABLE audit_procedures ADD COLUMN fraud_focus INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE audit_procedures ADD COLUMN response_level TEXT NOT NULL DEFAULT 'Standard'",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise


def connect(db_path=None):
    db_path = Path(db_path) if db_path else DEFAULT_DB
    # check_same_thread=False: the app server (Streamlit) may serve different
    # requests on different threads while sharing one cached engine. All access
    # is serialised with a lock in engine.RuleEngine; the app only reads.
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path=None):
    """Create schema and seed fixed reference data. Idempotent."""
    conn = connect(db_path)
    conn.executescript(SCHEMA)
    _migrate(conn)
    for cid, name, desc in CYCLES:
        conn.execute(
            "INSERT OR IGNORE INTO business_cycles (id, name, description) VALUES (?, ?, ?)",
            (cid, name, desc),
        )
    for iid, name, desc in INDUSTRIES:
        conn.execute(
            "INSERT OR IGNORE INTO industries (id, name, description) VALUES (?, ?, ?)",
            (iid, name, desc),
        )
    for aid, cat, name, desc, note in ASSERTIONS:
        conn.execute(
            "INSERT OR IGNORE INTO assertions (id, category, name, description, framework_note)"
            " VALUES (?, ?, ?, ?, ?)",
            (aid, cat, name, desc, note),
        )
    conn.execute(
        "INSERT INTO library_builds (built_at, note) VALUES (?, ?)",
        (time.strftime("%Y-%m-%d %H:%M:%S"), "schema initialised"),
    )
    conn.commit()
    return conn


def _needs_seed(conn):
    """True when the database is missing or has no library content.

    A fresh ``sqlite3.connect()`` creates an empty file without tables, so a
    first run on a new machine (or a cloud deploy) must initialise + seed.
    An existing database with content is never touched.
    """
    try:
        row = conn.execute("SELECT COUNT(*) FROM business_factors").fetchone()
    except sqlite3.OperationalError:
        return True  # table (or the whole schema) is missing
    return (row[0] if row else 0) == 0


def ensure_db(db_path=None):
    """Make sure the database exists, is initialised, and is seeded.

    Safe to call on every startup: it is a single cheap ``COUNT(*)`` when the
    database already has content, and only builds + seeds on a fresh/empty
    database. Never deletes or rebuilds existing content (unlike seed.py's
    manual full-rebuild mode). Returns an open connection to the ready database.
    """
    db_path = Path(db_path) if db_path else DEFAULT_DB
    probe = connect(db_path)
    try:
        if not _needs_seed(probe):
            return probe
    except Exception:
        probe.close()
        raise
    probe.close()
    # Fresh or empty database: build schema + fixed data, then load the seed library.
    # Lazy import: seed.py imports from db.py, so import here to avoid a cycle.
    from seed import SEED_DIR, check_seed_file, load_seed_file

    conn = init_db(db_path)
    # Mirror seed.py's full-rebuild load order (FKs deferred, validated after).
    conn.execute("PRAGMA foreign_keys = OFF")
    seed_files = sorted(SEED_DIR.glob("*.json"))
    for path in seed_files:
        if check_seed_file(path):
            continue  # structural errors - skip, same as seed.py
        doc = json.loads(path.read_text(encoding="utf-8"))
        load_seed_file(conn, doc, path.name)
    conn.execute(
        "INSERT INTO library_builds (built_at, note) VALUES (?, ?)",
        (time.strftime("%Y-%m-%d %H:%M:%S"),
         f"seeded on first run from {len(seed_files)} files"),
    )
    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate_db(conn):
    """Check library integrity. Returns a list of error strings (empty = OK).

    Checks:
      1. foreign-key integrity
      2. every Verified risk has >= 1 Verified procedure via risk_procedure
      3. every Verified procedure has >= 1 Verified evidence via procedure_evidence
      4. every Verified risk has >= 1 assertion link with a rationale
      5. every Active rule has valid JSON definition and at least one outcome
      6. every Verified record has a non-empty source_reference or notes
      7. every Active rule's referenced ids actually exist
    """
    errors = []

    fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    for row in fk:
        errors.append(f"FK violation in {row['table']}: rowid {row['rowid']} -> {row['fktable']}.{row['fkid']}")

    risks = conn.execute(
        "SELECT id, title FROM risk_events WHERE review_status = 'Verified'"
    ).fetchall()
    for r in risks:
        n = conn.execute(
            "SELECT COUNT(*) c FROM risk_procedure rp JOIN audit_procedures p ON p.id = rp.procedure_id"
            " WHERE rp.risk_id = ? AND p.review_status = 'Verified'", (r["id"],)
        ).fetchone()["c"]
        if n == 0:
            errors.append(f"Verified risk {r['id']} ({r['title']}) has no Verified procedure.")
        n = conn.execute(
            "SELECT COUNT(*) c FROM risk_assertion WHERE risk_id = ?", (r["id"],)
        ).fetchone()["c"]
        if n == 0:
            errors.append(f"Verified risk {r['id']} ({r['title']}) has no assertion link.")

    procs = conn.execute(
        "SELECT id, title FROM audit_procedures WHERE review_status = 'Verified'"
    ).fetchall()
    for p in procs:
        n = conn.execute(
            "SELECT COUNT(*) c FROM procedure_evidence pe JOIN evidence e ON e.id = pe.evidence_id"
            " WHERE pe.procedure_id = ? AND e.review_status = 'Verified'", (p["id"],)
        ).fetchone()["c"]
        if n == 0:
            errors.append(f"Verified procedure {p['id']} ({p['title']}) has no Verified evidence.")

    for table, label in (
        ("risk_events", "risk"), ("business_factors", "factor"), ("audit_procedures", "procedure"),
        ("evidence", "evidence item"), ("controls", "control"),
    ):
        rows = conn.execute(
            f"SELECT id FROM {table} WHERE review_status = 'Verified'"
            " AND (source_reference IS NULL OR TRIM(source_reference) = '')"
        ).fetchall()
        for row in rows:
            errors.append(f"Verified {label} {row['id']} has no source reference.")

    for o in conn.execute(
            "SELECT id, objective FROM control_objectives WHERE review_status = 'Verified'").fetchall():
        n = conn.execute(
            "SELECT COUNT(*) c FROM control_objective WHERE objective_id = ?", (o["id"],)
        ).fetchone()["c"]
        if n == 0:
            errors.append(f"Verified control objective {o['id']} has no linked controls.")

    for ap in conn.execute(
            "SELECT id FROM analytical_procedures WHERE review_status = 'Verified'").fetchall():
        n = conn.execute(
            "SELECT COUNT(*) c FROM analytical_procedures WHERE id = ? AND detail IS NOT NULL"
            " AND TRIM(detail) != ''", (ap["id"],)
        ).fetchone()["c"]
        if n == 0:
            errors.append(f"Verified analytical procedure {ap['id']} has no detail.")

    rules = conn.execute("SELECT id, version, definition FROM rules WHERE status = 'Active'").fetchall()
    for rule in rules:
        try:
            d = json.loads(rule["definition"])
        except json.JSONDecodeError as exc:
            errors.append(f"Rule {rule['id']} v{rule['version']}: invalid JSON ({exc}).")
            continue
        then = d.get("then", {})
        if not any(then.get(k) for k in ("risk_ids", "procedure_ids", "control_ids", "assertion_ids")):
            errors.append(f"Rule {rule['id']} v{rule['version']}: no outcomes defined.")
        for key, table in (("risk_ids", "risk_events"), ("procedure_ids", "audit_procedures"),
                           ("control_ids", "controls"), ("assertion_ids", "assertions")):
            for rid in then.get(key, []):
                exists = conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (rid,)).fetchone()
                if not exists:
                    errors.append(f"Rule {rule['id']} v{rule['version']}: {key} references unknown id {rid}.")
        when = d.get("when", {})
        for cond in when.get("all", []) + when.get("any", []) + when.get("exclude", []):
            if cond.get("type") == "factor_selected":
                exists = conn.execute("SELECT 1 FROM business_factors WHERE id = ?", (cond.get("factor_id"),)).fetchone()
                if not exists:
                    errors.append(f"Rule {rule['id']} v{rule['version']}: condition references unknown factor {cond.get('factor_id')}.")

    return errors


if __name__ == "__main__":
    conn = init_db()
    errs = validate_db(conn)
    print("validation errors:", errs if errs else "none")
    conn.close()
