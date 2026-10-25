"""Read record logs (shelter reports, warehouse inventory, commitments) from disk.

Each log is a CSV with the data fields plus the record metadata
(record_id, source, received_at, status, validated_by, validated_at,
supersedes, source_text). Rows are re-validated on load, so a record with
errors is never treated as usable even if its status says validated.
A missing file means no data yet (an empty log), not an error.
"""
import os

import pandas as pd

from src.data_io import load_inventory, load_shelter_reports
from src.records import COMMITMENT_COLUMNS, empty_commitments, empty_log
from src.schemas import INVENTORY_COLUMNS, RECORD_META_COLUMNS, SHELTER_COLUMNS, normalize_tag
from src.validation import validate_inventory, validate_shelter_reports

STATUSES = ("pending", "validated", "rejected")


def _load_log(path, loader, validator, data_columns):
    """Return (log_df, issues). issues lists file problems and row errors."""
    if not os.path.exists(path):
        return empty_log(data_columns), []
    raw = loader(path)
    missing = [c for c in ("record_id", "status", "received_at") if c not in raw.columns]
    if missing:
        return empty_log(data_columns), [
            {"severity": "error", "row": None, "field": c, "message": f"record log is missing column '{c}'"}
            for c in missing]
    log, issues = validator(raw)
    for col in RECORD_META_COLUMNS:
        if col not in log.columns:
            log[col] = ""
    # utc + ISO8601: rows may mix offsets (+09:00 sample rows, UTC rows written by the app) and precisions
    log["received_at"] = pd.to_datetime(log["received_at"], errors="coerce", utc=True, format="ISO8601")
    log["validated_at"] = pd.to_datetime(log["validated_at"].replace("", None), errors="coerce", utc=True,
                                         format="ISO8601")
    bad_status = ~log["status"].isin(STATUSES)
    for i in log.index[bad_status]:
        issues.append({"severity": "error", "row": int(i), "field": "status",
                       "message": f"unknown status '{log.at[i, 'status']}'"})
    # A row with validation errors can't count as validated, whatever the file says
    downgrade = (log["status"] == "validated") & ~log["row_ok"].astype(bool)
    log.loc[downgrade | bad_status, "status"] = "pending"
    return log, issues


def load_shelter_log(path):
    return _load_log(path, load_shelter_reports, validate_shelter_reports, SHELTER_COLUMNS)


def load_inventory_log(path):
    return _load_log(path, load_inventory, validate_inventory, INVENTORY_COLUMNS)


COMMITMENT_STATUSES = ("approved", "dispatched", "delivered", "cancelled")


def load_commitments(path):
    """Read the approved/dispatched allocation log. Returns (commitments_df, issues).

    Invalid rows are left out and reported, so staff can fix the log.
    """
    if not os.path.exists(path):
        return empty_commitments(), []
    raw = pd.read_csv(path, dtype=str, keep_default_na=False)
    optional = ("warehouse_id", "delivered_at")
    missing = [c for c in COMMITMENT_COLUMNS if c not in raw.columns and c not in optional]
    if missing:
        return empty_commitments(), [{"severity": "error", "row": None, "field": c,
                                      "message": f"commitments log is missing column '{c}'"} for c in missing]
    for col in optional:
        if col not in raw.columns:
            raw[col] = ""
    rows, issues = [], []
    for i, r in enumerate(raw.to_dict("records")):
        problems = []
        if r["status"] not in COMMITMENT_STATUSES:
            problems.append(f"unknown status '{r['status']}'")
        try:
            meals = int(r["meals"])
            if meals < 0:
                problems.append("meals is negative")
        except ValueError:
            problems.append(f"meals '{r['meals']}' is not a whole number")
        times = {}
        for col in ("committed_at", "dispatched_at", "delivered_at"):
            if not r[col]:
                times[col] = None
                continue
            ts = pd.Timestamp(r[col]) if r[col] else None
            if ts is None or ts.tzinfo is None:
                problems.append(f"{col} '{r[col]}' needs a timezone offset")
            times[col] = ts
        if times.get("committed_at") is None:
            problems.append("committed_at is required")
        if r["status"] in ("dispatched", "delivered") and times.get("dispatched_at") is None:
            problems.append(f"{r['status']} rows need dispatched_at")
        if r["status"] == "delivered" and times.get("delivered_at") is None:
            problems.append("delivered rows need delivered_at (confirmed delivery time)")
        if r["status"] != "delivered" and times.get("delivered_at") is not None:
            problems.append(f"delivered_at is set but status is {r['status']}")
        if (times.get("delivered_at") is not None and times.get("dispatched_at") is not None
                and times["delivered_at"] < times["dispatched_at"]):
            problems.append("delivered_at is before dispatched_at")
        if problems:
            issues += [{"severity": "error", "row": i, "field": None, "message": m} for m in problems]
            continue
        rows.append({**{c: r[c] for c in COMMITMENT_COLUMNS}, "meals": meals,
                     "diet_tag": normalize_tag(r["diet_tag"]), **times})
    return pd.DataFrame(rows, columns=COMMITMENT_COLUMNS), issues


def append_record(path, row, default_columns):
    """Append one record row to a CSV log, never rewriting existing rows.

    Uses the file's own header order; creates the file (with default_columns) if it
    doesn't exist. An exclusive lock prevents interleaved writes from two staff.
    """
    import csv
    import fcntl

    from src.workspace import assert_writable

    assert_writable(path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a+", newline="", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0)
            header = next(csv.reader(f), None)
            if not header:
                header = list(default_columns)
                f.seek(0, os.SEEK_END)
                csv.writer(f).writerow(header)
            missing = [c for c in header if c not in row]
            extra = [c for c in row if c not in header]
            if extra:
                raise ValueError(f"log {path} has no column(s) {extra}")
            f.seek(0, os.SEEK_END)
            if f.tell() > 0:
                f.seek(f.tell() - 1)
                last = f.read(1)
                f.seek(0, os.SEEK_END)
                if last not in ("\n", "\r"):
                    f.write("\n")
            csv.writer(f).writerow([row.get(c, "") for c in header])
            f.flush()
            os.fsync(f.fileno())
            return missing
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
