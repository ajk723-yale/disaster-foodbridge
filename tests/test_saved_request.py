"""Draft supply request saved with each finalized plan: linked, immutable, UTC-stamped."""
import json
import sqlite3

import pytest

from src import agent_tools, config, finalization
from src.finalization import finalize_and_store, get_saved_plan, get_saved_request, list_finalized_plans
from src.planning import build_plan
from src.request_format import format_request_markdown
from src.timeutil import display_time, to_utc
from tests.test_allocation_tool import SHELTERS, V, logs

CONFIG = {"meals_per_person_per_day": 3, "planning_window_hours": 24}
SHELTERS_SPECIAL = SHELTERS + f"s3,{V},S3,Three,2026-01-01T06:00+09:00,10,0,\"infant_formula:2; halal:?\",\n"
INVENTORY = (f"x,{V},W1,I1,Rice,meal,general,pack,60,1,2026-01-01T05:00+09:00\n"
             f"y,{V},W1,I2,Formula,f,infant_formula,pack,4,1,2026-01-01T05:00+09:00\n")
PENDING_S2 = "p1,csv,2026-01-01T09:05+09:00,pending,,,S2,Two,2026-01-01T09:00+09:00,80,0,,\n"
REASON = "Proceeding on the last validated S2 report for this cycle"
LOCAL_AT = "2026-01-01T21:30+09:00"                    # staff clock in Tokyo


def finalized(tmp_path, db, shelters=SHELTERS_SPECIAL + PENDING_S2):
    s, i, c, _ = logs(tmp_path, shelters, INVENTORY)
    paths = [str(tmp_path / f"{n}.csv") for n in ("s", "i", "c")]
    plan = build_plan(s, i, c, CONFIG)
    acks = [{"warning_id": w["warning_id"], "reason": REASON} for w in plan["pending_data_warnings"]]
    result = finalize_and_store(db, *paths, CONFIG, plan["fingerprint"], "Tanaka", LOCAL_AT, "PLAN-1", acks)
    assert result["status"] == "finalized"
    return paths, plan, result


def test_saved_request_matches_its_finalized_plan(tmp_path, isolated_finalization_db):
    db = isolated_finalization_db
    _, plan, result = finalized(tmp_path, db)
    req, snap = get_saved_request(db, "PLAN-1"), get_saved_plan(db, "PLAN-1")
    assert req == result["supply_request"]
    assert req["status"].startswith("DRAFT") and "Not sent" in req["status"]
    assert "Linked to finalized allocation plan PLAN-1" in req["status"]
    assert "No allocation has been finalized" not in req["status"]
    assert (req["plan_id"], req["plan_fingerprint"]) == ("PLAN-1", plan["fingerprint"])
    assert req["plan_fingerprint"] == snap["fingerprint"] == snap["reviewed_fingerprint"]
    # same allocation results as the finalized snapshot
    g = req["general_meals"]
    assert (g["total_unmet_meals"], g["available_meals"], g["additional_meals_to_request"]) == \
        (snap["general"]["total_unmet_meals"], snap["general"]["available_meals"], snap["general"]["shortage_meals"])
    assert [(s["shelter_id"], s["shortfall_meals"]) for s in g["shortfall_by_shelter_after_plan_a"]] == \
        [(l["shelter_id"], l["shortfall_meals"]) for l in snap["general"]["lines"]]
    special = {s["diet_category"]: s for s in req["special_diet_requirements"]}
    assert {t: s["status"] for t, s in special.items()} == {g["diet_tag"]: g["status"] for g in snap["special"]}
    assert special["infant_formula"]["additional_meals_to_request"] == 2          # need 6, stock 4
    assert str(special["halal"]["additional_meals_to_request"]).startswith("to be confirmed")
    assert req["planning_period"]["window_hours"] == snap["config"]["planning_window_hours"] == 24
    assert any("S2" in w and "pending" in w for w in req["pending_or_uncertain_data"])
    assert req["placeholders"]["recipient"].startswith("[")


def test_later_data_changes_do_not_alter_the_saved_request(tmp_path, isolated_finalization_db, monkeypatch):
    db = isolated_finalization_db
    paths, _, _ = finalized(tmp_path, db)
    conn = sqlite3.connect(db)
    stored_before = conn.execute("SELECT request_json FROM supply_requests").fetchone()[0]
    conn.close()

    with open(paths[0], "a") as f:          # S2 report validated with more people; a new shelter appears
        f.write(f"z1,{V},S2,Two,2026-01-01T13:00+09:00,120,0,,\n"
                f"z2,{V},S9,Nine,2026-01-01T13:00+09:00,40,0,,\n")
    with open(paths[1], "a") as f:          # recount: rice nearly gone
        f.write(f"z3,{V},W1,I1,Rice,meal,general,pack,5,1,2026-01-01T13:00+09:00\n")

    conn = sqlite3.connect(db)
    stored_after = conn.execute("SELECT request_json FROM supply_requests").fetchone()[0]
    conn.close()
    assert stored_after == stored_before                       # byte-for-byte the same snapshot
    assert get_saved_request(db, "PLAN-1") == json.loads(stored_before)

    # whereas a fresh draft from current data is different
    for name, path in zip(("SHELTER_LOG_PATH", "INVENTORY_LOG_PATH", "COMMITMENTS_LOG_PATH"), paths):
        monkeypatch.setattr(config, name, path)
    current = agent_tools.prepare_supply_request()
    saved = json.loads(stored_before)
    assert current["general_meals"] != saved["general_meals"]
    assert current["allocation_plan_fingerprint"] != saved["plan_fingerprint"]


def test_no_request_without_successful_finalization(tmp_path, isolated_finalization_db):
    db = isolated_finalization_db
    s, i, c, _ = logs(tmp_path, SHELTERS + PENDING_S2, INVENTORY)
    paths = [str(tmp_path / f"{n}.csv") for n in ("s", "i", "c")]
    plan = build_plan(s, i, c, CONFIG)
    result = finalize_and_store(db, *paths, CONFIG, plan["fingerprint"], "Tanaka", LOCAL_AT)
    assert result["status"] == "acknowledgement_required"
    result = finalize_and_store(db, *paths, CONFIG, "stale-fingerprint", "Tanaka", LOCAL_AT)
    assert result["status"] == "needs_confirmation"
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM supply_requests").fetchone()[0] == 0
    conn.close()


def test_repeat_finalization_keeps_the_original_request(tmp_path, isolated_finalization_db):
    db = isolated_finalization_db
    paths, plan, first = finalized(tmp_path, db)
    again = finalize_and_store(db, *paths, CONFIG, plan["fingerprint"], "Suzuki", "2026-01-02T08:00+09:00")
    assert again["status"] == "already_finalized"
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM supply_requests").fetchone()[0] == 1
    conn.close()
    assert get_saved_request(db, "PLAN-1")["finalized_by"] == "Tanaka"


def test_request_rolls_back_with_the_plan(tmp_path, isolated_finalization_db, monkeypatch):
    db = isolated_finalization_db
    s, i, c, _ = logs(tmp_path, SHELTERS, INVENTORY)
    paths = [str(tmp_path / f"{n}.csv") for n in ("s", "i", "c")]
    plan = build_plan(s, i, c, CONFIG)
    monkeypatch.setattr(finalization, "supply_request_from_allocation",
                        lambda allocation: (_ for _ in ()).throw(RuntimeError("request build failed")))
    with pytest.raises(RuntimeError):
        finalize_and_store(db, *paths, CONFIG, plan["fingerprint"], "Tanaka", LOCAL_AT)
    assert list_finalized_plans(db) == []


def test_stored_timestamps_are_utc_and_display_uses_configured_zone(tmp_path, isolated_finalization_db, monkeypatch):
    db = isolated_finalization_db
    _, _, result = finalized(tmp_path, db)
    conn = sqlite3.connect(db)
    stamps = [conn.execute("SELECT finalized_at FROM finalized_plans").fetchone()[0],
              conn.execute("SELECT created_at FROM supply_requests").fetchone()[0],
              *[r[0] for r in conn.execute("SELECT committed_at FROM plan_commitments")],
              *[r[0] for r in conn.execute("SELECT acknowledged_at FROM plan_acknowledgements")]]
    conn.close()
    assert stamps and all(s.endswith("+00:00") for s in stamps)
    assert stamps[0] == "2026-01-01T12:30:00+00:00"            # 21:30 JST
    assert get_saved_request(db, "PLAN-1")["finalized_at"] == stamps[0]

    assert config.DISPLAY_TIMEZONE == "Asia/Tokyo"
    assert display_time(stamps[0]) == "2026-01-01 21:30 JST"
    monkeypatch.setattr(config, "DISPLAY_TIMEZONE", "America/New_York")
    assert display_time(stamps[0]) == "2026-01-01 07:30 EST"
    with pytest.raises(ValueError):
        to_utc("2026-01-01T12:00")                              # naive times are refused


def test_rendered_request_shows_only_saved_facts(tmp_path, isolated_finalization_db):
    db = isolated_finalization_db
    finalized(tmp_path, db)
    text = format_request_markdown(get_saved_request(db, "PLAN-1"))
    assert text.startswith("**DRAFT - REQUIRES STAFF REVIEW - NOT SENT**")
    assert "Plan ID: PLAN-1" in text and "2026-01-01 21:30 JST" in text
    assert "[RECIPIENT: PREFECTURAL DISASTER HEADQUARTERS OR NATIONAL GOVERNMENT CONTACT]" in text
    assert "not updated" in text
    assert "halal: amount to be confirmed" in text and "infant_formula: 2 additional meals" in text
