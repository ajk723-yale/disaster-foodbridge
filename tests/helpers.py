"""Build small in-memory logs from CSV text. Test data only."""
import io

from src.data_io import load_inventory, load_shelter_reports
from src.records import append_records, make_records, set_status
from src.validation import validate_inventory, validate_shelter_reports

_counter = iter(range(1, 10**6))


def next_id():
    return f"r{next(_counter):05d}"


def shelter_records(csv_text, received_at="2026-10-23T09:00+09:00", validate=True):
    clean, issues = validate_shelter_reports(load_shelter_reports(io.StringIO(csv_text)))
    recs = make_records(clean, "csv", received_at, id_factory=next_id)
    return _maybe_validate(recs, validate), issues


def inventory_records(csv_text, received_at="2026-10-23T09:00+09:00", validate=True):
    clean, issues = validate_inventory(load_inventory(io.StringIO(csv_text)))
    recs = make_records(clean, "csv", received_at, id_factory=next_id)
    return _maybe_validate(recs, validate), issues


def _maybe_validate(recs, validate):
    if validate:
        for rid in list(recs["record_id"]):
            recs = set_status(recs, rid, "validated", "tester", "2026-10-23T09:30+09:00")
    return recs


def combine(*logs):
    out = None
    for log in logs:
        out = append_records(out, log)
    return out
