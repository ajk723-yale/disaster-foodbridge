"""P41: reproduce dashboard defects F1/F2 (found in P40) and record before/after evidence.

    .venv/bin/python scripts/impact_eval/reproduce_dashboard_defects.py before
    .venv/bin/python scripts/impact_eval/reproduce_dashboard_defects.py after

Each scenario runs on isolated copies under evidence/impact/cases/D*/ (data/live and data/sample are
hashed before and after). Writes evidence/impact/dashboard_defects_<label>.json.
"""
import copy
import glob
import hashlib
import json
import os
import shutil
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from src import agent_tools, config  # noqa: E402
from src.dashboard import build_dashboard  # noqa: E402
from src.dashboard_map import load_training_locations, map_entities  # noqa: E402
from src.dashboard_view import render_dashboard  # noqa: E402

OUT = os.path.join(ROOT, "evidence", "impact")
CASES = os.path.join(OUT, "cases")
SAMPLE = os.path.join(ROOT, "data", "sample")
FILES = {"SHELTER_LOG_PATH": "shelter_log.csv", "INVENTORY_LOG_PATH": "inventory_log.csv",
         "COMMITMENTS_LOG_PATH": "commitments_log.csv"}
V = "csv,2026-10-24T05:00+09:00,validated,Eval,2026-10-24T05:10+09:00,"  # through supersedes ("" ); then source_text
UNEXPECTED = ["WH-Z: thermometer reading missing for cold storage",
              "general: commitment cmt-999 refers to an unknown plan",
              "Data source note without any ID"]


def hashes(folder):
    return {p: hashlib.sha256(open(p, "rb").read()).hexdigest()
            for p in sorted(glob.glob(os.path.join(folder, "**", "*"), recursive=True)) if os.path.isfile(p)}


def case_dir(name, source=SAMPLE, extra_shelter_rows=()):
    folder = os.path.join(CASES, name)
    if os.path.exists(folder):
        shutil.rmtree(folder)
    os.makedirs(folder)
    for f in FILES.values():
        shutil.copyfile(os.path.join(source, f), os.path.join(folder, f))
    for row in extra_shelter_rows:
        with open(os.path.join(folder, FILES["SHELTER_LOG_PATH"]), "a", encoding="utf-8") as fh:
            fh.write(row + "\n")
    return folder


def outputs(folder):
    for setting, f in FILES.items():
        setattr(config, setting, os.path.join(folder, f))
    config.FINALIZATION_DB_PATH = os.path.join(folder, "finalization.db")
    return (agent_tools.get_shelter_reports(), agent_tools.get_warehouse_inventory(),
            agent_tools.calculate_shelter_needs(), agent_tools.calculate_allocation())


def text_of(c):
    if isinstance(c, (str, int, float)):
        return str(c)
    if c is None:
        return ""
    if isinstance(c, (list, tuple)):
        return " ".join(text_of(x) for x in c)
    return text_of(getattr(c, "children", None))


def observe(name, description, tool_outputs, expect):
    allocation = tool_outputs[3]
    record = {"scenario": name, "description": description, "expected": expect,
              "special_diet_statuses": {d["diet_category"]: {"status": d["status"],
                                                             "known_unmet": d["total_unmet_meals_known"],
                                                             "available": d["available_meals"]}
                                        for d in allocation["special_diets"]},
              "data_warnings": allocation["data_warnings"]}
    try:
        d = build_dashboard(*tool_outputs)
        page = text_of(render_dashboard(d))
        start = page.index("Special diets (separate")
        record.update({
            "dashboard_builds": True, "error": None,
            "actions": [{"kind": a["kind"], "severity": a["severity"], "title": a["title"]} for a in d["actions"]],
            "special_table_text": page[start:page.index("Shelter details", start)].strip(),
            "data_notes_listed": d["details"]["data_warnings"],
            "every_warning_listed_in_data_notes": d["details"]["data_warnings"] == allocation["data_warnings"],
            "map_status": {e["id"]: e["status"] for e in map_entities(d, load_training_locations())},
        })
    except Exception as exc:
        record.update({"dashboard_builds": False, "error": f"{type(exc).__name__}: {exc}",
                       "traceback": traceback.format_exc(limit=4).replace(ROOT + os.sep, "<project>/")})
    return record


def main(label):
    guard = {"data/live": hashes(os.path.join(ROOT, "data", "live")), "data/sample": hashes(SAMPLE)}
    saved = {k: getattr(config, k) for k in (*FILES, "FINALIZATION_DB_PATH")}
    scenarios = []
    try:
        r3 = os.path.join(CASES, "R3_unknown_special_count")
        r7 = os.path.join(CASES, "R7_no_validated_inventory")
        scenarios.append(observe(
            "F1_R3_state", "P40 R3 final state: halal 5 people, 0 halal stock (2 unmatched warnings)",
            outputs(case_dir("D1_F1_R3_state", source=r3)),
            "dashboard builds; halal shortage listed as an action; every warning shown"))
        scenarios.append(observe(
            "F1_R7_state", "P40 R7 state: no validated inventory (several unmatched warnings)",
            outputs(case_dir("D2_F1_R7_state", source=r7)),
            "dashboard builds; special-diet shortages listed; every warning shown"))
        tools = list(outputs(case_dir("D3_F1_unexpected_warnings")))
        tools[3] = copy.deepcopy(tools[3])
        tools[3]["data_warnings"] += UNEXPECTED
        scenarios.append(observe(
            "F1_unexpected_warning_types", "Sample data + 3 unexpected warnings (unknown warehouse, unknown plan, "
            "no ID) injected into the allocation output", tools,
            "dashboard builds; each unexpected warning shown as a 'Data note' (the WH-Z one tied to WH-Z)"))
        scenarios.append(observe(
            "F2_no_stock_special_diet", "Sample + validated SH-03 report at 10:50 with halal 5 (need 15, 0 halal "
            "stock); only one unmatched warning, so F1 does not hide F2",
            outputs(case_dir("D4_F2_no_stock", extra_shelter_rows=[
                f"eval-d4,{V},,SH-03,Higashi Junior High Gym,2026-10-24T10:50+09:00,210,0,halal:5,,Eval,"])),
            "halal labeled as a shortage (15 short, none in stock) in the action list and the special-diet table"))
        scenarios.append(observe(
            "F2_unknown_vs_zero_demand", "Sample: halal count unknown (missing_info); infant formula with known "
            "demand covered by stock",
            outputs(case_dir("D5_F2_unknown_vs_zero")),
            "halal shown as unknown demand (not 0 needed); formula and allergy-free shown as enough in stock"))
        zero = outputs(case_dir("D6_F2_confirmed_zero_demand", extra_shelter_rows=[
            f"eval-d6,{V},,SH-01,Minami Elementary School,2026-10-24T11:30+09:00,135,25,infant_formula:3,"
            "infant_formula:9,Eval,"]))
        scenarios.append(observe(
            "F2_confirmed_zero_demand", "Sample + SH-01 report at 11:30 with 9 formula meals on hand for 3 infants "
            "(confirmed demand fully covered, unmet 0)", zero,
            "infant formula shown as no unmet need (confirmed zero), distinct from unknown"))
    finally:
        for k, v in saved.items():
            setattr(config, k, v)
    after = {"data/live": hashes(os.path.join(ROOT, "data", "live")), "data/sample": hashes(SAMPLE)}
    result = {"label": label, "scenarios": scenarios,
              "isolation": {"data_live_unchanged": guard["data/live"] == after["data/live"],
                            "data_sample_unchanged": guard["data/sample"] == after["data/sample"]}}
    path = os.path.join(OUT, f"dashboard_defects_{label}.json")
    json.dump(result, open(path, "w"), indent=2, ensure_ascii=False, default=str)
    for s in scenarios:
        print(s["scenario"], "builds" if s["dashboard_builds"] else s["error"],
              [a["kind"] for a in s.get("actions", [])], "|", (s.get("special_table_text") or "")[:160])
    print(result["isolation"])


if __name__ == "__main__":
    main(sys.argv[1])
