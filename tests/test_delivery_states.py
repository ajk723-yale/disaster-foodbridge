"""Approved / dispatched / delivered / cancelled food in the needs and stock calculations."""
import pytest

from src.records import (
    add_commitments,
    cancel_commitments,
    empty_commitments,
    incoming_breakdown,
    inventory_position,
    latest_validated,
    mark_delivered,
    mark_dispatched,
)
from tests.helpers import combine, inventory_records, shelter_records

SH = "shelter_id,shelter_name,reported_at,evacuee_count,general_on_hand_meals\n"
INV = "warehouse_id,item_id,item_name,category,diet_tag,unit,quantity,meals_per_unit,counted_at\n"


def t(hhmm):
    return f"2026-10-24T{hhmm}+09:00"


def approved(meals=30, at="07:00"):
    return add_commitments(empty_commitments(), "P1", [("S1", "general", meals)], t(at))


def ids(c):
    return list(c["commitment_id"])


def shelters(*reports):
    log = combine(*[shelter_records(SH + f"S1,One,{t(at)},10,{on_hand}")[0] for at, on_hand in reports])
    return latest_validated(log, ["shelter_id"], "reported_at")


def states(shelter_rows, commitments):
    incoming, flags = incoming_breakdown(shelter_rows, commitments)
    return incoming.get(("S1", "general")), flags


def test_approved_is_committed_not_shipped():
    got, flags = states(shelters(("08:00", 0)), approved())
    assert got == {"committed_not_shipped": 30, "shipped_not_confirmed": 0, "delivered_after_report": 0}
    assert flags == []


def test_dispatched_after_report_is_shipped_not_confirmed():
    c = approved()
    c = mark_dispatched(c, ids(c), t("09:00"), "W1")
    got, flags = states(shelters(("08:00", 0)), c)
    assert got["shipped_not_confirmed"] == 30 and flags == []


def test_delayed_delivery_newer_report_does_not_assume_arrival():
    c = approved()
    c = mark_dispatched(c, ids(c), t("07:30"), "W1")
    # Shelter reports at 10:00; the truck is delayed and delivery isn't confirmed
    got, flags = states(shelters(("06:00", 0), ("10:00", 5)), c)
    assert got == {"committed_not_shipped": 0, "shipped_not_confirmed": 30, "delivered_after_report": 0}
    assert len(flags) == 1 and "delivery is not confirmed" in flags[0]["message"]


def test_delivery_confirmed_after_report_counts_until_next_report():
    c = approved()
    c = mark_delivered(mark_dispatched(c, ids(c), t("07:30"), "W1"), ids(c), t("11:00"))
    got, _ = states(shelters(("10:00", 5)), c)
    assert got["delivered_after_report"] == 30


def test_newer_report_after_confirmed_delivery_is_not_double_counted():
    c = approved()
    c = mark_delivered(mark_dispatched(c, ids(c), t("07:30"), "W1"), ids(c), t("11:00"))
    got, flags = states(shelters(("10:00", 5), ("12:00", 35)), c)  # 12:00 on-hand includes the 30 meals
    assert got is None and flags == []


def test_delivery_at_report_time_is_in_that_report():
    c = approved()
    c = mark_delivered(mark_dispatched(c, ids(c), t("07:30"), "W1"), ids(c), t("10:00"))
    got, _ = states(shelters(("10:00", 35)), c)
    assert got is None


def test_cancelled_is_ignored():
    c = approved()
    got, _ = states(shelters(("08:00", 0)), cancel_commitments(c, ids(c)))
    assert got is None


def test_state_transitions_are_enforced():
    c = approved()
    with pytest.raises(ValueError):
        mark_delivered(c, ids(c), t("09:00"))                   # approved -> delivered skips shipping
    shipped = mark_dispatched(c, ids(c), t("08:00"), "W1")
    with pytest.raises(ValueError):
        cancel_commitments(shipped, ids(c))                      # shipped food can't be cancelled
    delivered = mark_delivered(shipped, ids(c), t("09:00"))
    assert delivered["status"].iloc[0] == "delivered"
    with pytest.raises(ValueError):
        mark_delivered(delivered, ids(c), t("10:00"))


def test_delivery_does_not_change_warehouse_deduction():
    log, _ = inventory_records(INV + f"W1,I1,Rice,meal,general,pack,300,1,{t('06:30')}")
    c = approved(100)
    shipped = mark_dispatched(c, ids(c), t("08:00"), "W1")
    delivered = mark_delivered(shipped, ids(c), t("13:00"))
    latest = latest_validated(log, ["warehouse_id", "item_id"], "counted_at")
    for commitments in (shipped, delivered):
        positions, _, _ = inventory_position(latest, commitments)
        assert positions["general"]["available"] == 200
    recount, _ = inventory_records(INV + f"W1,I1,Rice,meal,general,pack,200,1,{t('10:00')}")
    latest = latest_validated(combine(log, recount), ["warehouse_id", "item_id"], "counted_at")
    positions, _, _ = inventory_position(latest, delivered)
    assert positions["general"]["available"] == 200            # recount already reflects it


def test_needs_tool_reports_states_and_delayed_delivery(tmp_path):
    from src import agent_tools
    from src.store import load_commitments, load_shelter_log
    (tmp_path / "s.csv").write_text(
        "record_id,source,received_at,status,validated_by,validated_at,shelter_id,shelter_name,reported_at,"
        "evacuee_count,general_on_hand_meals\n"
        f"a,csv,{t('10:05')},validated,T,{t('10:10')},S1,One,{t('10:00')},20,0\n")
    (tmp_path / "c.csv").write_text(
        "commitment_id,plan_id,shelter_id,diet_tag,meals,status,committed_at,dispatched_at,warehouse_id,delivered_at\n"
        f"c1,P,S1,general,10,approved,{t('09:00')},,,\n"
        f"c2,P,S1,general,15,dispatched,{t('07:00')},{t('07:30')},W1,\n"        # delayed: left before report
        f"c3,P,S1,general,8,delivered,{t('07:00')},{t('07:30')},W1,{t('11:00')}\n"
        f"c4,P,S1,general,99,delivered,{t('06:00')},{t('06:30')},W1,{t('09:00')}\n"  # in the 10:00 on-hand
        f"c5,P,S1,general,50,cancelled,{t('09:00')},,,\n")
    log, _ = load_shelter_log(str(tmp_path / "s.csv"))
    commitments, issues = load_commitments(str(tmp_path / "c.csv"))
    assert issues == []
    result = agent_tools.shelter_needs_from_logs(log, commitments,
                                                 {"meals_per_person_per_day": 3, "planning_window_hours": 24})
    [line] = result["general_meals"]["shelters"]
    assert (line["approved_not_shipped_meals"], line["shipped_not_confirmed_meals"],
            line["delivered_after_report_meals"]) == (10, 15, 8)
    assert line["still_on_its_way_meals"] == 25      # delivered food is not "on its way"
    assert (line["need_meals"], line["on_hand_at_report_meals"], line["unmet_meals"]) == (60, 0, 27)
    assert any("c2" in f and "not confirmed" in f for f in result["flags"])


def test_loader_checks_delivery_fields(tmp_path):
    from src.store import load_commitments
    (tmp_path / "c.csv").write_text(
        "commitment_id,plan_id,shelter_id,diet_tag,meals,status,committed_at,dispatched_at,warehouse_id,delivered_at\n"
        f"c1,P,S1,general,10,delivered,{t('07:00')},{t('07:30')},W1,\n"
        f"c2,P,S1,general,10,delivered,{t('07:00')},{t('09:30')},W1,{t('09:00')}\n"
        f"c3,P,S1,general,10,dispatched,{t('07:00')},{t('07:30')},W1,{t('09:00')}\n")
    commitments, issues = load_commitments(str(tmp_path / "c.csv"))
    assert commitments.empty
    text = " ".join(i["message"] for i in issues)
    assert "need delivered_at" in text and "before dispatched_at" in text and "status is dispatched" in text
