"""
Audit Risk and Evidence Library - offline Streamlit interface.

Run:  streamlit run app.py
Works fully offline after installation. No AI, no network calls.
"""

import io
import sqlite3
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import connect  # noqa: E402
from engine import RuleEngine  # noqa: E402
from export import export_csv, export_excel  # noqa: E402

st.set_page_config(page_title="Audit Risk & Evidence Library", layout="wide")

JUDGMENT_NOTICE = (
    "This library lists *possible* risks and *suggested* procedures. A risk factor does not "
    "prove a misstatement exists. A failed control test does not prove the financial statements "
    "are misstated, and a passed control test does not prove the balance is correct. "
    "Apply professional judgment throughout."
)


@st.cache_resource
def get_engine():
    return RuleEngine()


def factor_options(eng):
    rows = eng.query(
        "SELECT f.id, f.name, c.name AS cycle FROM business_factors f"
        " JOIN business_cycles c ON c.id = f.cycle_id"
        " WHERE f.review_status = 'Verified' ORDER BY c.name, f.id"
    )
    return {f"{r['cycle']} - {r['name']}": r["id"] for r in rows}


def render_risk(risk):
    st.subheader(f"{risk['id']}: {risk['title']}")
    if risk.get("significance") == "Significant risk":
        st.error("SIGNIFICANT RISK - requires special audit consideration: obtain a heightened "
                 "understanding, evaluate control design, and perform substantive procedures "
                 "specifically responsive to the risk.")
    st.caption(f"Triggered by rule(s): {', '.join(risk['triggered_by_rules'])} | Cycle: {risk['cycle_id']}")
    st.markdown(f"**Description.** {risk['description']}")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Why the risk exists**")
        st.write(risk["causes"] or "-")
        st.markdown("**Potential misstatement**")
        st.write(risk["potential_consequences"] or "-")
        st.markdown("**Relevant assertions** (each with its own rationale)")
        for a in risk["assertions"]:
            st.markdown(f"- **{a['id']} {a['name']}** - {a['why_relevant']}"
                        + (f" *({a['conditions']})*" if a["conditions"] else ""))
    with col2:
        st.markdown("**Relevant controls**")
        for c in risk["controls"]:
            st.markdown(f"- {c['description']} *({c['preventive_detective'] or '?'}; "
                        f"{c['manual_automated'] or '?'})*")
            if c["limitations"]:
                st.caption(f"Limitation: {c['limitations']}")
        st.markdown("**Inherent risk considerations**")
        st.write(risk["inherent_risk_notes"] or "-")
        st.caption(f"Source: {risk['source_reference'] or 'not recorded'}")

    st.markdown("### Suggested audit procedures")
    for p in risk["procedures"]:
        fraud_tag = " [FRAUD RESPONSE]" if p.get("fraud_focus") else ""
        ext_tag = " [EXTENDED]" if p.get("response_level") == "Extended" else ""
        with st.expander(f"{p['id']} - {p['title']} ({p['procedure_type']}, {p['test_type']}){fraud_tag}{ext_tag}"):
            st.markdown(f"**Objective.** {p['objective']}")
            st.markdown("**Steps**")
            st.write(p["steps"])
            if p["population"]:
                st.markdown(f"**Population:** {p['population']}")
            if p["sampling_notes"]:
                st.markdown(f"**Sampling:** {p['sampling_notes']}")
            st.markdown(f"**Assertions tested:** {', '.join(p['assertions'])}")
            st.markdown("**Required evidence**")
            for e in p["evidence"]:
                st.markdown(f"- **{e['name']}** ({e['source'] or 'n/a'}): {e['description']}")
                st.caption(f"Reliability: {e['reliability_notes']}")
                if e["limitations"]:
                    st.caption(f"Limitation: {e['limitations']}")
                if e["contradictory_evidence"]:
                    st.caption(f"Contradictory evidence to watch for: {e['contradictory_evidence']}")
            st.success(f"**Expected result.** {p['expected_result']}")
            st.warning(f"**Exception criteria.** {p['exception_criteria']}")
            st.info(f"**Follow-up if the test fails.** {p['follow_up']}")
            st.caption(f"Why this procedure: {p['link_reason'] or '-'} | "
                       f"Rule(s): {', '.join(p['triggered_by_rules'])}")


def page_assess():
    st.header("Interactive risk assessment")
    st.info(JUDGMENT_NOTICE)
    eng = get_engine()
    industries = {i["name"]: i["id"] for i in eng.industries()}
    sel_industries = st.multiselect(
        "Client industry (adds industry-specific inherent risk factors):",
        list(industries.keys()),
    )
    industry_ids = [industries[n] for n in sel_industries]
    options = factor_options(eng)
    selected_labels = st.multiselect(
        "Select the business conditions (factors) observed at the client:",
        list(options.keys()),
    )
    if st.button("Generate risk and testing plan", type="primary"):
        factor_ids = [options[l] for l in selected_labels]
        plan = eng.assess(factor_ids, industry_ids=industry_ids)
        st.session_state["plan"] = plan
    plan = st.session_state.get("plan")
    if not plan:
        return
    c = plan["counts"]
    msg = (f"Rules triggered: {c['rules_triggered']} | Risks: {c['risks']} | "
           f"Procedures: {c['procedures']} | Controls: {c['controls']}")
    if c.get("significant_risks"):
        msg += f" | Significant risks: {c['significant_risks']}"
    if c.get("fraud_responses"):
        msg += f" | Fraud responses: {c['fraud_responses']}"
    st.success(msg)
    if plan.get("industry_added_factors"):
        with st.expander("Industry factors added automatically"):
            for f in plan["industry_added_factors"]:
                st.markdown(f"- `{f['factor_id']}` (from industry `{f['industry_id']}`)")
    with st.expander("Rules applied (with version and rationale)"):
        for t in plan["triggered_rules"]:
            st.markdown(f"**{t['rule_id']}** v{t['version']} - {t['rule_name']} "
                        f"(priority {t['priority']}, effective {t['effective_date']}, status {t['review_status']})")
            st.caption(t["rationale"] or "")
            st.caption(f"Source: {t['source_reference'] or 'not recorded'}")
    if plan["missing_information"]:
        with st.expander("Information still required", expanded=True):
            for m in plan["missing_information"]:
                st.markdown(f"- {m}")
    if plan.get("fraud_responses"):
        with st.expander("Fraud risk responses (perform in addition to standard procedures)", expanded=True):
            for p in plan["fraud_responses"]:
                st.markdown(f"- **{p['id']}** - {p['title']} "
                            f"(addresses: {', '.join(p['risk_ids'])})")
    for risk in plan["risks"]:
        with st.container(border=True):
            render_risk(risk)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Download CSV workpaper"):
            buf = io.StringIO()
            import tempfile
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
            export_csv(plan, tmp.name)
            st.session_state["csv_path"] = tmp.name
            st.download_button("Save workpaper.csv", data=open(tmp.name, "rb").read(),
                               file_name="audit_workpaper.csv", mime="text/csv")
    with col2:
        if st.button("Download Excel workpaper"):
            import tempfile
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
            export_excel(plan, tmp.name)
            st.download_button("Save workpaper.xlsx", data=open(tmp.name, "rb").read(),
                               file_name="audit_workpaper.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def page_search():
    st.header("Search the library")
    eng = get_engine()
    query = st.text_input("Search factors, risks, procedures, evidence, controls",
                          placeholder='e.g. "unsecured warehouse", "unrecorded liabilities", "completeness"')
    cycle_filter = st.selectbox("Filter by business cycle", ["All"] + [
        r["name"] for r in eng.query("SELECT name FROM business_cycles ORDER BY name")])
    if query:
        results = eng.search(query)
        st.write(f"{len(results)} result(s)")
        for r in results:
            with st.expander(f"[{r['kind']}] {r['label']}"):
                st.write(f"ID: `{r['id']}` - open the Library browser or Risk assessment to see full detail.")


def page_library():
    st.header("Library browser")
    eng = get_engine()
    cycles = eng.query("SELECT id, name FROM business_cycles ORDER BY name")
    cycle = st.selectbox("Business cycle", [c["name"] for c in cycles])
    cid = next(c["id"] for c in cycles if c["name"] == cycle)
    factors = eng.query(
        "SELECT id, name FROM business_factors WHERE cycle_id = ? AND review_status='Verified' ORDER BY id",
        (cid,))
    if not factors:
        st.info("No verified content for this cycle yet.")
        return
    fsel = st.selectbox("Business factor", [f"{f['id']}: {f['name']}" for f in factors])
    fid = fsel.split(":")[0]
    plan = eng.assess([fid])
    if not plan["risks"]:
        st.info("No verified risks mapped to this factor yet.")
        return
    for risk in plan["risks"]:
        with st.container(border=True):
            render_risk(risk)


def page_about():
    st.header("About this library")
    st.markdown("""
**Methodology.** Every recommendation is produced by deterministic rules evaluated against a
versioned SQLite database - no AI, no cloud, no probabilistic inference. The same inputs and
database version always produce the same results. Rules are editable JSON files in `data/rules/`;
the engine evaluates the database copy.

**Concepts are not interchangeable.** The library distinguishes:
- a *risk factor* (a condition that may increase risk),
- an *identified risk* (what could go wrong),
- a *potential misstatement* (the financial statement effect if the risk materialised),
- a *control deficiency* (a missing or ineffective control),
- an *exception* (a test result outside expectations),
- a *confirmed misstatement* (a quantified error),
- a *suspected fraud indicator* (a red flag requiring investigation, never an automatic conclusion).

**References.** The library deliberately cites NO ISA/IFRS paragraph numbers, because unverifiable
citations are worse than none. See `docs/REFERENCES.md` for the verified/unverified register.
All seeded content is marked with its review status; only `Verified` records drive the engine.
""")
    st.info(JUDGMENT_NOTICE)


def page_industry():
    st.header("Industry inherent risks")
    st.info("Select an industry to see the inherent risk factors characteristic of it. "
            "Industry factors can be added to a risk assessment with one click. " + JUDGMENT_NOTICE)
    eng = get_engine()
    industries = {i["name"]: i for i in eng.industries()}
    if not industries:
        st.info("No industries in the library yet.")
        return
    sel = st.selectbox("Industry", list(industries.keys()))
    ind = industries[sel]
    st.markdown(f"**{ind['name']}** - {ind['description']}")
    factors = eng.industry_factors(ind["id"])
    if not factors:
        st.info("No verified industry factors for this industry yet.")
        return
    for f in factors:
        with st.expander(f"{f['id']}: {f['name']}"):
            st.write(f["description"])
            if f.get("industry_explanation"):
                st.caption(f"Why characteristic of {ind['name']}: {f['industry_explanation']}")
            if f.get("warning_signs"):
                st.markdown("**Warning signs**")
                st.write(f["warning_signs"])
    if st.button(f"Run risk assessment with all {ind['name']} factors", type="primary"):
        plan = eng.assess([], industry_ids=[ind["id"]])
        st.session_state["plan"] = plan
        st.success(f"Assessment generated: {plan['counts']['risks']} risk(s), "
                   f"{plan['counts']['procedures']} procedure(s). Open 'Risk assessment' to view it.")


def page_fraud():
    st.header("Fraud risk indicators and responses")
    st.warning("Indicators are red flags, not proof. A fraud indicator never establishes that fraud "
               "has occurred - it directs additional, specifically responsive procedures and "
               "professional scepticism.")
    eng = get_engine()
    indicators = eng.fraud_indicators()
    if not indicators:
        st.info("No fraud indicators in the library yet.")
        return
    for fi in indicators:
        with st.expander(f"{fi['id']}: {fi['name']} [{fi.get('fraud_triangle') or 'n/a'}]"):
            st.write(fi["description"])
            if fi.get("warning_signs"):
                st.markdown("**Observable red flags**")
                st.write(fi["warning_signs"])
            if fi.get("conditions_relevant"):
                st.caption(f"Relevant when: {fi['conditions_relevant']}")
    sel = st.selectbox("Assess fraud indicators observed:",
                       ["(select)"] + [f"{f['id']}: {f['name']}" for f in indicators])
    if sel != "(select)" and st.button("Generate fraud risk plan", type="primary"):
        fid = sel.split(":")[0]
        plan = eng.assess([fid])
        st.session_state["plan"] = plan
        c = plan["counts"]
        st.success(f"Risks: {c['risks']} (significant: {c.get('significant_risks', 0)}) | "
                   f"Fraud responses: {c.get('fraud_responses', 0)}")
        for risk in plan["risks"]:
            with st.container(border=True):
                render_risk(risk)


def page_analytical():
    st.header("Analytical procedures by area")
    st.info("Substantive analytical procedures: build an independent expectation from plausible "
            "relationships and investigate differences above the threshold. Analytical procedures "
            "alone are generally weaker for significant risks - combine with tests of details.")
    eng = get_engine()
    areas = eng.analytical_areas()
    if not areas:
        st.info("No analytical procedures in the library yet.")
        return
    area = st.selectbox("Audit area", areas)
    for ap in eng.analytical_procedures(area):
        with st.expander(f"{ap['id']}: {ap['title']}"):
            st.markdown("**How to perform**")
            st.write(ap["detail"])
            if ap.get("expected_relationship"):
                st.markdown("**Expected (plausible) relationship**")
                st.write(ap["expected_relationship"])
            if ap.get("investigation_threshold"):
                st.warning(f"Investigate when: {ap['investigation_threshold']}")
            if ap.get("follow_up"):
                st.info(f"Follow-up: {ap['follow_up']}")
            st.caption(f"Source: {ap.get('source_reference') or 'not recorded'}")


def page_controls():
    st.header("Control explorer")
    st.info("Two directions: pick a control objective to see which controls achieve it, "
            "or pick a control to see which objectives it serves.")
    eng = get_engine()
    tab1, tab2 = st.tabs(["Objective -> Controls", "Control -> Objectives"])
    with tab1:
        objectives = {f"{o['id']}: {o['objective']}": o["id"] for o in eng.control_objectives()}
        if not objectives:
            st.info("No control objectives in the library yet.")
        else:
            sel = st.selectbox("Control objective", list(objectives.keys()))
            oid = objectives[sel]
            obj = next(o for o in eng.control_objectives() if o["id"] == oid)
            if obj.get("description"):
                st.write(obj["description"])
            for c in eng.controls_for_objective(oid):
                with st.expander(f"{c['id']}: {c['description'][:90]}..."):
                    st.write(c["description"])
                    st.caption(f"How it achieves the objective: {c.get('link_explanation') or '-'}")
                    st.markdown(f"*Type:* {c.get('preventive_detective') or '?'} / "
                                f"{c.get('manual_automated') or '?'} | "
                                f"*Frequency:* {c.get('frequency') or '?'} | "
                                f"*Owner:* {c.get('responsible_role') or '?'}")
                    if c.get("limitations"):
                        st.caption(f"Limitation: {c['limitations']}")
    with tab2:
        controls = {f"{c['id']}: {c['description'][:80]}": c["id"] for c in eng.verified_controls()}
        sel = st.selectbox("Control", list(controls.keys()))
        cid = controls[sel]
        objs = eng.objectives_for_control(cid)
        if not objs:
            st.info("No objectives linked to this control yet.")
        for o in objs:
            st.markdown(f"- **{o['id']}**: {o['objective']}")
            if o.get("link_explanation"):
                st.caption(o["link_explanation"])


def page_backup():
    st.header("Backup")
    if st.button("Create database backup now"):
        import shutil, time
        src = Path("library.db")
        dest_dir = Path("backups")
        dest_dir.mkdir(exist_ok=True)
        dest = dest_dir / f"library-{time.strftime('%Y%m%d-%H%M%S')}.db"
        shutil.copy2(src, dest)
        st.success(f"Backup created: {dest}")
    st.write("Existing backups:")
    for p in sorted(Path("backups").glob("*.db")):
        st.caption(str(p))


nav = st.sidebar.radio("Navigate", ["Risk assessment", "Industry risks", "Fraud indicators",
                             "Analytical procedures", "Control explorer",
                             "Search", "Library browser", "Backup", "About"])
st.sidebar.caption("Audit Risk & Evidence Library - offline, deterministic, no AI.")
st.sidebar.caption("Build v1.2 - if you don't see this line, you're running an older version.")
if nav == "Risk assessment":
    page_assess()
elif nav == "Industry risks":
    page_industry()
elif nav == "Fraud indicators":
    page_fraud()
elif nav == "Analytical procedures":
    page_analytical()
elif nav == "Control explorer":
    page_controls()
elif nav == "Search":
    page_search()
elif nav == "Library browser":
    page_library()
elif nav == "Backup":
    page_backup()
else:
    page_about()
