"""Technical fixtures are not published studies or scientific estimates."""

import pytest
import requests

from amr_evidence.models import Estimate, Study
from amr_evidence.store import Store

TEST_QUOTE = "[TEST ONLY] Escherichia coli were resistant to ciprofloxacin: 3/10 (30%)."


@pytest.fixture(autouse=True)
def block_unmocked_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Tests must not make live network or paid AI calls.")

    monkeypatch.setattr(requests.sessions.Session, "request", blocked)


@pytest.fixture
def store():
    value = Store(":memory:")
    yield value
    value.close()


@pytest.fixture
def source(store):
    study_id = store.add_study(Study(title="[TEST ONLY] Technical fixture, not a study"))
    return store.add_source(study_id, "test-input.txt", [TEST_QUOTE])


@pytest.fixture
def candidate(source):
    return Estimate(
        source_id=source,
        page=1,
        quote=TEST_QUOTE,
        organism_raw="Escherichia coli",
        antibiotic_raw="ciprofloxacin",
        outcome="resistant",
        numerator=3,
        denominator=10,
        reported_percentage="30",
    )
