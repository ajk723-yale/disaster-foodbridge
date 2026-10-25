"""SQLite persistence of finalized plans and protection against duplicate finalization."""
import json
import multiprocessing
import sqlite3
import threading
import time

import pytest

from src import agent_tools, config, finalization
from src.finalization import finalize_and_store, load_finalized_commitments
from src.planning import build_plan
from tests.test_allocation_tool import CM, INV, SH, SHELTERS, V, logs

CONFIG = {"meals_per_person_per_day": 3, "planning_window_hours": 24}
RICE_60 = f"x,{V},W1,I1,Rice,meal,general,pack,60,1,2026-01-01T05:00+09:00\n"
AT = "2026-01-01T12:00+09:00"


def setup(tmp_path, db_path, shelters=SHELTERS):
    s, i, c, _ = logs(tmp_path, shelters, RICE_60)
    paths = [str(tmp_path / f"{n}.csv") for n in ("s", "i", "c")]
    reviewed = build_plan(s, i, c, CONFIG)          # what staff saw (no finalized plans yet)
    return paths, reviewed


def finalize(db_path, paths, fingerprint, staff, plan_id=None):
    return finalize_and_store(db_path, *paths, CONFIG, fingerprint, staff, AT, plan_id)


def stored(db_path):
    conn = sqlite3.connect(db_path)
    try:
        plans = conn.execute("SELECT plan_id, reviewed_fingerprint, finalized_by FROM finalized_plans").fetchall()
        lines = conn.execute("SELECT plan_id, shelter_id, diet_tag, meals, status FROM plan_commitments "
                             "ORDER BY shelter_id").fetchall()
        return plans, lines
    finally:
        conn.close()


def test_successful_finalization_persists_plan_and_approvals(tmp_path, isolated_finalization_db, monkeypatch):
    db = isolated_finalization_db
    paths, reviewed = setup(tmp_path, db)
    result = finalize(db, paths, reviewed["fingerprint"], "Tanaka", plan_id="PLAN-1")
    assert result["status"] == "finalized" and result["plan_id"] == "PLAN-1"

    plans, lines = stored(db)
    assert plans == [("PLAN-1", reviewed["fingerprint"], "Tanaka")]
    assert lines == [("PLAN-1", "S1", "general", 15, "approved"), ("PLAN-1", "S2", "general", 45, "approved")]
    conn = sqlite3.connect(db)
    snapshot = json.loads(conn.execute("SELECT snapshot_json FROM finalized_plans").fetchone()[0])
    conn.close()
    assert snapshot["fingerprint"] == reviewed["fingerprint"] and snapshot["finalized_by"] == "Tanaka"
    assert [l["allocated_meals"] for l in snapshot["general"]["lines"]] == [15, 45]

    # The agent's tools now see the approvals: stock is reserved and the next draft is incremental
    assert len(load_finalized_commitments(db)) == 2
    for name, path in zip(("SHELTER_LOG_PATH", "INVENTORY_LOG_PATH", "COMMITMENTS_LOG_PATH"), paths):
        monkeypatch.setattr(config, name, path)
    draft = agent_tools.calculate_allocation()["general_meals"]
    assert (draft["available_meals"], draft["total_unmet_meals"], draft["plan_a_total_meals"]) == (0, 60, 0)


def test_repeated_finalization_fails_safely(tmp_path, isolated_finalization_db):
    db = isolated_finalization_db
    paths, reviewed = setup(tmp_path, db)
    first = finalize(db, paths, reviewed["fingerprint"], "Tanaka", plan_id="PLAN-1")
    second = finalize(db, paths, reviewed["fingerprint"], "Suzuki")
    assert first["status"] == "finalized"
    assert second == {"status": "already_finalized", "plan_id": "PLAN-1", "finalized_by": "Tanaka",
                      "finalized_at": first["snapshot"]["finalized_at"]}
    plans, lines = stored(db)
    assert len(plans) == 1 and len(lines) == 2                      # no duplicate approvals


def test_simultaneous_finalization_threads(tmp_path, isolated_finalization_db, monkeypatch):
    db = isolated_finalization_db
    paths, reviewed = setup(tmp_path, db)
    real = finalization.finalize_plan

    def slow_finalize_plan(*args, **kwargs):      # hold the transaction open to force overlap
        time.sleep(0.5)
        return real(*args, **kwargs)

    monkeypatch.setattr(finalization, "finalize_plan", slow_finalize_plan)
    barrier, results = threading.Barrier(2), {}

    def staff(name):
        barrier.wait()
        start = time.monotonic()
        results[name] = (finalize(db, paths, reviewed["fingerprint"], name), time.monotonic() - start)

    threads = [threading.Thread(target=staff, args=(n,)) for n in ("Tanaka", "Suzuki")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    statuses = sorted(r["status"] for r, _ in results.values())
    assert statuses == ["already_finalized", "finalized"]
    loser = next(n for n, (r, _) in results.items() if r["status"] == "already_finalized")
    assert results[loser][1] >= 0.4                                  # it waited for the lock
    plans, lines = stored(db)
    assert len(plans) == 1 and [l[3] for l in lines] == [15, 45]


def _process_finalize(args):
    db, paths, fingerprint, name = args
    return finalize_and_store(db, *paths, CONFIG, fingerprint, name, AT)["status"]


def test_simultaneous_finalization_separate_processes(tmp_path, isolated_finalization_db):
    db = isolated_finalization_db
    paths, reviewed = setup(tmp_path, db)
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(4) as pool:
        statuses = pool.map(_process_finalize, [(db, paths, reviewed["fingerprint"], f"staff-{n}") for n in range(4)])
    assert sorted(statuses) == ["already_finalized"] * 3 + ["finalized"]
    plans, lines = stored(db)
    assert len(plans) == 1 and len(lines) == 2


def test_stale_review_needs_confirmation_and_stores_nothing(tmp_path, isolated_finalization_db):
    db = isolated_finalization_db
    paths, reviewed = setup(tmp_path, db)
    with open(paths[0], "a") as f:                                 # a newer validated report arrives
        f.write(f"c,{V},S2,Two,2026-01-01T09:00+09:00,50,0,,\n")
    result = finalize(db, paths, reviewed["fingerprint"], "Tanaka")
    assert result["status"] == "needs_confirmation"
    assert stored(db) == ([], [])
    confirmed = finalize(db, paths, result["plan"]["fingerprint"], "Tanaka")
    assert confirmed["status"] == "finalized"
    assert [l[3] for l in stored(db)[1]] == [10, 50]


def test_failure_while_writing_rolls_back_everything(tmp_path, isolated_finalization_db, monkeypatch):
    db = isolated_finalization_db
    paths, reviewed = setup(tmp_path, db)
    real = finalization.finalize_plan

    def broken_finalize_plan(*args, **kwargs):     # last approval violates CHECK (meals > 0)
        result = real(*args, **kwargs)
        result["commitments"].loc[result["commitments"].index[-1], "meals"] = 0
        return result

    monkeypatch.setattr(finalization, "finalize_plan", broken_finalize_plan)
    with pytest.raises(sqlite3.IntegrityError):
        finalize(db, paths, reviewed["fingerprint"], "Tanaka")
    assert stored(db) == ([], [])                                   # plan row rolled back too
    monkeypatch.setattr(finalization, "finalize_plan", real)
    assert finalize(db, paths, reviewed["fingerprint"], "Tanaka")["status"] == "finalized"
