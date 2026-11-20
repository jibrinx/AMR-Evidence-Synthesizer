"""Small-workspace SQLite persistence. No agent receives a raw connection."""

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from amr_evidence import SCHEMA_VERSION
from amr_evidence.models import Estimate, Review, Study


def now():
    return datetime.now(UTC).isoformat()


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def digest(value):
    return hashlib.sha256(dumps(value).encode()).hexdigest()


class Store:
    def __init__(self, path="data/evidence.sqlite3", read_only=False):
        self.read_only = read_only
        path = Path(path).resolve() if path != ":memory:" else path
        if read_only and path != ":memory:" and path.exists():
            self.db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=10)
        else:
            if not read_only and path != ":memory:":
                path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(":memory:" if read_only else str(path), timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, SCHEMA_VERSION):
            self.db.close()
            raise ValueError("Unsupported database schema version. Back up and migrate first.")
        if version == 0:
            if read_only and path != ":memory:" and path.exists():
                raise ValueError("Read-only database is not initialized.")
            self._initialize()

    def _initialize(self):
        self.db.executescript("""
        CREATE TABLE studies(id INTEGER PRIMARY KEY, pmid TEXT UNIQUE, doi TEXT UNIQUE, data TEXT NOT NULL);
        CREATE TABLE sources(id INTEGER PRIMARY KEY, study_id INTEGER NOT NULL REFERENCES studies(id),
          content_hash TEXT NOT NULL UNIQUE, name TEXT NOT NULL, kind TEXT NOT NULL, pages TEXT NOT NULL);
        CREATE TABLE estimates(id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources(id),
          fingerprint TEXT NOT NULL UNIQUE, data TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
          review TEXT, method TEXT NOT NULL, run_id INTEGER, created TEXT NOT NULL, updated TEXT NOT NULL);
        CREATE TABLE audit(id INTEGER PRIMARY KEY, at TEXT NOT NULL, actor TEXT NOT NULL,
          action TEXT NOT NULL, entity TEXT NOT NULL, before_json TEXT, after_json TEXT NOT NULL);
        CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT,'append only'); END;
        CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT,'append only'); END;
        CREATE TABLE runs(id INTEGER PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE events(id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES runs(id),
          at TEXT NOT NULL, data TEXT NOT NULL);
        PRAGMA user_version=1;
        """)

    def close(self):
        self.db.close()

    def writable(self):
        if self.read_only:
            raise PermissionError("Read-only mode: changes and AI execution are disabled.")

    def _audit(self, actor, action, entity, before, after):
        self.db.execute(
            "INSERT INTO audit(at,actor,action,entity,before_json,after_json) VALUES(?,?,?,?,?,?)",
            (now(), actor, action, str(entity), dumps(before) if before else None, dumps(after)),
        )

    def add_study(self, study: Study):
        self.writable()
        matches = self.db.execute(
            "SELECT id FROM studies WHERE (pmid IS NOT NULL AND pmid=?) OR (doi IS NOT NULL AND doi=?)",
            (study.pmid, study.doi),
        ).fetchall()
        if len(matches) > 1:
            raise ValueError("PMID and DOI match different records; resolve citation conflict.")
        if matches:
            return matches[0]["id"]
        with self.db:
            row = self.db.execute(
                "INSERT INTO studies(pmid,doi,data) VALUES(?,?,?)",
                (study.pmid, study.doi, study.model_dump_json()),
            )
            self._audit("user", "create_study", row.lastrowid, None, study.model_dump())
        return row.lastrowid

    def add_source(self, study_id, name, pages, kind="text"):
        self.writable()
        if not pages or len(pages) > 100 or not any(p.strip() for p in pages):
            raise ValueError("Source must contain extractable text and at most 100 pages.")
        if sum(len(p) for p in pages) > 2_000_000:
            raise ValueError("Source text exceeds the 2 million character processing limit.")
        content_hash = digest(pages)
        match = self.db.execute(
            "SELECT id,study_id FROM sources WHERE content_hash=?", (content_hash,)
        ).fetchone()
        if match:
            if match["study_id"] != study_id:
                raise ValueError("This document already belongs to a different citation.")
            return match["id"]
        with self.db:
            row = self.db.execute(
                "INSERT INTO sources(study_id,content_hash,name,kind,pages) VALUES(?,?,?,?,?)",
                (study_id, content_hash, str(name)[:500], kind, dumps(pages)),
            )
            self._audit("user", "create_source", row.lastrowid, None, {"sha256": content_hash})
        return row.lastrowid

    def source(self, source_id):
        row = self.db.execute(
            "SELECT s.*,t.data AS study FROM sources s JOIN studies t ON t.id=s.study_id WHERE s.id=?",
            (source_id,),
        ).fetchone()
        if not row:
            raise ValueError("Unknown source.")
        value = dict(row)
        value["pages"] = json.loads(value["pages"])
        value["study"] = json.loads(value["study"])
        return value

    def sources(self):
        rows = self.db.execute("SELECT id FROM sources ORDER BY id DESC").fetchall()
        return [self.source(row["id"]) for row in rows]

    def check_evidence(self, estimate):
        source = self.source(estimate.source_id)
        if estimate.page > len(source["pages"]):
            raise ValueError("Source page does not exist.")
        if estimate.quote not in source["pages"][estimate.page - 1]:
            raise ValueError("Evidence quote must match the identified source page exactly.")

    @staticmethod
    def fingerprint(estimate):
        # Ignore execution metadata only. Preserve different quotes, strata, definitions, and fields.
        value = estimate.model_dump(exclude={"ai_observations", "notes"})
        return digest(value)

    def add_estimate(self, estimate: Estimate, method="manual", run_id=None):
        self.writable()
        if method not in {"manual", "rules", "agent"}:
            raise ValueError("Unknown extraction method.")
        self.check_evidence(estimate)
        fingerprint = self.fingerprint(estimate)
        match = self.db.execute(
            "SELECT id FROM estimates WHERE fingerprint=?", (fingerprint,)
        ).fetchone()
        if match:
            return match["id"]
        with self.db:
            row = self.db.execute(
                """INSERT INTO estimates(source_id,fingerprint,data,method,run_id,created,updated)
                VALUES(?,?,?,?,?,?,?)""",
                (
                    estimate.source_id,
                    fingerprint,
                    estimate.model_dump_json(),
                    method,
                    run_id,
                    now(),
                    now(),
                ),
            )
            self._audit(method, "create_pending", row.lastrowid, None, estimate.model_dump())
        return row.lastrowid

    def estimate(self, estimate_id):
        row = self.db.execute("SELECT * FROM estimates WHERE id=?", (estimate_id,)).fetchone()
        if not row:
            raise ValueError("Unknown estimate.")
        value = dict(row)
        value["data"] = json.loads(value["data"])
        value["review"] = json.loads(value["review"]) if value["review"] else None
        value["flags"] = Estimate.model_validate(value["data"]).flags()
        return value

    def estimates(self, status=None):
        if status not in (None, "pending", "approved", "rejected"):
            raise ValueError("Unknown review status.")
        rows = self.db.execute(
            "SELECT id FROM estimates WHERE (? IS NULL OR status=?) ORDER BY id DESC",
            (status, status),
        ).fetchall()
        return [self.estimate(row["id"]) for row in rows]

    def review(self, estimate_id, estimate: Estimate, review: Review, expected_updated=None):
        self.writable()
        before = self.estimate(estimate_id)
        if expected_updated is not None and before["updated"] != expected_updated:
            raise ValueError("Record changed since loading. Refresh before saving.")
        if before["source_id"] != estimate.source_id:
            raise ValueError(
                "Cannot reassign an estimate to another source; create a new candidate."
            )
        self.check_evidence(estimate)
        review.check_approval(estimate)
        try:
            with self.db:
                result = self.db.execute(
                    """UPDATE estimates SET data=?,fingerprint=?,status=?,review=?,updated=?
                    WHERE id=? AND updated=?""",
                    (
                        estimate.model_dump_json(),
                        self.fingerprint(estimate),
                        review.status,
                        review.model_dump_json(),
                        now(),
                        estimate_id,
                        before["updated"],
                    ),
                )
                if result.rowcount != 1:
                    raise ValueError("Concurrent edit detected. Refresh before saving.")
                self._audit(
                    review.reviewer,
                    "review_estimate",
                    estimate_id,
                    before,
                    {"data": estimate.model_dump(), "review": review.model_dump()},
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                "This edit duplicates another estimate; keep the records separate or correct the fields."
            ) from exc

    def new_run(self, data):
        self.writable()
        with self.db:
            row = self.db.execute("INSERT INTO runs(data) VALUES(?)", (dumps(data),))
        return row.lastrowid

    def save_run(self, run_id, data):
        self.writable()
        with self.db:
            self.db.execute("UPDATE runs SET data=? WHERE id=?", (dumps(data), run_id))

    def event(self, run_id, data):
        self.writable()
        with self.db:
            self.db.execute(
                "INSERT INTO events(run_id,at,data) VALUES(?,?,?)", (run_id, now(), dumps(data))
            )

    def runs(self):
        return [
            {"id": row["id"], **json.loads(row["data"])}
            for row in self.db.execute("SELECT * FROM runs ORDER BY id DESC")
        ]

    def events(self, run_id):
        return [
            {"at": row["at"], **json.loads(row["data"])}
            for row in self.db.execute("SELECT * FROM events WHERE run_id=? ORDER BY id", (run_id,))
        ]

    def audit(self, estimate_id):
        return [
            dict(row)
            for row in self.db.execute(
                "SELECT * FROM audit WHERE entity=? AND action IN ('create_pending','review_estimate') ORDER BY id",
                (str(estimate_id),),
            )
        ]
