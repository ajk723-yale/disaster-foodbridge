"""Finalization stops on pending data until staff acknowledge each warning with a reason."""
import json
import sqlite3

from src.finalization import finalize_and_store
from src.planning import MIN_REASON_LENGTH, build_plan
from tests.test_allocation_tool import SHELTERS, V, logs

CONFIG = {"meals_per_person_per_day": 3, "planning_window_hours": 24}
RICE_60 = f"x,{V},W1,I1,Rice,meal,general,pack,60,1,2026-01-01T05:00+09:00\n"
PENDING_S2 = "p1,csv,2026-01-01T09:05+09:00,pending,,,S2,Two,2026-01-01T09:00+09:00,80,0,,\n"
PENDING_ONLY_S3 = "p2,csv,2026-01-01T09:05+09:00,pending,,,S3,Three,2026-01-01T09:00+09:00,12,0,,\n"
REJECTED_ONLY_S4 = "r1,csv,2026-01-01T09:05+09:00,rejected,T,2026-01-01T09:10+09:00,S4,Four,2026-01-01T09:00+09:00,9,0,,\n"
PENDING_COUNT = "p3,csv,2026-01-01T09:05+09:00,pending,,,W1,I1,Rice,meal,general,pack,5,1,2026-01-01T09:00+09:00\n"
REASON = "S2 headcount call unanswered; deliver today on last validated figures"
AT = "2026-01-01T12:00+09:00"


def review(tmp_path, shelters=SHELTERS, inventory=RICE_60):
    s, i, c, _ = logs(tmp_path, shelters, inventory)
    return [str(tmp_path / f"{n}.csv") for n in ("s", "i", "c")], build_plan(s, i, c, CONFIG)


def finalize(db, paths, plan, acks=None, staff="Tanaka"):
    return finalize_and_store(db, *paths, CONFIG, plan["fingerprint"], staff, AT, acknowledgements=acks)


def ack_all(plan, reason=REASON):
    return [{"warning_id": w["warning_id"], "reason": reason} for w in plan["pending_data_warnings"]]


def stored(db):
    conn = sqlite3.connect(db)
    try:
        return (conn.execute("SELECT COUNT(*) FROM finalized_plans").fetchone()[0],
                conn.execute("SELECT COUNT(*) FROM plan_commitments").fetchone()[0],
                conn.execute("SELECT warning_id, reason, acknowledged_by FROM plan_acknowledgements "
                             "ORDER BY warning_id").fetchall())
    finally:
        conn.close()


def test_normal_finalization_without_pending_data(tmp_path, isolated_finalization_db):
    paths, plan = review(tmp_path)
    assert plan["pending_data_warnings"] == []
    result = finalize(isolated_finalization_db, paths, plan)
    assert result["status"] == "finalized" and result["snapshot"]["acknowledgements"] == []
    assert stored(isolated_finalization_db) == (1, 2, [])


def test_all_kinds_of_pending_data_are_warned(tmp_path):
    _, plan = review(tmp_path, SHELTERS + PENDING_S2 + PENDING_ONLY_S3 + REJECTED_ONLY_S4, RICE_60 + PENDING_COUNT)
    kinds = {(w["kind"], w["subject"]) for w in plan["pending_data_warnings"]}
    assert kinds == {("pending_shelter_report", "S2"), ("shelter_without_validated_report", "S3"),
                     ("shelter_without_validated_report", "S4"), ("pending_inventory_count", "W1/I1")}
    by_subject = {w["subject"]: w for w in plan["pending_data_warnings"]}
    assert by_subject["S2"]["pending_record_ids"] == ["p1"]
    assert "only rejected reports" in by_subject["S4"]["message"]


def test_missing_acknowledgements_stop_finalization(tmp_path, isolated_finalization_db):
    db = isolated_finalization_db
    paths, plan = review(tmp_path, SHELTERS + PENDING_S2 + PENDING_ONLY_S3)
    result = finalize(db, paths, plan)
    assert result["status"] == "acknowledgement_required"
    assert {p["problem"] for p in result["problems"]} == {"not acknowledged"}
    assert len(result["warnings"]) == 2
    # partial, too-short, duplicate, and unknown acknowledgements are all rejected
    first, second = plan["pending_data_warnings"]
    bad = [{"warning_id": first["warning_id"], "reason": REASON},
           {"warning_id": first["warning_id"], "reason": REASON},
           {"warning_id": second["warning_id"], "reason": "ok"},
           {"warning_id": "made-up", "reason": REASON}]
    result = finalize(db, paths, plan, bad)
    problems = {(p["warning_id"], p["problem"]) for p in result["problems"]}
    assert result["status"] == "acknowledgement_required"
    assert (first["warning_id"], "acknowledged more than once") in problems
    assert (second["warning_id"], f"reason must be at least {MIN_REASON_LENGTH} characters") in problems
    assert ("made-up", "not a current warning (data may have changed)") in problems
    assert stored(db) == (0, 0, [])


def test_acknowledged_warnings_finalize_and_are_stored_for_audit(tmp_path, isolated_finalization_db):
    db = isolated_finalization_db
    paths, plan = review(tmp_path, SHELTERS + PENDING_S2, RICE_60 + PENDING_COUNT)
    result = finalize(db, paths, plan, ack_all(plan), staff="Suzuki")
    assert result["status"] == "finalized"
    acks = result["snapshot"]["acknowledgements"]
    assert {a["kind"] for a in acks} == {"pending_shelter_report", "pending_inventory_count"}
    assert all(a["reason"] == REASON and a["acknowledged_by"] == "Suzuki" and a["acknowledged_at"] for a in acks)
    plans, lines, rows = stored(db)
    assert (plans, lines) == (1, 2)
    assert sorted(r[0] for r in rows) == sorted(w["warning_id"] for w in plan["pending_data_warnings"])
    assert all(r[1:] == (REASON, "Suzuki") for r in rows)
    conn = sqlite3.connect(db)
    snapshot = json.loads(conn.execute("SELECT snapshot_json FROM finalized_plans").fetchone()[0])
    conn.close()
    assert [a["warning_id"] for a in snapshot["acknowledgements"]] == [a["warning_id"] for a in acks]


def test_new_pending_data_after_review_requires_fresh_review_and_acknowledgement(tmp_path, isolated_finalization_db):
    db = isolated_finalization_db
    paths, plan = review(tmp_path, SHELTERS + PENDING_S2)
    acks = ack_all(plan)
    with open(paths[0], "a") as f:                       # another pending report arrives before finalizing
        f.write(PENDING_ONLY_S3)
    result = finalize(db, paths, plan, acks)
    assert result["status"] == "needs_confirmation"     # allocation unchanged, but warnings changed
    fresh = result["plan"]
    assert [l["allocated_meals"] for l in fresh["general"]["lines"]] == \
        [l["allocated_meals"] for l in plan["general"]["lines"]]
    result = finalize(db, paths, fresh, acks)            # old acknowledgements don't cover the new warning
    assert result["status"] == "acknowledgement_required"
    assert [p["problem"] for p in result["problems"]] == ["not acknowledged"]
    assert finalize(db, paths, fresh, ack_all(fresh))["status"] == "finalized"
    assert len(stored(db)[2]) == 2


def test_replaced_pending_report_changes_the_warning(tmp_path, isolated_finalization_db):
    db = isolated_finalization_db
    paths, plan = review(tmp_path, SHELTERS + PENDING_S2)
    acks = ack_all(plan)
    with open(paths[0], "a") as f:                       # a second, newer pending report for the same shelter
        f.write("p9,csv,2026-01-01T10:05+09:00,pending,,,S2,Two,2026-01-01T10:00+09:00,95,0,,\n")
    result = finalize(db, paths, plan, acks)
    assert result["status"] == "needs_confirmation"
    [new_warning] = result["plan"]["pending_data_warnings"]
    assert new_warning["warning_id"] != acks[0]["warning_id"] and new_warning["pending_record_ids"] == ["p1", "p9"]
    assert stored(db) == (0, 0, [])


def test_pending_data_validated_before_finalization_requires_fresh_review(tmp_path, isolated_finalization_db):
    db = isolated_finalization_db
    paths, plan = review(tmp_path, SHELTERS + PENDING_S2)
    text = open(paths[0]).read().replace("p1,csv,2026-01-01T09:05+09:00,pending,,,",
                                         "p1,csv,2026-01-01T09:05+09:00,validated,T,2026-01-01T09:30+09:00,")
    open(paths[0], "w").write(text)
    result = finalize(db, paths, plan, ack_all(plan))
    assert result["status"] == "needs_confirmation"
    fresh = result["plan"]
    assert fresh["pending_data_warnings"] == []
    assert finalize(db, paths, fresh)["status"] == "finalized"   # no acknowledgement needed now
