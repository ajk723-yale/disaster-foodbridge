import pytest

from src.planning import build_plan, finalize_plan
from src.records import (
    cancel_commitments,
    empty_commitments,
    latest_validated,
    mark_delivered,
    mark_dispatched,
    set_status,
)
from tests.helpers import combine, inventory_records, shelter_records

CONFIG = {"meals_per_person_per_day": 3, "planning_window_hours": 24}
SH = "shelter_id,shelter_name,reported_at,evacuee_count,general_on_hand_meals,special_needs\n"
INV = "warehouse_id,item_id,item_name,category,diet_tag,unit,quantity,meals_per_unit,counted_at\n"


def test_latest_validated_ignores_pending_and_older_reports():
    old, _ = shelter_records(SH + "S1,A,2026-10-23T06:00+09:00,10,0,")
    new, _ = shelter_records(SH + "S1,A,2026-10-23T08:00+09:00,20,0,")
    newest_pending, _ = shelter_records(SH + "S1,A,2026-10-23T10:00+09:00,99,0,", validate=False)
    log = combine(new, old, newest_pending)  # order of arrival doesn't matter
    latest = latest_validated(log, ["shelter_id"], "reported_at")
    assert list(latest["evacuee_count"]) == [20]


def test_validated_correction_supersedes_original():
    orig, _ = shelter_records(SH + "S1,A,2026-10-23T08:00+09:00,10,0,")
    fix, _ = shelter_records(SH + "S1,A,2026-10-23T08:00+09:00,12,0,", received_at="2026-10-23T09:10+09:00",
                             validate=False)
    fix["supersedes"] = orig["record_id"].iloc[0]
    log = combine(orig, fix)
    assert list(latest_validated(log, ["shelter_id"], "reported_at")["evacuee_count"]) == [10]
    log = set_status(log, fix["record_id"].iloc[0], "validated", "staff", "2026-10-23T09:20+09:00")
    assert list(latest_validated(log, ["shelter_id"], "reported_at")["evacuee_count"]) == [12]


def test_status_rules():
    bad, _ = shelter_records(SH + "S1,A,2026-10-23T08:00+09:00,-1,0,", validate=False)
    with pytest.raises(ValueError, match="validation errors"):
        set_status(bad, bad["record_id"].iloc[0], "validated", "staff", "2026-10-23T09:00+09:00")
    ok, _ = shelter_records(SH + "S1,A,2026-10-23T08:00+09:00,1,0,")
    with pytest.raises(ValueError, match="already validated"):
        set_status(ok, ok["record_id"].iloc[0], "rejected", "staff", "2026-10-23T09:00+09:00")


def _setup(general_qty=60):
    shelters, _ = shelter_records(SH + "S1,A,2026-10-23T08:00+09:00,10,0,\nS2,B,2026-10-23T08:00+09:00,30,0,")
    inv, _ = inventory_records(INV + f"W1,I1,Meal,ready_meal,general,pack,{general_qty},1,2026-10-23T07:00+09:00")
    return shelters, inv


def test_finalize_records_commitments_and_prevents_double_counting():
    shelters, inv = _setup(general_qty=200)
    plan = build_plan(shelters, inv, empty_commitments(), CONFIG)
    assert plan["general"]["allocated_meals"] == 120
    result = finalize_plan(shelters, inv, empty_commitments(), CONFIG, plan["fingerprint"], "staff",
                           "2026-10-23T10:00+09:00", plan_id="P1")
    assert result["status"] == "finalized"
    commitments = result["commitments"]
    assert sorted(commitments["meals"]) == [30, 90]

    # Same data again: the food is already committed, so nothing more is allocated
    again = build_plan(shelters, inv, commitments, CONFIG)
    assert again["general"]["available_meals"] == 80
    assert again["general"]["total_unmet_meals"] == 0

    # Dispatched still counts as committed; cancelling an approved line returns it
    dispatched = mark_dispatched(commitments, [commitments["commitment_id"].iloc[0]], "2026-10-23T11:00+09:00")
    assert build_plan(shelters, inv, dispatched, CONFIG)["general"]["available_meals"] == 80
    cancelled = cancel_commitments(dispatched, [commitments["commitment_id"].iloc[1]])
    assert build_plan(shelters, inv, cancelled, CONFIG)["general"]["available_meals"] == 170
    with pytest.raises(ValueError):
        cancel_commitments(dispatched, [commitments["commitment_id"].iloc[0]])


def test_recount_after_dispatch_is_not_deducted_again():
    shelters, inv = _setup(general_qty=200)
    plan = build_plan(shelters, inv, empty_commitments(), CONFIG)
    commitments = finalize_plan(shelters, inv, empty_commitments(), CONFIG, plan["fingerprint"], "staff",
                                "2026-10-23T10:00+09:00")["commitments"]
    commitments = mark_dispatched(commitments, list(commitments["commitment_id"]), "2026-10-23T11:00+09:00", "W1")
    recount, _ = inventory_records(INV + "W1,I1,Meal,ready_meal,general,pack,80,1,2026-10-23T12:00+09:00")
    plan = build_plan(shelters, combine(inv, recount), commitments, CONFIG)
    assert plan["general"]["available_meals"] == 80


def test_new_shelter_report_after_dispatch_replaces_incoming():
    shelters, inv = _setup(general_qty=200)
    plan = build_plan(shelters, inv, empty_commitments(), CONFIG)
    commitments = finalize_plan(shelters, inv, empty_commitments(), CONFIG, plan["fingerprint"], "staff",
                                "2026-10-23T10:00+09:00")["commitments"]
    commitments = mark_dispatched(commitments, list(commitments["commitment_id"]), "2026-10-23T11:00+09:00", "W1")
    commitments = mark_delivered(commitments, list(commitments["commitment_id"]), "2026-10-23T12:00+09:00")
    # S1 reports again after confirmed delivery: its on-hand now includes the delivered food
    update, _ = shelter_records(SH + "S1,A,2026-10-23T13:00+09:00,15,30,")
    plan = build_plan(combine(shelters, update), inv, commitments, CONFIG)
    s1 = next(l for l in plan["general"]["lines"] if l["shelter_id"] == "S1")
    assert (s1["incoming_meals"], s1["unmet_meals"], s1["allocated_meals"]) == (0, 15, 15)


def test_changed_data_requires_confirmation_before_finalizing():
    shelters, inv = _setup(general_qty=60)
    reviewed = build_plan(shelters, inv, empty_commitments(), CONFIG)

    # A newer report is validated after staff reviewed the plan
    update, _ = shelter_records(SH + "S2,B,2026-10-23T09:45+09:00,50,0,")
    log = combine(shelters, update)
    result = finalize_plan(log, inv, empty_commitments(), CONFIG, reviewed["fingerprint"], "staff",
                           "2026-10-23T10:00+09:00")
    assert result["status"] == "needs_confirmation"
    updated = result["plan"]
    assert [l["allocated_meals"] for l in updated["general"]["lines"]] == [10, 50]

    # Staff confirm the updated plan -> finalized
    result = finalize_plan(log, inv, empty_commitments(), CONFIG, updated["fingerprint"], "staff",
                           "2026-10-23T10:05+09:00")
    assert result["status"] == "finalized"
    assert result["snapshot"]["inputs"]["shelter_record_ids"] == updated["inputs"]["shelter_record_ids"]


def test_config_change_also_changes_fingerprint():
    shelters, inv = _setup()
    a = build_plan(shelters, inv, empty_commitments(), CONFIG)
    b = build_plan(shelters, inv, empty_commitments(), {**CONFIG, "planning_window_hours": 12})
    assert a["fingerprint"] != b["fingerprint"]
    assert build_plan(shelters, inv, empty_commitments(), CONFIG)["fingerprint"] == a["fingerprint"]


def test_pending_newer_report_produces_warning():
    shelters, inv = _setup()
    pending, _ = shelter_records(SH + "S1,A,2026-10-23T11:00+09:00,12,0,", validate=False)
    plan = build_plan(combine(shelters, pending), inv, empty_commitments(), CONFIG)
    assert any("S1" in w and "pending" in w for w in plan["warnings"])
