"""Persist finalized allocation plans in SQLite, one staff finalization at a time.

The CSV record logs stay the source for reports, counts, and the dispatch log.
SQLite stores only what finalization creates: the plan snapshot and its approved
allocation lines, written in one transaction.

finalize_and_store():
1. BEGIN IMMEDIATE takes the database write lock before anything is read, so two
   finalizations can't interleave; the second waits (up to the busy timeout).
2. If the reviewed fingerprint was already finalized, it stops: already_finalized.
3. It loads the CSV logs, adds the approvals already stored here, and calls the
   existing finalize_plan(), which recalculates and compares fingerprints.
   finalize_plan() also stops until every pending-data warning is acknowledged
   with a reason (acknowledgement_required).
4. Only a "finalized" result is written: plan + approvals + acknowledgements +
   the draft supply request commit together, or nothing does. The request is
   built from the same inputs as the plan (same fingerprint) and stored as a
   snapshot; it is never regenerated from newer data afterwards.
All stored timestamps are UTC. A UNIQUE reviewed_fingerprint is the last guard against a
   duplicate finalization.
"""
import json
import os
import sqlite3

import pandas as pd

from src.drafts import allocation_from_logs, supply_request_from_allocation
from src.planning import build_plan, finalize_plan
from src.records import COMMITMENT_COLUMNS, empty_commitments
from src.store import load_commitments, load_inventory_log, load_shelter_log
from src.timeutil import to_utc, utc_iso, utc_now
from src.workspace import assert_writable

SCHEMA = """
CREATE TABLE IF NOT EXISTS finalized_plans (
    plan_id              TEXT PRIMARY KEY,
    reviewed_fingerprint TEXT NOT NULL UNIQUE,
    finalized_by         TEXT NOT NULL,
    finalized_at         TEXT NOT NULL,
    snapshot_json        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS plan_commitments (
    commitment_id TEXT PRIMARY KEY,
    plan_id       TEXT NOT NULL REFERENCES finalized_plans(plan_id),
    shelter_id    TEXT NOT NULL,
    diet_tag      TEXT NOT NULL,
    meals         INTEGER NOT NULL CHECK (meals > 0),
    status        TEXT NOT NULL,
    committed_at  TEXT NOT NULL,
    dispatched_at TEXT,
    warehouse_id  TEXT,
    delivered_at  TEXT
);
CREATE TABLE IF NOT EXISTS plan_acknowledgements (
    plan_id            TEXT NOT NULL REFERENCES finalized_plans(plan_id),
    warning_id         TEXT NOT NULL,
    kind               TEXT NOT NULL,
    subject            TEXT NOT NULL,
    pending_record_ids TEXT NOT NULL,
    message            TEXT NOT NULL,
    reason             TEXT NOT NULL,
    acknowledged_by    TEXT NOT NULL,
    acknowledged_at    TEXT NOT NULL,
    PRIMARY KEY (plan_id, warning_id)
);
CREATE TABLE IF NOT EXISTS supply_requests (
    plan_id          TEXT PRIMARY KEY REFERENCES finalized_plans(plan_id),
    plan_fingerprint TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    request_json     TEXT NOT NULL
);
"""
REQUEST_SNAPSHOT_NOTE = ("Snapshot of the data and allocation results at finalization. It is not updated "
                         "when shelter reports, inventory counts, or dispatches change later.")
BUSY_TIMEOUT_SECONDS = 30


def connect(db_path):
    """Open the finalization database, creating its tables if needed.

    isolation_level=None: transactions are begun and ended explicitly.
    """
    assert_writable(db_path)
    conn = sqlite3.connect(db_path, timeout=BUSY_TIMEOUT_SECONDS, isolation_level=None)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def _stored_commitments(conn):
    rows = conn.execute(f"SELECT {', '.join(COMMITMENT_COLUMNS)} FROM plan_commitments").fetchall()
    df = pd.DataFrame(rows, columns=COMMITMENT_COLUMNS)
    for col in ("committed_at", "dispatched_at", "delivered_at"):
        df[col] = [pd.Timestamp(v) if v else None for v in df[col]]
    df["warehouse_id"] = df["warehouse_id"].fillna("")
    return df


def load_finalized_commitments(db_path):
    """Approved allocation lines from finalized plans (empty if no database yet)."""
    if not os.path.exists(db_path):
        return empty_commitments()
    conn = connect(db_path)
    try:
        return _stored_commitments(conn)
    finally:
        conn.close()


def _combine(*frames):
    frames = [f for f in frames if f is not None and not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else empty_commitments()


def _iso(value):
    return pd.Timestamp(value).isoformat() if value is not None and pd.notna(value) else None


def _load_inputs(shelter_log_path, inventory_log_path, commitments_log_path, stored_commitments):
    shelter_log, _ = load_shelter_log(shelter_log_path)
    inventory_log, _ = load_inventory_log(inventory_log_path)
    csv_commitments, issues = load_commitments(commitments_log_path)
    return shelter_log, inventory_log, _combine(csv_commitments, stored_commitments), issues


def review_plan(db_path, shelter_log_path, inventory_log_path, commitments_log_path, config):
    """The plan staff review before finalizing, built from the same inputs that
    finalize_and_store() rechecks (CSV logs plus approvals already finalized)."""
    shelter_log, inventory_log, commitments, _ = _load_inputs(
        shelter_log_path, inventory_log_path, commitments_log_path, load_finalized_commitments(db_path))
    return build_plan(shelter_log, inventory_log, commitments, config)


def finalize_and_store(db_path, shelter_log_path, inventory_log_path, commitments_log_path, config,
                       reviewed_fingerprint, staff_name, at, plan_id=None, acknowledgements=None):
    """Finalize the reviewed plan and persist it atomically.

    acknowledgements: [{"warning_id", "reason"}] for the plan's pending-data warnings.
    Returns one of:
    - {"status": "finalized", "plan_id", "snapshot", "commitments", "supply_request"}  (new approvals only)
    - {"status": "needs_confirmation", "plan"}  data or warnings changed since review; nothing stored
    - {"status": "acknowledgement_required", "plan", "warnings", "problems"}  nothing stored
    - {"status": "already_finalized", "plan_id", "finalized_by", "finalized_at"}  nothing stored
    """
    at = to_utc(at)
    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            existing = conn.execute(
                "SELECT plan_id, finalized_by, finalized_at FROM finalized_plans WHERE reviewed_fingerprint = ?",
                (reviewed_fingerprint,)).fetchone()
            if existing:
                conn.execute("ROLLBACK")
                return _already_finalized(existing)

            # Read inputs inside the lock so the recalculation sees the latest data
            shelter_log, inventory_log, commitments, commitment_issues = _load_inputs(
                shelter_log_path, inventory_log_path, commitments_log_path, _stored_commitments(conn))

            result = finalize_plan(shelter_log, inventory_log, commitments, config, reviewed_fingerprint,
                                   staff_name, at, plan_id, acknowledgements)
            if result["status"] != "finalized":
                conn.execute("ROLLBACK")
                return result

            snapshot = {**result["snapshot"], "reviewed_fingerprint": reviewed_fingerprint}
            plan_id = snapshot["plan_id"]

            # Draft request from the very same inputs (before this plan's approvals)
            draft = allocation_from_logs(shelter_log, inventory_log, commitments, config, commitment_issues)
            if draft["plan_fingerprint"] != reviewed_fingerprint:
                raise RuntimeError("supply request inputs do not match the finalized plan")
            request = {**supply_request_from_allocation(draft),
                       "status": (f"DRAFT requiring staff review. Not sent to anyone. Linked to finalized "
                                  f"allocation plan {plan_id}; nothing has been dispatched by this request."),
                       "plan_id": plan_id,
                       "plan_fingerprint": reviewed_fingerprint, "finalized_by": staff_name,
                       "finalized_at": snapshot["finalized_at"], "created_at": utc_iso(utc_now()),
                       "snapshot_note": REQUEST_SNAPSHOT_NOTE}
            new = result["commitments"][result["commitments"]["plan_id"] == plan_id]
            conn.execute(
                "INSERT INTO finalized_plans (plan_id, reviewed_fingerprint, finalized_by, finalized_at, snapshot_json)"
                " VALUES (?, ?, ?, ?, ?)",
                (plan_id, reviewed_fingerprint, staff_name, snapshot["finalized_at"],
                 json.dumps(snapshot, sort_keys=True, ensure_ascii=False)))
            conn.executemany(
                f"INSERT INTO plan_commitments ({', '.join(COMMITMENT_COLUMNS)})"
                f" VALUES ({', '.join('?' * len(COMMITMENT_COLUMNS))})",
                [(r["commitment_id"], plan_id, r["shelter_id"], r["diet_tag"], int(r["meals"]), r["status"],
                  _iso(r["committed_at"]), _iso(r["dispatched_at"]), r["warehouse_id"] or None,
                  _iso(r["delivered_at"]))
                 for r in new.to_dict("records")])
            conn.executemany(
                "INSERT INTO plan_acknowledgements (plan_id, warning_id, kind, subject, pending_record_ids, message,"
                " reason, acknowledged_by, acknowledged_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(plan_id, a["warning_id"], a["kind"], a["subject"], json.dumps(a["pending_record_ids"]),
                  a["message"], a["reason"], a["acknowledged_by"], a["acknowledged_at"])
                 for a in snapshot["acknowledgements"]])
            conn.execute(
                "INSERT INTO supply_requests (plan_id, plan_fingerprint, created_at, request_json) VALUES (?, ?, ?, ?)",
                (plan_id, reviewed_fingerprint, request["created_at"],
                 json.dumps(request, sort_keys=True, ensure_ascii=False)))
            conn.execute("COMMIT")
            return {"status": "finalized", "plan_id": plan_id, "snapshot": snapshot,
                    "commitments": new.reset_index(drop=True), "supply_request": request}
        except sqlite3.IntegrityError:
            conn.execute("ROLLBACK")
            existing = conn.execute(
                "SELECT plan_id, finalized_by, finalized_at FROM finalized_plans WHERE reviewed_fingerprint = ?",
                (reviewed_fingerprint,)).fetchone()
            if existing:
                return _already_finalized(existing)
            raise
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()


def _already_finalized(row):
    plan_id, by, at = row
    return {"status": "already_finalized", "plan_id": plan_id, "finalized_by": by, "finalized_at": at}


def get_saved_request(db_path, plan_id):
    """The draft supply request stored with a finalized plan, exactly as saved (or None)."""
    if not os.path.exists(db_path):
        return None
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT request_json FROM supply_requests WHERE plan_id = ?", (plan_id,)).fetchone()
        return json.loads(row[0]) if row else None
    finally:
        conn.close()


def get_saved_plan(db_path, plan_id):
    """The finalized plan snapshot (or None)."""
    if not os.path.exists(db_path):
        return None
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT snapshot_json FROM finalized_plans WHERE plan_id = ?", (plan_id,)).fetchone()
        return json.loads(row[0]) if row else None
    finally:
        conn.close()


def list_finalized_plans(db_path):
    """[(plan_id, finalized_by, finalized_at UTC)], newest first."""
    if not os.path.exists(db_path):
        return []
    conn = connect(db_path)
    try:
        return conn.execute("SELECT plan_id, finalized_by, finalized_at FROM finalized_plans "
                            "ORDER BY finalized_at DESC").fetchall()
    finally:
        conn.close()
