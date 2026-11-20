"""Provenance-rich exports. JSON remains machine-faithful; CSV protects spreadsheet text."""

import csv
import io
import json

from amr_evidence import SCHEMA_VERSION
from amr_evidence.store import now


def export_records(store, statuses=("approved",)):
    if not statuses or set(statuses) - {"pending", "approved", "rejected"}:
        raise ValueError("Select valid review statuses.")
    output = []
    for row in store.estimates():
        if row["status"] not in statuses:
            continue
        source = store.source(row["source_id"])
        output.append(
            {
                "schema_version": SCHEMA_VERSION,
                "estimate_id": row["id"],
                **row["data"],
                "review_status": row["status"],
                "review": row["review"],
                "flags": row["flags"],
                "extraction_method": row["method"],
                "agent_run_id": row["run_id"],
                "source_name": source["name"],
                "source_kind": source["kind"],
                "source_sha256": source["content_hash"],
                "study": source["study"],
                "created": row["created"],
                "updated": row["updated"],
            }
        )
    return output


def to_json(records):
    return json.dumps(
        {"schema_version": SCHEMA_VERSION, "exported_at": now(), "estimates": records},
        ensure_ascii=False,
        indent=2,
    )


def safe_cell(value):
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False)
    if isinstance(value, str) and (
        value.startswith(("\t", "\r", "\n")) or value.lstrip().startswith(("=", "+", "-", "@"))
    ):
        return "'" + value
    return value


def to_csv(records):
    stream = io.StringIO(newline="")
    headers = list(records[0]) if records else ["schema_version", "estimate_id", "review_status"]
    writer = csv.DictWriter(stream, fieldnames=headers)
    writer.writeheader()
    writer.writerows({key: safe_cell(value) for key, value in row.items()} for row in records)
    return stream.getvalue()
