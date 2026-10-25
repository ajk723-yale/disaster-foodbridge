from pydantic_ai.models.test import TestModel

from src import agent, agent_tools, config
from src.records import empty_commitments
from src.store import load_shelter_log

HEADER = ("record_id,source,received_at,status,validated_by,validated_at,supersedes,shelter_id,shelter_name,"
          "reported_at,evacuee_count,general_on_hand_meals,special_needs,special_on_hand_meals\n")


def write_log(tmp_path, rows):
    path = tmp_path / "shelter_log.csv"
    path.write_text(HEADER + rows)
    return str(path)


def test_missing_file_means_no_validated_data(tmp_path):
    log, issues = load_shelter_log(str(tmp_path / "nope.csv"))
    result = agent_tools.shelter_reports_from_log(log)
    assert result["validated_shelters"] == [] and issues == []
    assert result["note"] == "No validated shelter reports are available."


def test_latest_validated_and_newer_pending(tmp_path):
    path = write_log(tmp_path,
        "a,csv,2026-01-01T07:00+09:00,validated,T,2026-01-01T07:10+09:00,,S1,One,2026-01-01T06:00+09:00,10,5,halal:?,\n"
        "b,csv,2026-01-01T09:00+09:00,validated,T,2026-01-01T09:10+09:00,,S1,One,2026-01-01T08:00+09:00,12,4.5,,\n"
        "c,csv,2026-01-01T10:00+09:00,pending,,,,S1,One,2026-01-01T09:30+09:00,30,0,,\n"
        "d,csv,2026-01-01T10:00+09:00,pending,,,,S2,Two,2026-01-01T09:30+09:00,7,0,,\n"
        "e,csv,2026-01-01T10:00+09:00,rejected,T,2026-01-01T10:05+09:00,,S2,Two,2026-01-01T09:45+09:00,700,0,,\n")
    log, _ = load_shelter_log(path)
    result = agent_tools.shelter_reports_from_log(log)
    [s1] = result["validated_shelters"]
    assert (s1["shelter_id"], s1["evacuee_count"], s1["general_food_on_hand_meals"]) == ("S1", 12, 4.5)
    assert s1["reported_at"] == "2026-01-01T08:00:00+09:00"
    pending = {p["shelter_id"]: p["has_validated_report"] for p in result["newer_reports_pending_validation"]}
    assert pending == {"S1": True, "S2": False}
    assert "note" not in result


def test_row_with_errors_is_not_used_even_if_marked_validated(tmp_path):
    path = write_log(tmp_path,
        "a,csv,2026-01-01T07:00+09:00,validated,T,2026-01-01T07:10+09:00,,S1,One,2026-01-01T06:00+09:00,-5,0,,\n")
    log, issues = load_shelter_log(path)
    assert agent_tools.shelter_reports_from_log(log)["validated_shelters"] == []
    assert any(i["severity"] == "error" for i in issues)


def test_agent_calls_tool_offline(tmp_path, monkeypatch):
    path = write_log(tmp_path,
        "a,csv,2026-01-01T07:00+09:00,validated,T,2026-01-01T07:10+09:00,,S1,One,2026-01-01T06:00+09:00,10,5,,\n")
    monkeypatch.setattr(config, "SHELTER_LOG_PATH", path)
    monkeypatch.setattr(config, "INVENTORY_LOG_PATH", str(tmp_path / "no_inventory.csv"))
    monkeypatch.setattr(config, "COMMITMENTS_LOG_PATH", str(tmp_path / "no_commitments.csv"))
    monkeypatch.setattr(config, "PORTKEY_API_KEY", "test-not-a-real-key")
    agent._agent.cache_clear()
    try:
        with agent._agent().override(model=TestModel()):
            result = agent.run_agent("What's the latest situation?", [])
    finally:
        agent._agent.cache_clear()
    events = {e["tool"]: e["detail"] for e in result["tool_events"]}  # TestModel calls every tool
    assert set(events) == {"get_shelter_reports", "get_warehouse_inventory", "calculate_shelter_needs",
                           "calculate_allocation", "prepare_supply_request"}
    assert "1 validated shelters" in events["get_shelter_reports"]
    assert "0 validated items" in events["get_warehouse_inventory"]


INV_HEADER = ("record_id,source,received_at,status,validated_by,validated_at,warehouse_id,item_id,"
              "item_name,category,diet_tag,unit,quantity,meals_per_unit,counted_at,expiry_date\n")


def write_inventory(tmp_path, rows):
    path = tmp_path / "inventory_log.csv"
    path.write_text(INV_HEADER + rows)
    return str(path)


def test_inventory_missing_file_means_no_data(tmp_path):
    from src.store import load_inventory_log
    log, _ = load_inventory_log(str(tmp_path / "nope.csv"))
    result = agent_tools.warehouse_inventory_from_log(log, empty_commitments())
    assert result["items"] == [] and result["meal_totals_by_diet_category"] == {}
    assert result["note"] == "No validated warehouse inventory counts are available."


def test_inventory_totals_keep_diet_categories_separate(tmp_path):
    from src.store import load_inventory_log
    path = write_inventory(tmp_path,
        "a,csv,2026-01-01T07:00+09:00,validated,T,2026-01-01T07:10+09:00,W1,I1,Rice,meal,general,pack,10,1,2026-01-01T06:00+09:00,\n"
        "b,csv,2026-01-01T07:00+09:00,validated,T,2026-01-01T07:10+09:00,W1,I2,Bread,meal,general,case,2,24,2026-01-01T06:00+09:00,2027-01-01\n"
        "c,csv,2026-01-01T07:00+09:00,validated,T,2026-01-01T07:10+09:00,W1,I3,Water,water,general,bottle,99,0,2026-01-01T06:00+09:00,\n"
        "d,csv,2026-01-01T07:00+09:00,validated,T,2026-01-01T07:10+09:00,W2,I4,Formula,formula,infant_formula,pack,5,1,2026-01-01T06:00+09:00,\n"
        "e,csv,2026-01-01T09:00+09:00,validated,T,2026-01-01T09:10+09:00,W1,I1,Rice,meal,general,pack,7,1,2026-01-01T08:00+09:00,\n"
        "f,csv,2026-01-01T10:00+09:00,pending,,,W2,I4,Formula,formula,infant_formula,pack,50,1,2026-01-01T09:00+09:00,\n"
        "g,csv,2026-01-01T10:00+09:00,rejected,T,2026-01-01T10:05+09:00,W1,I2,Bread,meal,general,case,200,24,2026-01-01T09:30+09:00,\n")
    log, _ = load_inventory_log(path)
    result = agent_tools.warehouse_inventory_from_log(log, empty_commitments())
    totals = {tag: t["available_meal_equivalents"] for tag, t in result["meal_totals_by_diet_category"].items()}
    assert totals == {"general": 7 + 48, "infant_formula": 5}
    water = next(i for i in result["items"] if i["item_id"] == "I3")
    assert water["counts_as_meals"] is False and water["meal_equivalents"] == 0
    bread = next(i for i in result["items"] if i["item_id"] == "I2")
    assert (bread["quantity"], bread["meal_equivalents"], bread["expiry_date"]) == (2, 48, "2027-01-01")
    assert [p["item_id"] for p in result["newer_counts_pending_validation"]] == ["I4"]


COMMIT_HEADER = "commitment_id,plan_id,shelter_id,diet_tag,meals,status,committed_at,dispatched_at,warehouse_id,delivered_at\n"


def tool_totals(tmp_path, inventory_rows, commitment_rows):
    from src.store import load_commitments, load_inventory_log
    (tmp_path / "commitments.csv").write_text(COMMIT_HEADER + commitment_rows)
    log, _ = load_inventory_log(write_inventory(tmp_path, inventory_rows))
    commitments, issues = load_commitments(str(tmp_path / "commitments.csv"))
    return agent_tools.warehouse_inventory_from_log(log, commitments, issues)


COUNT_0630 = "a,csv,2026-01-01T06:40+09:00,validated,T,2026-01-01T06:50+09:00,W1,I1,Rice,meal,general,pack,300,1,2026-01-01T06:30+09:00,\n"
RECOUNT_1000 = "b,csv,2026-01-01T10:05+09:00,validated,T,2026-01-01T10:10+09:00,W1,I1,Rice,meal,general,pack,200,1,2026-01-01T10:00+09:00,\n"
DISPATCH_0800 = "c1,P1,S1,general,100,dispatched,2026-01-01T07:30+09:00,2026-01-01T08:00+09:00,W1,\n"


def test_tool_dispatch_after_latest_count(tmp_path):
    result = tool_totals(tmp_path, COUNT_0630, DISPATCH_0800)
    g = result["meal_totals_by_diet_category"]["general"]
    assert (g["counted_meal_equivalents"], g["dispatched_since_count"], g["available_meal_equivalents"]) == (300, 100, 200)
    assert result["approved_and_dispatched_allocations"][0]["treatment"] == "deducted: left W1 after its latest count"


def test_tool_newer_recount_replaces_earlier_count(tmp_path):
    result = tool_totals(tmp_path, COUNT_0630 + RECOUNT_1000, DISPATCH_0800)
    g = result["meal_totals_by_diet_category"]["general"]
    assert (g["counted_meal_equivalents"], g["dispatched_since_count"], g["available_meal_equivalents"]) == (200, 0, 200)
    assert result["approved_and_dispatched_allocations"][0]["treatment"] == \
        "not deducted: W1 was recounted after this dispatch"


def test_tool_reports_bad_dispatch_log_rows(tmp_path):
    result = tool_totals(tmp_path, COUNT_0630, "c1,P1,S1,general,lots,dispatched,2026-01-01T07:30+09:00,,W1,\n")
    assert result["approved_and_dispatched_allocations"] == []
    assert any("not a whole number" in f for f in result["flags"])
    assert any("need dispatched_at" in f for f in result["flags"])


def needs_for(tmp_path, shelter_rows, commitment_rows="", plan=None):
    from src.store import load_commitments
    log, _ = load_shelter_log(write_log(tmp_path, shelter_rows))
    (tmp_path / "commitments.csv").write_text(COMMIT_HEADER + commitment_rows)
    commitments, _ = load_commitments(str(tmp_path / "commitments.csv"))
    plan = plan or {"meals_per_person_per_day": 3, "planning_window_hours": 24}
    return agent_tools.shelter_needs_from_logs(log, commitments, plan)


def test_needs_subtract_on_hand_and_on_its_way(tmp_path):
    result = needs_for(tmp_path,
        "a,csv,2026-01-01T07:00+09:00,validated,T,2026-01-01T07:10+09:00,,S1,One,2026-01-01T06:00+09:00,10,5,,\n",
        "c1,P1,S1,general,7,dispatched,2026-01-01T08:00+09:00,2026-01-01T08:30+09:00,W1,\n"
        # delivery confirmed before the report: already in its on-hand figure
        "c0,P0,S1,general,99,delivered,2026-01-01T05:00+09:00,2026-01-01T05:30+09:00,W1,2026-01-01T05:50+09:00\n")
    [line] = result["general_meals"]["shelters"]
    assert (line["need_meals"], line["on_hand_at_report_meals"], line["still_on_its_way_meals"],
            line["delivered_after_report_meals"], line["unmet_meals"]) == (30, 5, 7, 0, 18)


def test_needs_use_configured_rate_and_window(tmp_path):
    rows = "a,csv,2026-01-01T07:00+09:00,validated,T,2026-01-01T07:10+09:00,,S1,One,2026-01-01T06:00+09:00,10,0,,\n"
    result = needs_for(tmp_path, rows, plan={"meals_per_person_per_day": 2, "planning_window_hours": 36})
    assert result["general_meals"]["shelters"][0]["need_meals"] == 30
    assert result["planning"]["planning_window_hours"] == 36


def test_needs_keep_special_diets_separate_and_flag_unknowns(tmp_path):
    result = needs_for(tmp_path,
        "a,csv,2026-01-01T07:00+09:00,validated,T,2026-01-01T07:10+09:00,,S1,One,2026-01-01T06:00+09:00,10,0,"
        "\"infant_formula:2; halal:?\",infant_formula:1\n"
        "b,csv,2026-01-01T09:00+09:00,pending,,,,S1,One,2026-01-01T08:00+09:00,40,0,,\n"
        "c,csv,2026-01-01T09:00+09:00,pending,,,,S2,Two,2026-01-01T08:00+09:00,5,0,,\n")
    [g] = result["general_meals"]["shelters"]
    assert (g["people"], g["need_meals"], g["newer_report_pending_validation"]) == (8, 24, True)
    special = {s["diet_category"]: s for s in result["special_diets"]}
    assert special["infant_formula"]["complete"] and special["infant_formula"]["total_unmet_meals_known"] == 5
    halal = special["halal"]
    assert not halal["complete"] and halal["shelters"][0]["people"] == "unknown"
    assert halal["shelters"][0]["unmet_meals"] is None
    assert [s["shelter_id"] for s in result["shelters_without_validated_report"]] == ["S2"]
    text = " ".join(result["flags"])
    assert "general need may be overstated" in text and "'halal' is unknown" in text
    assert "newer report is pending" in text and "S2: no validated report" in text


def test_needs_without_validated_reports(tmp_path):
    result = needs_for(tmp_path, "")
    assert result["general_meals"]["shelters"] == [] and "note" in result
