"""Counted vs available stock with dispatch tracking. Small test data only."""
from src.records import add_commitments, cancel_commitments, empty_commitments, inventory_position, latest_validated
from tests.helpers import combine, inventory_records

INV = "warehouse_id,item_id,item_name,category,diet_tag,unit,quantity,meals_per_unit,counted_at\n"


def latest(log):
    return latest_validated(log, ["warehouse_id", "item_id"], "counted_at")


def approve(meals, at, tag="general", commitments=None):
    commitments = empty_commitments() if commitments is None else commitments
    return add_commitments(commitments, "P1", [("S1", tag, meals)], at)


def dispatch(commitments, at, warehouse):
    from src.records import mark_dispatched
    return mark_dispatched(commitments, list(commitments.loc[commitments["status"] == "approved", "commitment_id"]),
                           at, warehouse)


def position(log, commitments, tag="general"):
    positions, deductions, flags = inventory_position(latest(log), commitments)
    return positions[tag], deductions, flags


def test_dispatch_after_latest_count_is_deducted():
    count, _ = inventory_records(INV + "W1,I1,Rice,meal,general,pack,300,1,2026-10-24T06:30+09:00")
    c = dispatch(approve(100, "2026-10-24T07:30+09:00"), "2026-10-24T08:00+09:00", "W1")
    pos, deductions, flags = position(count, c)
    assert (pos["counted"], pos["dispatched_since_count"], pos["available"]) == (300, 100, 200)
    assert deductions[0]["treatment"] == "deducted: left W1 after its latest count"
    assert flags == []


def test_newer_recount_replaces_earlier_count_without_double_deduction():
    first, _ = inventory_records(INV + "W1,I1,Rice,meal,general,pack,300,1,2026-10-24T06:30+09:00")
    c = dispatch(approve(100, "2026-10-24T07:30+09:00"), "2026-10-24T08:00+09:00", "W1")
    recount, _ = inventory_records(INV + "W1,I1,Rice,meal,general,pack,200,1,2026-10-24T10:00+09:00")
    pos, deductions, _ = position(combine(first, recount), c)
    assert (pos["counted"], pos["dispatched_since_count"], pos["available"]) == (200, 0, 200)
    assert deductions[0]["treatment"] == "not deducted: W1 was recounted after this dispatch"


def test_recount_in_one_warehouse_does_not_affect_dispatch_from_another():
    log, _ = inventory_records(INV + "W1,I1,Rice,meal,general,pack,300,1,2026-10-24T06:30+09:00\n"
                                     "W2,I1,Rice,meal,general,pack,120,1,2026-10-24T10:00+09:00")
    from_w2 = dispatch(approve(30, "2026-10-24T08:30+09:00"), "2026-10-24T09:00+09:00", "W2")
    pos, _, _ = position(log, from_w2)
    assert pos["available"] == 420               # W2's 10:00 recount already reflects it
    from_w1 = dispatch(approve(30, "2026-10-24T08:30+09:00"), "2026-10-24T09:00+09:00", "W1")
    pos, _, _ = position(log, from_w1)
    assert pos["available"] == 390               # W1 not recounted since: deduct


def test_approved_food_stays_reserved_across_recounts():
    count, _ = inventory_records(INV + "W1,I1,Rice,meal,general,pack,300,1,2026-10-24T10:00+09:00")
    c = approve(50, "2026-10-24T08:00+09:00")
    pos, deductions, _ = position(count, c)
    assert (pos["reserved_not_dispatched"], pos["available"]) == (50, 250)
    assert deductions[0]["status"] == "approved"
    pos, deductions, _ = position(count, cancel_commitments(c, list(c["commitment_id"])))
    assert pos["available"] == 300 and deductions == []


def test_dispatch_without_warehouse_is_conservative_and_flagged():
    log, _ = inventory_records(INV + "W1,I1,Rice,meal,general,pack,300,1,2026-10-24T06:30+09:00\n"
                                     "W2,I1,Rice,meal,general,pack,120,1,2026-10-24T10:00+09:00")
    c = dispatch(approve(30, "2026-10-24T08:30+09:00"), "2026-10-24T09:00+09:00", "")
    pos, _, flags = position(log, c)
    assert pos["available"] == 390
    assert any("no source warehouse" in f["message"] for f in flags)


def test_special_diet_dispatch_only_affects_its_own_tag():
    log, _ = inventory_records(INV + "W1,I1,Rice,meal,general,pack,300,1,2026-10-24T06:30+09:00\n"
                                     "W1,I2,Formula,formula,infant_formula,pack,20,1,2026-10-24T06:30+09:00")
    c = dispatch(approve(5, "2026-10-24T07:00+09:00", tag="infant_formula"), "2026-10-24T07:30+09:00", "W1")
    positions, _, _ = inventory_position(latest(log), c)
    assert positions["general"]["available"] == 300
    assert positions["infant_formula"]["available"] == 15


def test_commitments_cannot_make_stock_negative():
    count, _ = inventory_records(INV + "W1,I1,Rice,meal,general,pack,10,1,2026-10-24T06:30+09:00")
    c = dispatch(approve(25, "2026-10-24T07:00+09:00"), "2026-10-24T07:30+09:00", "W1")
    pos, _, flags = position(count, c)
    assert pos["available"] == 0
    assert any("exceed counted stock" in f["message"] for f in flags)


SH = "shelter_id,shelter_name,reported_at,evacuee_count,general_on_hand_meals\n"


def incoming_for(report_time, commitments):
    from src.records import incoming_by_shelter
    from tests.helpers import shelter_records
    shelters, _ = shelter_records(SH + f"S1,One,{report_time},10,0")
    return incoming_by_shelter(latest_validated(shelters, ["shelter_id"], "reported_at"), commitments)


def test_food_dispatched_after_report_is_on_its_way_even_if_approved_before():
    c = dispatch(approve(30, "2026-10-24T08:30+09:00"), "2026-10-24T08:45+09:00", "W1")
    assert incoming_for("2026-10-24T08:30+09:00", c) == {("S1", "general"): 30}


def test_food_dispatched_before_report_is_not_assumed_delivered():
    c = dispatch(approve(30, "2026-10-24T07:00+09:00"), "2026-10-24T07:30+09:00", "W1")
    assert incoming_for("2026-10-24T08:00+09:00", c) == {("S1", "general"): 30}


def test_approved_not_dispatched_is_always_on_its_way():
    c = approve(24, "2026-10-24T07:00+09:00")
    assert incoming_for("2026-10-24T09:00+09:00", c) == {("S1", "general"): 24}
