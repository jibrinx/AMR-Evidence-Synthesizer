from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from amr_evidence.config import Settings

APP = Path(__file__).parents[1] / "app.py"


@pytest.mark.parametrize(
    "changes",
    [
        {"read_only": True},
        {"ai_enabled": False},
        {"ai_model": ""},
        {"ai_base_url": "http://cloud.example/v1"},
        {"ai_base_url": "https://user:pass@cloud.example/v1"},
        {"ai_base_url": "https://cloud.example/v1?key=secret"},
        {"ai_base_url": "file:///etc/passwd"},
        {"ai_base_url": "http://localhost:11434/v1"},
        {"ai_api_key": ""},
    ],
)
def test_invalid_ai_settings(changes):
    config = Settings(
        **{
            "read_only": False,
            "ai_enabled": True,
            "ai_model": "test",
            "ai_api_key": "test",
            **changes,
        }
    )
    with pytest.raises((ValueError, PermissionError)):
        config.validate_ai()


def test_local_settings_and_redacted_repr():
    config = Settings(
        read_only=False,
        ai_enabled=True,
        ai_model="local-tool-model",
        ai_base_url="http://localhost:11434/v1",
        allow_local_http=True,
    )
    config.validate_ai()
    assert "localhost:11434" in config.public_destination()
    assert "secret-test" not in repr(Settings(ai_api_key="secret-test"))


def test_default_public_settings(monkeypatch):
    monkeypatch.delenv("AMR_READ_ONLY", raising=False)
    monkeypatch.delenv("AMR_AI_ENABLED", raising=False)
    assert Settings.from_env().read_only
    assert not Settings.from_env().ai_enabled


def test_ambiguous_readonly_setting_fails_closed(monkeypatch):
    monkeypatch.setenv("AMR_READ_ONLY", "truue")
    with pytest.raises(ValueError, match="ambiguous"):
        Settings.from_env()


@pytest.mark.parametrize("mode", ["true", "false"])
def test_all_empty_app_views(tmp_path, monkeypatch, mode):
    monkeypatch.setenv("AMR_DB_PATH", str(tmp_path / "app.sqlite3"))
    monkeypatch.setenv("AMR_READ_ONLY", mode)
    monkeypatch.setenv("AMR_AI_ENABLED", "false")
    app = AppTest.from_file(str(APP), default_timeout=15).run()
    assert not app.exception
    for area in ["Upload", "Agent", "Review", "Database", "Guide", "Discover"]:
        app.sidebar.radio[0].set_value(area).run()
        assert not app.exception, f"{area}: {app.exception}"


def test_review_app_with_record(tmp_path, monkeypatch):
    from amr_evidence.models import Estimate, Study
    from amr_evidence.store import Store

    path = tmp_path / "app.sqlite3"
    store = Store(path)
    study = store.add_study(Study(title="[TEST ONLY] UI test"))
    sid = store.add_source(study, "test.txt", ["[TEST ONLY] source quote"])
    eid = store.add_estimate(
        Estimate(
            source_id=sid,
            page=1,
            quote="[TEST ONLY] source quote",
            organism_raw="test organism",
            antibiotic_raw="test antibiotic",
            outcome="resistant",
            reported_percentage="30",
        )
    )
    store.close()
    monkeypatch.setenv("AMR_DB_PATH", str(path))
    monkeypatch.setenv("AMR_READ_ONLY", "false")
    monkeypatch.setenv("AMR_AI_ENABLED", "false")
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    app.sidebar.radio[0].set_value("Review").run()
    assert not app.exception
    labels = [t.label for t in app.text_input]
    assert "Reviewer identity" in labels
    next(t for t in app.text_input if t.label == "Reviewer identity").set_value("UI test reviewer")
    next(t for t in app.selectbox if t.label == "Review decision").set_value("approved")
    next(
        t
        for t in app.checkbox
        if t.label == "I verified that this estimate concerns Nigerian samples"
    ).check()
    next(t for t in app.button if t.label == "Save review").click().run()
    assert not app.exception and not app.error
    store = Store(path)
    assert store.estimate(eid)["status"] == "approved"
    store.close()
    app.sidebar.radio[0].set_value("Database").run()
    assert not app.exception
    assert app.metric[0].value == "1"
