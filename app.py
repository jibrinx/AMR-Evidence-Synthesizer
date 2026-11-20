"""Streamlit entry point: streamlit run app.py."""

import os
from dataclasses import asdict
from pathlib import Path

import streamlit as st

from amr_evidence.agent import Agent, CompatibleProvider, Limits
from amr_evidence.config import Settings
from amr_evidence.export import export_records, to_csv, to_json
from amr_evidence.extraction import extract_rules
from amr_evidence.intake import read_upload
from amr_evidence.models import DOMAINS, DomainAssessment, Estimate, Review, Study
from amr_evidence.pubmed import DEFAULT_QUERY, PubMed, import_article
from amr_evidence.store import Store

st.set_page_config(page_title="AMR Evidence Synthesizer", page_icon="A", layout="wide")

TEXT_FIELDS = {
    "organism_raw": "Organism (as reported)",
    "organism_normalized": "Organism (normalized; optional)",
    "antibiotic_raw": "Antibiotic (as reported)",
    "antibiotic_normalized": "Antibiotic (normalized; optional)",
    "sampling_unit": "Sampling unit (isolates / patients / specimens)",
    "stratum": "Stratum / subgroup",
    "country": "Country (as reported)",
    "location": "Nigerian location",
    "setting": "Study setting",
    "collection_dates": "Collection dates (not publication year)",
    "specimen": "Specimen",
    "ast_method": "AST method",
    "breakpoint_standard": "Breakpoint standard",
    "breakpoint_version": "Breakpoint version / year",
    "reported_ci": "Reported confidence interval (optional)",
    "notes": "Reviewer / extraction notes",
}
OUTCOMES = ["unknown", "resistant", "non_susceptible", "intermediate"]
SECTORS = ["unknown", "human", "animal", "environmental", "mixed"]
JUDGMENTS = ["not_assessed", "low_concern", "some_concern", "high_concern", "unclear"]


def settings():
    # Root-level Streamlit secrets support hosting without putting keys in Git.
    try:
        for key in (
            "AMR_DB_PATH",
            "AMR_READ_ONLY",
            "AMR_AI_ENABLED",
            "AMR_AI_BASE_URL",
            "AMR_AI_MODEL",
            "AMR_AI_API_KEY",
            "AMR_ALLOW_LOCAL_HTTP",
            "NCBI_EMAIL",
        ):
            if key in st.secrets:
                os.environ.setdefault(key, str(st.secrets[key]))
    except FileNotFoundError:
        pass
    return Settings.from_env()


def source_label(source):
    return f"#{source['id']} · {source['study']['title'][:100]} · {source['kind']}"


def discover(store, config):
    st.header("Discover studies")
    st.caption("PubMed results are screening candidates, not confirmed Nigerian AMR evidence.")
    with st.form("pubmed_search"):
        query = st.text_area("PubMed query", DEFAULT_QUERY)
        col1, col2, col3 = st.columns(3)
        lower = col1.number_input("From publication year", 1800, 2200, 2000)
        upper = col2.number_input("Through publication year", 1800, 2200, 2026)
        count = col3.number_input("Maximum results", 1, 100, 20)
        search = st.form_submit_button("Search PubMed")
    if search:
        with st.spinner("Searching PubMed"):
            try:
                st.session_state["search_results"] = PubMed(config.ncbi_email).search(
                    query, int(count), int(lower), int(upper)
                )
            except ValueError as exc:
                st.error(str(exc))
    results = st.session_state.get("search_results", [])
    if search and not results:
        st.info("No results to display. Try a broader query.")
    for i, article in enumerate(results):
        study = article["study"]
        with st.expander(f"{study['title']} ({study['year'] or 'year not reported'})"):
            st.write(f"PMID: {study['pmid']} | DOI: {study['doi'] or 'not reported'}")
            st.text(article["abstract"] or "No abstract available.")
            if st.button(
                "Import abstract",
                key=f"import_{i}",
                disabled=config.read_only or not article["abstract"],
            ):
                try:
                    source_id = import_article(store, article)
                    st.success(f"Source #{source_id} imported. Eligibility is not confirmed.")
                except ValueError as exc:
                    st.error(str(exc))


def upload(store, config):
    st.header("Upload a publication")
    st.caption("Text-based PDF or UTF-8 TXT · 20 MB · 100 PDF pages. Originals are not retained.")
    if config.read_only:
        st.info("Uploads are disabled in public read-only mode.")
        return
    with st.form("upload"):
        title = st.text_input("Publication title")
        c1, c2, c3 = st.columns(3)
        pmid = c1.text_input("PMID (optional)")
        doi = c2.text_input("DOI (optional)")
        year = c3.text_input("Publication year (optional)")
        file = st.file_uploader("Authorized published document", type=["pdf", "txt"])
        authorized = st.checkbox(
            "I am authorized to process this published material; it contains no identifiable patient data."
        )
        submitted = st.form_submit_button("Import document")
    if submitted:
        try:
            if not file or not authorized:
                raise ValueError("Select a document and confirm authorization.")
            pages, kind = read_upload(file.name, file.getvalue())
            study = Study(
                title=title, pmid=pmid or None, doi=doi or None, year=int(year) if year else None
            )
            study_id = store.add_study(study)
            source_id = store.add_source(study_id, Path(file.name).name, pages, kind)
            st.success(f"Source #{source_id} imported with {len(pages)} page(s).")
        except (ValueError, PermissionError) as exc:
            st.error(str(exc))


def agent_workspace(store, config):
    st.header("Supervised agent")
    st.caption(
        "Search → inspect passages → propose pending estimates. Only a human can approve evidence."
    )
    st.write("Model destination:", config.public_destination())
    st.write("Configured model:", config.ai_model or "not configured")
    with st.expander("Run limits and data handling"):
        st.json(asdict(Limits()))
        st.write(
            "The configured provider receives the research goal, tool schemas, selected passages, "
            "discovered publication metadata, and submitted candidates within this run. "
            "No arbitrary browsing, code execution, or approval tool is available. "
            "Limits are not an exact monetary cap; use provider-side spending limits. "
            "Article text is untrusted, and AI field mappings still require human verification."
        )
    if config.read_only:
        st.info("AI execution is disabled in public read-only mode.")
    sources = store.sources()
    lookup = {s["id"]: s for s in sources}
    with st.form("agent_run"):
        goal = st.text_area(
            "Research goal",
            "Extract explicitly reported Nigerian AMR estimates from the selected sources.",
        )
        selected = st.multiselect(
            "Sources available to this run (maximum 5)",
            list(lookup),
            format_func=lambda sid: source_label(lookup[sid]),
        )
        discovery = st.checkbox(
            "Permit bounded PubMed discovery and abstract import during this run"
        )
        consent = st.checkbox(
            "I authorize sending in-scope published text to the displayed model destination. "
            "I understand outputs are unvalidated candidates and provider charges may apply."
        )
        run = st.form_submit_button("Run agent", disabled=config.read_only or not config.ai_enabled)
    if run:
        try:
            config.validate_ai()
            if not selected and not discovery:
                raise ValueError("Select at least one source or enable discovery.")
            with st.spinner("Agent is inspecting evidence; partial results will remain pending"):
                outcome = Agent(
                    store,
                    CompatibleProvider(config),
                    config.ai_model,
                    config.public_destination(),
                    PubMed(config.ncbi_email, timeout=15),
                ).run(goal, selected, discovery, consent)
            st.session_state["last_run"] = outcome["id"]
        except (ValueError, PermissionError) as exc:
            st.error(str(exc))
    if not config.ai_enabled:
        st.info(
            "AI is not enabled by the operator. Manual entry and rules remain available in Review."
        )
    runs = store.runs()
    if runs:
        run_ids = [r["id"] for r in runs]
        chosen = st.selectbox("Run history", run_ids)
        value = next(r for r in runs if r["id"] == chosen)
        st.write(
            f"Status: {value['status']} · Pending/existing candidates: {value['candidate_ids']}"
        )
        st.text("Agent-generated run message (not validated): " + value["message"])
        st.json({k: v for k, v in value.items() if k not in {"message", "goal"}})
        with st.expander("Operational tool activity"):
            st.json(store.events(chosen))


def estimate_form(store, source, existing=None):
    row_id = existing["id"] if existing else "new"
    data = existing["data"] if existing else {}
    old_review = existing["review"] or {} if existing else {}
    st.subheader(f"Edit estimate #{row_id}" if existing else "Manual candidate")
    with st.form(f"estimate_{source['id']}_{row_id}"):
        page = st.number_input(
            "Evidence page (abstracts use page 1)", 1, len(source["pages"]), data.get("page", 1)
        )
        quote = st.text_area(
            "Exact evidence quote (copy from source text)", data.get("quote", ""), height=130
        )
        values = {}
        columns = st.columns(2)
        for index, (key, label) in enumerate(TEXT_FIELDS.items()):
            values[key] = columns[index % 2].text_input(label, data.get(key) or "") or None
        c1, c2, c3 = st.columns(3)
        n = c1.text_input(
            "Resistant / outcome count (optional)",
            str(data.get("numerator")) if data.get("numerator") is not None else "",
        )
        d = c2.text_input(
            "Tested denominator (optional)",
            str(data.get("denominator")) if data.get("denominator") is not None else "",
        )
        pct = c3.text_input("Reported percentage, without %", data.get("reported_percentage") or "")
        outcome = st.selectbox(
            "Outcome definition", OUTCOMES, index=OUTCOMES.index(data.get("outcome", "unknown"))
        )
        sector = st.selectbox("Sector", SECTORS, index=SECTORS.index(data.get("sector", "unknown")))
        mapping_uncertain = st.checkbox(
            "Organism–antibiotic–stratum mapping is unresolved",
            value=data.get("mapping_uncertain", False),
        )
        if existing:
            st.markdown("#### Human review")
            reviewer = st.text_input("Reviewer identity", old_review.get("reviewer", ""))
            statuses = ["pending", "approved", "rejected"]
            status = st.selectbox(
                "Review decision", statuses, index=statuses.index(existing["status"])
            )
            eligible = st.checkbox(
                "I verified that this estimate concerns Nigerian samples",
                value=old_review.get("nigeria_eligible", False),
            )
            rationale = st.text_area("Decision rationale", old_review.get("rationale", ""))
            st.caption(
                "Tailored checklist; not a validated risk-of-bias score. Leave unassessed domains explicit."
            )
            assessments = {}
            for domain in DOMAINS:
                prior = old_review.get("assessments", {}).get(domain, {})
                left, right = st.columns([1, 2])
                judgment = left.selectbox(
                    domain.replace("_", " ").title(),
                    JUDGMENTS,
                    index=JUDGMENTS.index(prior.get("judgment", "not_assessed")),
                )
                explanation = right.text_input(
                    f"{domain.replace('_', ' ').title()} rationale", prior.get("rationale", "")
                )
                assessments[domain] = {"judgment": judgment, "rationale": explanation}
        saved = st.form_submit_button("Save review" if existing else "Create pending candidate")
    if saved:
        try:
            estimate = Estimate(
                source_id=source["id"],
                page=int(page),
                quote=quote,
                **values,
                numerator=int(n) if n.strip() else None,
                denominator=int(d) if d.strip() else None,
                reported_percentage=pct or None,
                outcome=outcome,
                mapping_uncertain=mapping_uncertain,
                sector=sector,
                ai_observations=data.get("ai_observations"),
            )
            if existing:
                review = Review(
                    reviewer=reviewer,
                    status=status,
                    nigeria_eligible=eligible,
                    rationale=rationale,
                    assessments={k: DomainAssessment(**v) for k, v in assessments.items()},
                )
                store.review(existing["id"], estimate, review, existing["updated"])
                st.success(f"Estimate #{existing['id']} saved as {status}.")
            else:
                estimate_id = store.add_estimate(estimate)
                st.success(f"Pending candidate #{estimate_id} created. Open it below to review.")
            st.write(
                "Remaining flags:",
                estimate.flags() or "None automatically detected (not proof of quality).",
            )
        except (ValueError, PermissionError) as exc:
            st.error(str(exc))


def review_workspace(store, config):
    st.header("Review evidence")
    sources = store.sources()
    if not sources:
        st.info("Import a PubMed abstract or upload a document first.")
        return
    lookup = {s["id"]: s for s in sources}
    sid = st.selectbox("Source", list(lookup), format_func=lambda i: source_label(lookup[i]))
    source = lookup[sid]
    page = st.selectbox("Inspect source page", list(range(1, len(source["pages"]) + 1)))
    st.caption(f"Source hash: {source['content_hash']} · copy quotes literally.")
    st.code(source["pages"][page - 1], language=None, wrap_lines=True)
    if config.read_only:
        st.info("Editing and rule extraction are disabled in public read-only mode.")
        return
    if st.button("Find narrow rule-based candidates"):
        found = extract_rules(sid, source["pages"])
        ids = [store.add_estimate(candidate, "rules") for candidate in found]
        st.info(
            f"{len(set(ids))} candidate record(s) matched narrow supported patterns. Unsupported text needs manual or AI-assisted entry."
        )
    with st.expander("Add a manual candidate"):
        estimate_form(store, source)
    rows = [r for r in store.estimates() if r["source_id"] == sid]
    if rows:
        ids = [r["id"] for r in rows]
        selected = st.selectbox("Candidate to review", ids)
        row = store.estimate(selected)
        st.write("Flags:", row["flags"])
        if row["data"].get("ai_observations"):
            st.text("Unvalidated AI observations: " + row["data"]["ai_observations"])
        estimate_form(store, source, row)
        with st.expander("Estimate audit history"):
            st.json(store.audit(selected))
    else:
        st.info("No candidates for this source yet.")


def database(store):
    st.header("Evidence database")
    statuses = st.multiselect(
        "Review statuses to display/export",
        ["approved", "pending", "rejected"],
        default=["approved"],
    )
    if not statuses:
        st.info("Select at least one review status.")
        return
    records = export_records(store, statuses)
    col1, col2, col3 = st.columns(3)
    organism = col1.text_input("Organism contains")
    antibiotic = col2.text_input("Antibiotic contains")
    sector = col3.selectbox("Sector filter", ["all", *SECTORS])
    records = [
        r
        for r in records
        if organism.lower() in (r["organism_raw"] or "").lower()
        and antibiotic.lower() in (r["antibiotic_raw"] or "").lower()
        and (sector == "all" or r["sector"] == sector)
    ]
    st.metric("Matching estimates", len(records))
    if records:
        st.dataframe(
            [
                {
                    "ID": r["estimate_id"],
                    "organism": r["organism_raw"],
                    "antibiotic": r["antibiotic_raw"],
                    "outcome": r["outcome"],
                    "n": r["numerator"],
                    "tested": r["denominator"],
                    "% reported": r["reported_percentage"],
                    "status": r["review_status"],
                    "source": r["source_name"],
                    "quality domains assessed": sum(
                        a["judgment"] != "not_assessed"
                        for a in (r["review"] or {}).get("assessments", {}).values()
                    ),
                }
                for r in records
            ],
            hide_index=True,
            use_container_width=True,
        )
    left, right = st.columns(2)
    left.download_button("Download CSV", to_csv(records), "amr_estimates.csv", "text/csv")
    right.download_button(
        "Download JSON", to_json(records), "amr_estimates.json", "application/json"
    )
    st.caption(
        "Exports match the displayed filters. JSON retains nulls and nested assessments; CSV escapes spreadsheet formula prefixes."
    )


def guide():
    st.header("Guide and limitations")
    st.markdown("""
1. **Discover or upload** authorized published text. Confirm citation metadata.
2. **Agent or rules/manual** creates pending estimates. The agent may search and inspect sources,
   but cannot approve evidence. Review the run's completion state and missing fields.
3. **Verify the source** for every organism–antibiotic–outcome–stratum mapping, count, percentage,
   denominator, sampling unit, and collection date. A matching quote is traceability, not correctness.
4. **Assess quality** using the transparent domain checklist and explanations. This is not a
   validated risk-of-bias scale. Unassessed domains stay visible.
5. **Approve or reject** as a named reviewer. Nigeria eligibility requires a human confirmation.
6. **Export** approved estimates by default, with provenance and review history available.

**Scientific boundaries:** resistant is not the same as non-susceptible; isolate estimates are
not patient prevalence. Never infer tested denominators from sample totals. Missing data remain
missing. Source text may not preserve table layout; OCR and complex table interpretation are
not supported. The application does not pool estimates or provide clinical recommendations.

**Deployment:** the default is public read-only mode. A private operator enables editing and,
optionally, AI. Use hosting-level access control and a durable SQLite volume. There is no built-in
multi-user authentication. Operational audit records are not tamper-proof. No pre-populated
Nigerian evidence corpus is included. See README and docs for installation, privacy, and limitations.
""")


def main():
    config = settings()
    st.title("AMR Evidence Synthesizer")
    st.caption(
        "NIGERIA · Published evidence · Source-grounded extraction · Human-reviewed decisions"
    )
    st.sidebar.title("Research workspace")
    if config.read_only:
        st.sidebar.info("Public read-only mode")
    else:
        st.sidebar.warning("Private review mode · host access control required")
    area = st.sidebar.radio(
        "Navigate", ["Discover", "Upload", "Agent", "Review", "Database", "Guide"]
    )
    st.sidebar.caption("v0.1.0 · Research software, not clinical advice")
    store = Store(config.db_path, config.read_only)
    try:
        if area == "Discover":
            discover(store, config)
        elif area == "Upload":
            upload(store, config)
        elif area == "Agent":
            agent_workspace(store, config)
        elif area == "Review":
            review_workspace(store, config)
        elif area == "Database":
            database(store)
        else:
            guide()
    finally:
        store.close()


if __name__ == "__main__":
    main()
