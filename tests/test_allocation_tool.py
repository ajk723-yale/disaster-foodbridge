"""calculate_allocation tool: Plan A / Plan B drafts built on build_plan. Small test data only."""
from src import agent_tools
from src.planning import build_plan
from src.store import load_commitments, load_inventory_log, load_shelter_log

CONFIG = {"meals_per_person_per_day": 3, "planning_window_hours": 24}
SH = ("record_id,source,received_at,status,validated_by,validated_at,shelter_id,shelter_name,reported_at,"
      "evacuee_count,general_on_hand_meals,special_needs,special_on_hand_meals\n")
INV = ("record_id,source,received_at,status,validated_by,validated_at,warehouse_id,item_id,item_name,category,"
       "diet_tag,unit,quantity,meals_per_unit,counted_at\n")
CM = "commitment_id,plan_id,shelter_id,diet_tag,meals,status,committed_at,dispatched_at,warehouse_id,delivered_at\n"
V = "csv,2026-01-01T07:00+09:00,validated,T,2026-01-01T07:10+09:00"


def logs(tmp_path, shelters, inventory, commitments=""):
    for name, header, rows in (("s", SH, shelters), ("i", INV, inventory), ("c", CM, commitments)):
        (tmp_path / f"{name}.csv").write_text(header + rows)
    s, _ = load_shelter_log(str(tmp_path / "s.csv"))
    i, _ = load_inventory_log(str(tmp_path / "i.csv"))
    c, issues = load_commitments(str(tmp_path / "c.csv"))
    return s, i, c, issues


def draft(tmp_path, shelters, inventory, commitments=""):
    s, i, c, issues = logs(tmp_path, shelters, inventory, commitments)
    return agent_tools.allocation_from_logs(s, i, c, CONFIG, issues), build_plan(s, i, c, CONFIG)


SHELTERS = (f"a,{V},S1,One,2026-01-01T06:00+09:00,10,0,,\n"      # unmet 30
            f"b,{V},S2,Two,2026-01-01T06:00+09:00,30,0,,\n")     # unmet 90


def test_plan_a_is_feasible_and_plan_b_meets_all_demand(tmp_path):
    result, plan = draft(tmp_path, SHELTERS, f"x,{V},W1,I1,Rice,meal,general,pack,60,1,2026-01-01T05:00+09:00\n")
    g = result["general_meals"]
    assert result["status"].startswith("DRAFT")
    assert (g["available_meals"], g["total_unmet_meals"], g["plan_a_total_meals"], g["shortage_meals"]) == (60, 120, 60, 60)
    lines = {l["shelter_id"]: l for l in g["shelters"]}
    assert (lines["S1"]["plan_a_meals"], lines["S2"]["plan_a_meals"]) == (15, 45)            # proportional
    assert (lines["S1"]["plan_a_shortfall_meals"], lines["S2"]["plan_a_shortfall_meals"]) == (15, 45)
    assert (lines["S1"]["plan_b_meals"], lines["S2"]["plan_b_meals"]) == (30, 90)            # all unmet
    assert result["plan_b_additional_procurement_meals"]["general"] == 60
    # Plan A is exactly the existing allocation logic
    assert [l["plan_a_meals"] for l in g["shelters"]] == [l["allocated_meals"] for l in plan["general"]["lines"]]
    assert result["plan_fingerprint"] == plan["fingerprint"]


def test_enough_stock_makes_plans_equal(tmp_path):
    result, _ = draft(tmp_path, SHELTERS, f"x,{V},W1,I1,Rice,meal,general,pack,500,1,2026-01-01T05:00+09:00\n")
    g = result["general_meals"]
    assert g["shortage_meals"] == 0
    assert all(l["plan_a_meals"] == l["plan_b_meals"] for l in g["shelters"])


def test_plan_a_uses_available_stock_after_commitments(tmp_path):
    result, _ = draft(tmp_path, SHELTERS, f"x,{V},W1,I1,Rice,meal,general,pack,80,1,2026-01-01T05:00+09:00\n",
                      "c1,P,S2,general,20,dispatched,2026-01-01T06:30+09:00,2026-01-01T07:00+09:00,W1,\n")
    g = result["general_meals"]
    assert g["available_meals"] == 60          # 80 counted - 20 dispatched after the count
    assert g["total_unmet_meals"] == 100       # S2 unmet 90 - 20 shipped, not confirmed
    assert g["plan_a_total_meals"] == 60


def test_special_diets_stay_separate_with_staff_decisions(tmp_path):
    shelters = (f"a,{V},S1,One,2026-01-01T06:00+09:00,10,0,\"infant_formula:2; halal:?\",\n"
                f"b,{V},S2,Two,2026-01-01T06:00+09:00,10,0,infant_formula:2; allergy_free:1,\n")
    inventory = (f"x,{V},W1,I1,Rice,meal,general,pack,1000,1,2026-01-01T05:00+09:00\n"
                 f"y,{V},W1,I2,Formula,f,infant_formula,pack,7,1,2026-01-01T05:00+09:00\n"
                 f"z,{V},W1,I3,AF meal,meal,allergy_free,pack,9,1,2026-01-01T05:00+09:00\n")
    result, _ = draft(tmp_path, shelters, inventory)
    special = {s["diet_category"]: s for s in result["special_diets"]}
    af = special["allergy_free"]
    assert af["status"] == "ok" and af["shelters"][0]["plan_a_meals"] == 3
    formula = special["infant_formula"]                       # need 6 + 6, only 7 in stock
    assert formula["status"] == "shortage" and formula["shortage_meals_known"] == 5
    assert all(l["plan_a_meals"] is None for l in formula["shelters"])
    assert [l["plan_b_meals"] for l in formula["shelters"]] == [6, 6]
    halal = special["halal"]
    assert halal["status"] == "missing_info" and halal["shelters"][0]["plan_b_meals"] is None
    assert result["plan_b_additional_procurement_meals"]["infant_formula"] == 5
    assert "unknown" in str(result["plan_b_additional_procurement_meals"]["halal"])
    # special stock never reaches general meals
    assert result["general_meals"]["available_meals"] == 1000


def test_data_warnings_include_pending_and_unknowns(tmp_path):
    shelters = SHELTERS + "c,csv,2026-01-01T09:00+09:00,pending,,,S1,One,2026-01-01T08:30+09:00,99,0,,\n"
    result, _ = draft(tmp_path, shelters, f"x,{V},W1,I1,Rice,meal,general,pack,60,1,2026-01-01T05:00+09:00\n")
    text = " ".join(result["data_warnings"])
    assert "S1" in text and "pending" in text
    assert len(result["data_warnings"]) == len(set(result["data_warnings"]))


def test_no_validated_reports(tmp_path):
    result, _ = draft(tmp_path, "", f"x,{V},W1,I1,Rice,meal,general,pack,60,1,2026-01-01T05:00+09:00\n")
    assert result["general_meals"]["shelters"] == [] and "note" in result
