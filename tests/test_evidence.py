import json
import sqlite3

import pytest
from pydantic import ValidationError

from amr_evidence.export import export_records, safe_cell, to_csv, to_json
from amr_evidence.models import DomainAssessment, Estimate, Review, Study
from amr_evidence.store import Store


@pytest.mark.parametrize(
    "values",
    [
        {"numerator": -1},
        {"denominator": 0},
        {"numerator": 11, "denominator": 10},
        {"numerator": 3.5},
        {"numerator": True},
        {"reported_percentage": "101"},
        {"reported_percentage": "NaN"},
        {"reported_percentage": "30%"},
        {"reported_percentage": "1e2"},
        {"outcome": "susceptible"},
        {"page": 0},
        {"status": "approved"},
        {"nigeria_eligible": True},
    ],
)
def test_invalid_estimates(candidate, values):
    with pytest.raises(ValidationError):
        Estimate.model_validate({**candidate.model_dump(), **values})


def test_missing_values_remain_missing(source):
    e = Estimate(source_id=source, page=1, quote="x", reported_percentage="33.3")
    assert e.numerator is None and e.denominator is None
    assert "missing_denominator" in e.flags() and e.outcome == "unknown"


@pytest.mark.parametrize(
    "n,d,pct,inconsistent",
    [
        (1, 3, "33.3", False),
        (1, 3, "33", False),
        (1, 3, "34", True),
        (0, 10, "0", False),
        (10, 10, "100.0", False),
        (3, 10, "40", True),
    ],
)
def test_rounding(candidate, n, d, pct, inconsistent):
    e = Estimate.model_validate(
        {
            **candidate.model_dump(),
            "numerator": n,
            "denominator": d,
            "reported_percentage": pct,
        }
    )
    assert ("count_percentage_inconsistency" in e.flags()) == inconsistent


def test_distinct_outcomes(candidate):
    assert (
        Estimate(**{**candidate.model_dump(), "outcome": "non_susceptible"}).outcome
        != candidate.outcome
    )


def test_quality_rationale():
    with pytest.raises(ValidationError):
        DomainAssessment(judgment="high_concern")
    with pytest.raises(ValidationError):
        Review(reviewer="test", assessments={"made_up": {"judgment": "not_assessed"}})
    assert DomainAssessment(judgment="not_assessed").rationale == ""


def test_study_identifiers():
    s = Study(title="Example", doi="https://doi.org/10.1000/TEST")
    assert s.doi == "10.1000/test"
    for values in ({"doi": "invalid"}, {"pmid": "../file"}, {"title": ""}):
        with pytest.raises(ValidationError):
            Study.model_validate({"title": "test", **values})


def test_study_dedup_and_conflict(store):
    first = store.add_study(Study(title="first", pmid="1", doi="10.1000/a"))
    assert store.add_study(Study(title="renamed", pmid="1")) == first
    store.add_study(Study(title="second", pmid="2", doi="10.1000/b"))
    with pytest.raises(ValueError, match="conflict"):
        store.add_study(Study(title="conflict", pmid="1", doi="10.1000/b"))


def test_document_duplicate_and_hash(store, source):
    s = store.source(source)
    assert len(s["content_hash"]) == 64
    assert store.add_source(s["study_id"], "newname", s["pages"]) == source
    another = store.add_study(Study(title="another"))
    with pytest.raises(ValueError, match="different citation"):
        store.add_source(another, "same", s["pages"])


def test_evidence_and_duplicates(store, candidate):
    first = store.add_estimate(candidate)
    assert first == store.add_estimate(candidate, "agent")
    assert store.estimate(first)["status"] == "pending"
    for values in ({"quote": "not in document"}, {"page": 2}):
        with pytest.raises(ValueError):
            store.add_estimate(Estimate(**{**candidate.model_dump(), **values}))
    # Different strata must not collapse.
    other = store.add_estimate(Estimate(**{**candidate.model_dump(), "stratum": "different"}))
    assert other != first


def test_review_workflow_export_and_audit(store, candidate):
    eid = store.add_estimate(candidate)
    assert export_records(store) == []
    review = Review(reviewer="test reviewer", status="approved", nigeria_eligible=True)
    store.review(eid, candidate, review)
    rows = export_records(store)
    assert rows[0]["review_status"] == "approved"
    assert rows[0]["review"]["reviewer"] == "test reviewer"
    assert rows[0]["reported_percentage"] == "30"
    assert rows[0]["source_sha256"] == store.source(candidate.source_id)["content_hash"]
    assert json.loads(to_json(rows))["estimates"][0]["estimate_id"] == eid
    assert "reported_percentage" in to_csv(rows)
    assert len(store.audit(eid)) == 2
    with pytest.raises(sqlite3.IntegrityError):
        store.db.execute("DELETE FROM audit")


@pytest.mark.parametrize(
    "changes,review_changes",
    [
        ({}, {"nigeria_eligible": False}),
        ({"organism_raw": None}, {}),
        ({"antibiotic_raw": None}, {}),
        ({"outcome": "unknown"}, {}),
        ({"numerator": None, "denominator": None, "reported_percentage": None}, {}),
        ({"reported_percentage": "50"}, {}),
    ],
)
def test_approval_gates(store, candidate, changes, review_changes):
    eid = store.add_estimate(candidate)
    review = Review(
        **{
            "reviewer": "test",
            "status": "approved",
            "nigeria_eligible": True,
            **review_changes,
        }
    )
    with pytest.raises(ValueError):
        store.review(eid, Estimate(**{**candidate.model_dump(), **changes}), review)
    assert store.estimate(eid)["status"] == "pending"


def test_denominator_free_percent_approval_flag(store, candidate):
    e = Estimate(**{**candidate.model_dump(), "numerator": None, "denominator": None})
    eid = store.add_estimate(e)
    store.review(eid, e, Review(reviewer="test", status="approved", nigeria_eligible=True))
    assert "missing_denominator" in export_records(store)[0]["flags"]


def test_ambiguous_mapping_blocks_approval(store, candidate):
    e = Estimate(**{**candidate.model_dump(), "mapping_uncertain": True})
    eid = store.add_estimate(e)
    assert "ambiguous_entity_or_stratum_mapping" in e.flags()
    with pytest.raises(ValueError, match="ambiguous"):
        store.review(eid, e, Review(reviewer="test", status="approved", nigeria_eligible=True))
    assert store.estimate(eid)["status"] == "pending"


def test_stale_review_and_duplicate_edit_rollback(store, candidate):
    eid = store.add_estimate(candidate)
    old = store.estimate(eid)
    review = Review(reviewer="test", status="pending")
    store.review(eid, candidate, review, old["updated"])
    with pytest.raises(ValueError, match="changed"):
        store.review(eid, candidate, review, old["updated"])
    other = Estimate(**{**candidate.model_dump(), "stratum": "other"})
    another = store.add_estimate(other)
    before = len(store.audit(another))
    with pytest.raises(ValueError, match="duplicates"):
        store.review(another, candidate, review)
    assert store.estimate(another)["data"]["stratum"] == "other"
    assert len(store.audit(another)) == before


def test_read_only_store(tmp_path):
    path = tmp_path / "db.sqlite3"
    writable = Store(path)
    writable.add_study(Study(title="read only test"))
    writable.close()
    ro = Store(path, read_only=True)
    with pytest.raises(PermissionError):
        ro.add_study(Study(title="fail"))
    ro.close()
    absent = tmp_path / "absent.sqlite3"
    ro = Store(absent, read_only=True)
    assert not absent.exists() and ro.sources() == []
    ro.close()


def test_unknown_schema(tmp_path):
    path = tmp_path / "future.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version=999")
    conn.close()
    with pytest.raises(ValueError, match="schema"):
        Store(path)


@pytest.mark.parametrize(
    "text", ["=HYPERLINK(1)", "+cmd", "-cmd", "@SUM(1)", "  =1", "\t=1", "\r=1"]
)
def test_csv_formula_defense(text):
    assert safe_cell(text).startswith("'")


def test_json_preserves_nulls_and_empty_export():
    assert safe_cell(None) == ""
    assert to_csv([]).startswith("schema_version,estimate_id,review_status")
    assert json.loads(to_json([{"x": None}]))["estimates"][0]["x"] is None
