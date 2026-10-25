"""Dashboard (P37/P38): figures come from the existing calculations, actions are derived from the data,
proposed allocations are never described as approved or dispatched, and nothing is written."""
import copy
import hashlib
import os
import re

import pytest

from src import agent_tools, config
from src.dashboard import build_dashboard, load_dashboard
from src.dashboard_view import render_dashboard

SH = ("record_id,source,received_at,status,validated_by,validated_at,shelter_id,shelter_name,reported_at,"
      "evacuee_count,general_on_hand_meals,special_needs,special_on_hand_meals\n")
INV = ("record_id,source,received_at,status,validated_by,validated_at,warehouse_id,item_id,item_name,category,"
       "diet_tag,unit,quantity,meals_per_unit,counted_at\n")
CM = "commitment_id,plan_id,shelter_id,diet_tag,meals,status,committed_at,dispatched_at,warehouse_id,delivered_at\n"
V = "csv,2026-01-01T07:00+09:00,validated,T,2026-01-01T07:10+09:00"
SHELTERS = (f"a,{V},S1,One,2026-01-01T06:00+09:00,10,0,,\n"      # unmet 30
            f"b,{V},S2,Two,2026-01-01T06:00+09:00,30,0,,\n")     # unmet 90
RICE = f"x,{V},W1,I1,Rice,meal,general,pack,{{}},1,2026-01-01T05:00+09:00\n"
SAMPLE = os.path.join(config.PROJECT_ROOT, "data", "sample")


@pytest.fixture
def data(tmp_path, monkeypatch):
    """Point the (read-only) tool reads at small CSVs written by the test."""
    def write(shelters, inventory, commitments=""):
        for name, header, rows, setting in (("s", SH, shelters, "SHELTER_LOG_PATH"),
                                            ("i", INV, inventory, "INVENTORY_LOG_PATH"),
                                            ("c", CM, commitments, "COMMITMENTS_LOG_PATH")):
            (tmp_path / f"{name}.csv").write_text(header + rows)
            monkeypatch.setattr(config, setting, str(tmp_path / f"{name}.csv"))
        return load_dashboard()
    return write


def tool_outputs(monkeypatch):
    for setting, name in (("SHELTER_LOG_PATH", "shelter_log.csv"), ("INVENTORY_LOG_PATH", "inventory_log.csv"),
                          ("COMMITMENTS_LOG_PATH", "commitments_log.csv")):
        monkeypatch.setattr(config, setting, os.path.join(SAMPLE, name))         # read only
    return (agent_tools.get_shelter_reports(), agent_tools.get_warehouse_inventory(),
            agent_tools.calculate_shelter_needs(), agent_tools.calculate_allocation())


def text_of(component):
    if isinstance(component, (str, int, float)):
        return str(component)
    if component is None:
        return ""
    if isinstance(component, (list, tuple)):
        return " ".join(text_of(c) for c in component)
    return text_of(getattr(component, "children", None))


def test_figures_are_the_existing_tool_outputs(monkeypatch):
    reports, inventory, needs, allocation = tool_outputs(monkeypatch)
    d = build_dashboard(reports, inventory, needs, allocation)
    assert d == load_dashboard()
    g = allocation["general_meals"]
    s = d["situation"]
    assert (s["available_meals"], s["unmet_meals"], s["additional_meals_needed"]) == (
        g["available_meals"], g["total_unmet_meals"], allocation["plan_b_additional_procurement_meals"]["general"])
    assert s["covered_share"] == pytest.approx(g["available_meals"] / g["total_unmet_meals"])
    for row, tool in zip(d["plans"]["rows"], g["shelters"]):
        assert (row["plan_a_meals"], row["plan_a_shortfall_meals"], row["plan_b_meals"]) == (
            tool["plan_a_meals"], tool["plan_a_shortfall_meals"], tool["plan_b_meals"])
    assert [x["diet_category"] for x in d["plans"]["special_diets"]] == [
        x["diet_category"] for x in allocation["special_diets"]]
    assert d["details"]["data_warnings"] == allocation["data_warnings"]


def test_sample_data_actions_cover_every_warning(monkeypatch):
    d = build_dashboard(*tool_outputs(monkeypatch))
    kinds = [a["kind"] for a in d["actions"]]
    assert kinds == ["missing_report", "unknown_special_count", "pending_report", "pending_inventory_count"]
    assert "other_note" not in kinds                         # every sample warning maps to a specific action
    for a in d["actions"]:
        assert a["title"] and a["why"] and a["next_step"]
    assert [a["tab"] for a in d["actions"]] == ["intake", "intake", "intake", None]


def test_actions_follow_the_data_in_priority_order(data):
    shelters = (f"a,{V},S1,One,2026-01-01T06:00+09:00,10,0,\"infant_formula:2; halal:?\",\n"
                f"b,{V},S2,Two,2026-01-01T06:00+09:00,10,0,infant_formula:2,\n"
                "c,csv,2026-01-01T09:00+09:00,pending,,,S2,Two,2026-01-01T08:30+09:00,12,0,,\n"
                "d,csv,2026-01-01T09:00+09:00,pending,,,S3,Three,2026-01-01T08:40+09:00,50,0,,\n")
    inventory = (RICE.format(1000) + f"y,{V},W1,I2,Formula,f,infant_formula,pack,7,1,2026-01-01T05:00+09:00\n"
                 "p,csv,2026-01-01T09:00+09:00,pending,,,W1,I1,Rice,meal,general,pack,900,1,2026-01-01T08:00+09:00\n")
    d = data(shelters, inventory)
    got = [(a["kind"], a["severity"]) for a in d["actions"]]
    assert got == [("special_diet_shortage", "shortage"), ("missing_report", "uncertain"),
                   ("unknown_special_count", "uncertain"), ("pending_report", "uncertain"),
                   ("pending_inventory_count", "uncertain")]
    short = d["actions"][0]
    assert "infant formula" in short["title"] and "5 short" in short["title"]   # 12 needed, 7 in stock
    assert "S3" in d["actions"][1]["title"] and d["actions"][1]["tab"] == "intake"
    assert "halal" in d["actions"][2]["title"] and "S1" in d["actions"][2]["title"]
    assert "S2" in d["actions"][3]["title"]
    assert "Rice" in d["actions"][4]["title"] and d["actions"][4]["tab"] is None
    assert [a["rank"] for a in d["actions"]] == [1, 2, 3, 4, 5]


def test_unmapped_warnings_are_never_dropped(monkeypatch):
    reports, inventory, needs, allocation = tool_outputs(monkeypatch)
    allocation = copy.deepcopy(allocation)
    allocation["data_warnings"].append("W9: a new kind of data problem nobody anticipated")
    d = build_dashboard(reports, inventory, needs, allocation)
    note = d["actions"][-1]
    assert note["kind"] == "other_note" and note["title"] == "Data note: " + allocation["data_warnings"][-1]
    assert note["tab"] == "review"


def test_dashboard_follows_the_data(data):
    d = data(SHELTERS, RICE.format(60))
    assert (d["situation"]["available_meals"], d["situation"]["unmet_meals"],
            d["situation"]["additional_meals_needed"]) == (60, 120, 60)
    assert d["situation"]["covered_share"] == pytest.approx(0.5)
    assert [r["plan_a_meals"] for r in d["plans"]["rows"]] == [15, 45]
    assert "50%" in text_of(render_dashboard(d))
    d = data(SHELTERS, RICE.format(500))                     # enough stock: no shortage, no actions
    assert d["situation"]["additional_meals_needed"] == 0 and d["situation"]["covered_share"] == 1.0
    assert d["actions"] == []
    page = text_of(render_dashboard(d))
    assert "No open issues" in page and "All unmet demand covered" in page
    assert "still short" not in page and "must be procured" not in page and " short" not in page.replace(
        "Remaining shortage", "")


def test_proposed_allocations_are_never_called_approved_or_dispatched(monkeypatch):
    page = text_of(render_dashboard(build_dashboard(*tool_outputs(monkeypatch))))
    assert "Proposed only: nothing has been approved, reserved, or dispatched." in page
    # The situation and the plan itself (not the assumptions, which describe real past deliveries)
    plan = page[:page.index("Shelter details")].replace(
        "Proposed only: nothing has been approved, reserved, or dispatched.", "")
    plan = plan[:plan.index("Actions required")] + plan[plan.index("Allocation plan"):]
    assert not re.search(r"\b(approved|dispatched|delivered|sent|sends|shipped|reserved)\b", plan, re.I), plan
    assert plan.count("proposed") >= 2 * len(build_dashboard(*tool_outputs(monkeypatch))["plans"]["rows"])
    assert "Plan A · uses available inventory" in page and "Plan B · requires additional procurement" in page
    for heading in ("Current situation", "Actions required", "Allocation plan"):
        assert heading in page
    assert page.index("Current situation") < page.index("Actions required") < page.index("Allocation plan")


def test_dashboard_reads_without_writing(data, tmp_path):
    data(SHELTERS, RICE.format(60))
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.glob("*.csv")}
    load_dashboard()
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.glob("*.csv")} == before
    assert not os.path.exists(config.FINALIZATION_DB_PATH)            # nothing finalized or created


# ---- P41 regressions: F1 (several unmatched warnings) and F2 (no-stock special diet) -------------------

def test_several_unexpected_warnings_never_crash_and_all_are_shown(monkeypatch):
    reports, inventory, needs, allocation = tool_outputs(monkeypatch)
    allocation = copy.deepcopy(allocation)
    extra = ["WH-Z: thermometer reading missing", "general: commitment cmt-999 refers to an unknown plan",
             "Data source note without any ID", "SH-09: shelter not in any report"]
    allocation["data_warnings"] += extra
    d = build_dashboard(reports, inventory, needs, allocation)          # F1: raised KeyError: 'other_note'
    notes = [a for a in d["actions"] if a["kind"] == "other_note"]
    assert [a["title"] for a in notes] == ["Data note: " + w for w in extra]   # the warning text is visible
    assert notes[0]["places"] == ["WH-Z"] and notes[2]["places"] == [] and notes[3]["places"] == ["SH-09"]
    assert d["details"]["data_warnings"] == allocation["data_warnings"]  # every warning listed
    page = text_of(render_dashboard(d))
    assert "Data note" in page


def test_no_stock_special_diet_is_labeled_a_shortage(data):
    shelters = SHELTERS + f"c,{V},S3,Three,2026-01-01T06:30+09:00,10,0,halal:5,\n"
    d = data(shelters, RICE.format(500))                                # no halal stock at all
    halal = next(x for x in d["plans"]["special_diets"] if x["diet_category"] == "halal")
    assert halal["status"] == "no_stock" and halal["demand"] == "known"
    action = next(a for a in d["actions"] if a["kind"] == "special_diet_shortage")
    assert action["severity"] == "shortage" and "15 short" in action["title"] and "None in stock" in action["why"]
    assert action["places"] == ["S3"]
    page = text_of(render_dashboard(d))
    table = page[page.index("Special diets (separate"):page.index("Shelter details")]
    assert "15 short (none in stock)" in table and "Enough in stock" not in table


def test_unknown_demand_is_distinct_from_confirmed_zero(data):
    shelters = (f"a,{V},S1,One,2026-01-01T06:00+09:00,10,0,halal:?,\n"
                f"b,{V},S2,Two,2026-01-01T06:00+09:00,10,0,infant_formula:2,infant_formula:6\n")
    inventory = RICE.format(500) + f"y,{V},W1,I2,Formula,f,infant_formula,pack,4,1,2026-01-01T05:00+09:00\n"
    d = data(shelters, inventory)
    by = {x["diet_category"]: x for x in d["plans"]["special_diets"]}
    assert by["halal"]["demand"] == "unknown" and by["infant_formula"]["demand"] == "zero"
    page = text_of(render_dashboard(d))
    table = page[page.index("Special diets (separate"):page.index("Shelter details")]
    assert "Halal unknown 0 ⚠️ count unknown" in table                   # not "0 needed"
    assert "Infant formula 0 4 No unmet need" in table                  # confirmed zero, not "unknown"


def test_items_without_any_validated_count_are_labeled_accurately(data):
    pending = ("p1,csv,2026-01-01T07:00+09:00,pending,,,W1,I1,Rice,meal,general,pack,60,1,2026-01-01T05:00+09:00\n"
               "p2,csv,2026-01-01T08:00+09:00,pending,,,W1,I1,Rice,meal,general,pack,50,1,2026-01-01T06:00+09:00\n")
    d = data(SHELTERS, pending)
    items = [a for a in d["actions"] if a["kind"] == "pending_inventory_count"]
    assert len(items) == 1                                              # one action per item, not per count
    assert items[0]["title"] == "No validated stock count for Rice at W1"
    assert "not included in available meals" in items[0]["why"] and "earlier count" not in items[0]["why"]
