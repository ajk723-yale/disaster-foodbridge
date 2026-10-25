"""P40 impact evaluation: accuracy, reliability, efficiency on isolated copies of the sample data.

    .venv/bin/python scripts/run_impact_eval.py            # accuracy + reliability + planning timings
    .venv/bin/python scripts/run_impact_eval.py --extraction   # also real extraction calls (model + safety screen)

Isolation: every case gets its own folder under evidence/impact/cases/<case>/ with copies of the
sample CSVs and its own finalization database; config paths are pointed there for the case. The
usage log goes to evidence/impact/usage_log_impact.jsonl. data/live/ and data/sample/ are hashed
before and after and must be unchanged. No application code is modified.

Expected results come from scripts/impact_eval/expected.py, which does not import src/.
"""
import contextlib
import glob
import hashlib
import json
import os
import shutil
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts", "impact_eval"))

from expected import expected_results  # noqa: E402  (independent oracle)
from src import agent_tools, config  # noqa: E402
from src.dashboard import load_dashboard  # noqa: E402
from src.finalization import finalize_and_store, list_finalized_plans, review_plan  # noqa: E402
from src.intake import approve_extracted_report  # noqa: E402

OUT = os.path.join(ROOT, "evidence", "impact")
CASES = os.path.join(OUT, "cases")
SAMPLE = os.path.join(ROOT, "data", "sample")
LIVE = os.path.join(ROOT, "data", "live")
FILES = {"shelter": "shelter_log.csv", "inventory": "inventory_log.csv", "commitments": "commitments_log.csv"}
SH_HEADER = ("record_id,source,received_at,status,validated_by,validated_at,supersedes,source_text,shelter_id,"
             "shelter_name,reported_at,evacuee_count,general_on_hand_meals,special_needs,special_on_hand_meals,"
             "reporter,notes\n")
INV_HEADER = ("record_id,source,received_at,status,validated_by,validated_at,supersedes,source_text,warehouse_id,"
              "item_id,item_name,category,diet_tag,unit,quantity,meals_per_unit,counted_at,expiry_date,notes\n")
CM_HEADER = "commitment_id,plan_id,shelter_id,diet_tag,meals,status,committed_at,dispatched_at,warehouse_id,delivered_at\n"
V = "csv,2026-10-24T05:00+09:00,validated,Eval,2026-10-24T05:10+09:00,"  # ends at supersedes; rows add ",,"


# ---- isolation -------------------------------------------------------------------------------

def tree_hashes(folder):
    out = {}
    for path in sorted(glob.glob(os.path.join(folder, "**", "*"), recursive=True)):
        if os.path.isfile(path):
            out[os.path.relpath(path, ROOT)] = hashlib.sha256(open(path, "rb").read()).hexdigest()
    return out


def new_case(name, files=None):
    """Folder with copies of the sample CSVs (or the given contents) and no database."""
    folder = os.path.join(CASES, name)
    if os.path.exists(folder):
        shutil.rmtree(folder)
    os.makedirs(folder)
    paths = {k: os.path.join(folder, v) for k, v in FILES.items()}
    for k, p in paths.items():
        if files and k in files:
            open(p, "w", encoding="utf-8").write(files[k])
        else:
            shutil.copyfile(os.path.join(SAMPLE, FILES[k]), p)
    paths["db"] = os.path.join(folder, "finalization.db")
    return paths


@contextlib.contextmanager
def pointed_at(paths, window_hours=None):
    saved = {k: getattr(config, k) for k in ("SHELTER_LOG_PATH", "INVENTORY_LOG_PATH", "COMMITMENTS_LOG_PATH",
                                             "FINALIZATION_DB_PATH", "PLANNING_WINDOW_HOURS")}
    config.SHELTER_LOG_PATH, config.INVENTORY_LOG_PATH = paths["shelter"], paths["inventory"]
    config.COMMITMENTS_LOG_PATH, config.FINALIZATION_DB_PATH = paths["commitments"], paths["db"]
    if window_hours is not None:
        config.PLANNING_WINDOW_HOURS = window_hours
    try:
        yield
    finally:
        for k, v in saved.items():
            setattr(config, k, v)


def append(path, line):
    with open(path, "a", encoding="utf-8") as f:
        f.write(line if line.endswith("\n") else line + "\n")


# ---- app outputs in the oracle's shape ----------------------------------------------------------

def _num(v):
    return int(v) if isinstance(v, float) and v.is_integer() else v


def app_results():
    needs = agent_tools.calculate_shelter_needs()
    inv = agent_tools.get_warehouse_inventory()
    alloc = agent_tools.calculate_allocation()
    out_needs = {}
    for r in needs["general_meals"]["shelters"]:
        out_needs.setdefault(r["shelter_id"], {})["general"] = {
            "people": _num(r["people"]), "need": _num(r["need_meals"]), "on_hand": _num(r["on_hand_at_report_meals"]),
            "on_its_way": _num(r["still_on_its_way_meals"]),
            "delivered_after_report": _num(r["delivered_after_report_meals"]), "unmet": _num(r["unmet_meals"])}
    for d in needs["special_diets"]:
        for r in d["shelters"]:
            row = {"people": _num(r["people"]), "need": _num(r["need_meals"]), "unmet": _num(r["unmet_meals"])}
            if r["need_meals"] is not None:
                row.update({"on_hand": _num(r["on_hand_at_report_meals"]), "on_its_way": _num(r["still_on_its_way_meals"]),
                            "delivered_after_report": _num(r["delivered_after_report_meals"])})
            out_needs.setdefault(r["shelter_id"], {})[d["diet_category"]] = row
    stock = {k: {"counted": _num(v["counted_meal_equivalents"]), "dispatched_since_count": _num(v["dispatched_since_count"]),
                 "reserved": _num(v["reserved_approved_not_dispatched"]), "available": _num(v["available_meal_equivalents"])}
             for k, v in inv["meal_totals_by_diet_category"].items()}
    g = alloc["general_meals"]
    procurement = alloc["plan_b_additional_procurement_meals"]
    special = {}
    for d in alloc["special_diets"]:
        p = procurement.get(d["diet_category"])
        special[d["diet_category"]] = {
            "status": d["status"], "known_unmet": _num(d["total_unmet_meals_known"]), "available": _num(d["available_meals"]),
            "known_shortage": _num(d["shortage_meals_known"]),
            "plan_a": ({s["shelter_id"]: _num(s["plan_a_meals"]) for s in d["shelters"]}
                       if all(s["plan_a_meals"] is not None for s in d["shelters"]) else None),
            "procurement": "unknown" if isinstance(p, str) and "unknown" in p else _num(p)}
    return {
        "needs": out_needs, "stock": stock,
        "general": {"available": _num(g["available_meals"]), "total_unmet": _num(g["total_unmet_meals"]),
                    "plan_a": {s["shelter_id"]: _num(s["plan_a_meals"]) for s in g["shelters"]},
                    "plan_a_total": _num(g["plan_a_total_meals"]),
                    "shortfall": {s["shelter_id"]: _num(s["plan_a_shortfall_meals"]) for s in g["shelters"]},
                    "procurement": _num(procurement.get("general"))},
        "special": special,
        "_raw": {"needs_flags": needs["flags"], "missing": needs.get("shelters_without_validated_report", []),
                 "warnings": alloc["data_warnings"], "fingerprint": alloc["plan_fingerprint"],
                 "inventory_flags": inv["flags"], "inventory_note": inv.get("note")},
    }


def flatten(d, prefix=""):
    out = {}
    for k, v in d.items():
        path = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(flatten(v, path + "."))
        else:
            out[path] = v
    return out


# Equivalences applied when comparing (recorded in the results): the app splits "not enough stock" into
# "shortage" (some stock) and "no_stock" (none); the oracle has one status for both.
STATUS_EQUIVALENTS = {"no_stock": "shortage"}


def compare(expected, actual):
    """Field-by-field comparison on every field the oracle computes. A stock category with nothing counted
    may be absent from the app's inventory summary (it reports only categories with validated counts)."""
    e = flatten({k: v for k, v in expected.items()})
    a = flatten({k: v for k, v in actual.items() if not k.startswith("_")})
    mismatches, skipped = [], []
    for f in e:
        got = a.get(f, "<missing>")
        if f.endswith(".status"):
            got = STATUS_EQUIVALENTS.get(got, got)
        if got == "<missing>" and f.startswith("stock.") and expected["stock"][f.split(".")[1]]["counted"] == 0:
            skipped.append(f)
            continue
        if got != e[f]:
            mismatches.append({"field": f, "expected": e[f], "actual": got})
    return {"fields_compared": len(e) - len(skipped), "fields_skipped_absent_zero_stock": skipped,
            "mismatches": mismatches, "pass": not mismatches}


def dashboard_check(paths, expect_action_kinds=()):
    """The dashboard's view model must build from this state (it is what staff see first)."""
    with pointed_at(paths):
        try:
            d = load_dashboard()
            kinds = [a["kind"] for a in d["actions"]]
            error = None
        except Exception as exc:
            kinds, error = None, f"{type(exc).__name__}: {exc}"
    checks = [check("dashboard builds from this state", error is None, "builds", error or "builds")]
    for kind in expect_action_kinds:
        checks.append(check(f"dashboard lists a '{kind}' action", kinds is not None and kind in kinds, kind,
                            kinds if kinds is not None else "dashboard not built"))
    return checks


def headline(r):
    g = r["general"]
    return {"available_general": g["available"], "total_unmet_general": g["total_unmet"], "plan_a": g["plan_a"],
            "procurement_general": g["procurement"],
            "special": {k: (v["status"], v["procurement"]) for k, v in r["special"].items()}}


def accuracy_case(case_id, description, files=None, edit=None, window_hours=None):
    paths = new_case(case_id, files)
    if edit:
        edit(paths)
    with pointed_at(paths, window_hours):
        actual = app_results()
    exp = expected_results(paths["shelter"], paths["inventory"], paths["commitments"],
                           window_hours=window_hours or config.PLANNING_WINDOW_HOURS,
                           meals_per_day=config.MEALS_PER_PERSON_PER_DAY)
    result = compare(exp, actual)
    return {"case": case_id, "description": description, "inputs": os.path.relpath(os.path.dirname(paths["db"]), ROOT),
            "planning_window_hours": window_hours or config.PLANNING_WINDOW_HOURS,
            "expected_headline": headline(exp), "actual_headline": headline(actual), **result,
            "expected_full": exp, "actual_full": {k: v for k, v in actual.items() if k != "_raw"}}


# ---- accuracy cases ------------------------------------------------------------------------------

def accuracy():
    cases = [accuracy_case("A1_sample", "Sample data as provided (2 warehouses, recount, delivered-after-report, "
                                         "reserved, cancelled, rejected and pending records)")]
    cases.append(accuracy_case(
        "A2_ample_stock", "Sample + a newer validated WH-B rice count of 600 packs (stock exceeds unmet demand)",
        edit=lambda p: append(p["inventory"], f"eval-a2,{V},,WH-B,ITM-RICE,Alpha rice (retort),ready_meal,general,"
                                              f"pack,600,1,2026-10-24T12:00+09:00,2027-03-31,")))
    tie = SH_HEADER + "".join(f"t{i},{V},,T{i},Tie {i},2026-10-24T06:00+09:00,10,0,,,," + "\n" for i in (1, 2, 3))
    cases.append(accuracy_case(
        "A3_tie_break", "Three equal shelters (unmet 30 each), 10 meals in stock: equal remainders, tie by shelter_id",
        files={"shelter": tie, "inventory": INV_HEADER + f"i1,{V},,W1,R,Rice,ready_meal,general,pack,10,1,"
                                                         "2026-10-24T05:00+09:00,,\n", "commitments": CM_HEADER}))
    short = SH_HEADER + (f"s1,{V},,S1,One,2026-10-24T06:00+09:00,20,10,infant_formula:5,,,\n"
                         f"s2,{V},,S2,Two,2026-10-24T06:00+09:00,30,0,infant_formula:3,,,\n")
    cases.append(accuracy_case(
        "A4_special_shortage", "Infant formula needed 24 meals, 10 in stock (special-diet shortage); general stock ample",
        files={"shelter": short,
               "inventory": INV_HEADER + (f"i1,{V},,W1,R,Rice,ready_meal,general,pack,500,1,2026-10-24T05:00+09:00,,\n"
                                          f"i2,{V},,W1,F,Formula,infant_formula,infant_formula,pack,10,1,"
                                          "2026-10-24T05:00+09:00,,\n"),
               "commitments": CM_HEADER}))
    frac = SH_HEADER + f"f1,{V},,S1,One,2026-10-24T08:00+09:00,7,0,,,,\n"
    frac_inv = INV_HEADER + (f"i1,{V},,W1,H,Half-meal pack,ready_meal,general,pack,7,0.5,2026-10-24T05:00+09:00,,\n"
                             f"i2,{V},,W1,R,Rice,ready_meal,general,pack,10,1,2026-10-24T05:00+09:00,,\n")
    frac_cm = CM_HEADER + ("c1,P,S1,general,5,delivered,2026-10-24T06:00+09:00,2026-10-24T06:30+09:00,W0,"
                           "2026-10-24T07:00+09:00\n"
                           "c2,P,S1,general,2,delivered,2026-10-24T06:00+09:00,2026-10-24T08:30+09:00,W0,"
                           "2026-10-24T09:00+09:00\n")
    cases.append(accuracy_case(
        "A5_rounding_and_delivery_timing", "Fractional meals per unit (stock 13.5 rounds down to 13); deliveries "
        "before vs after the report time", files={"shelter": frac, "inventory": frac_inv, "commitments": frac_cm}))
    cases.append(accuracy_case(
        "A6_planning_window_12h", "Sample data with a 12-hour planning window (need = ceil(people x 1.5))",
        window_hours=12))
    return cases


# ---- reliability cases -----------------------------------------------------------------------------

def check(name, ok, expected, actual):
    return {"check": name, "expected": expected, "actual": actual, "pass": bool(ok)}


def extraction_like(text, row):
    return {"source_text": text, "received_at": "2026-10-24T03:00:00+00:00", "shelter_row": row}


def reliability():
    results = []

    paths = new_case("R1_missing_report")
    with pointed_at(paths):
        a, d = app_results(), load_dashboard()
    kinds = [x["kind"] for x in d["actions"] if "SH-04" in x["places"]]
    results.append({"case": "R1_missing_report", "description": "SH-04 has only a pending report", "checks": [
        check("SH-04 excluded from needs", "SH-04" not in a["needs"], "absent", sorted(a["needs"])),
        check("SH-04 excluded from Plan A", "SH-04" not in a["general"]["plan_a"], "absent", a["general"]["plan_a"]),
        check("listed as without validated report", [m["shelter_id"] for m in a["_raw"]["missing"]] == ["SH-04"],
              ["SH-04"], [m["shelter_id"] for m in a["_raw"]["missing"]]),
        check("data warning names SH-04", any(w.startswith("SH-04") for w in a["_raw"]["warnings"]), True,
              [w for w in a["_raw"]["warnings"] if "SH-04" in w]),
        check("dashboard action 'missing_report'", kinds == ["missing_report"], ["missing_report"], kinds)]})

    paths = new_case("R2_pending_update")
    with pointed_at(paths):
        before = app_results()
        fp_before = before["_raw"]["fingerprint"]
        saved = approve_extracted_report(paths["shelter"], extraction_like(
            "Kita CC update 11:00 - about 80 people now, food ok", {}), {
            "shelter_id": "SH-02", "shelter_name": "Kita Community Center", "reported_at": "2026-10-24 11:00",
            "evacuee_count": "80", "general_on_hand_meals": "90", "special_needs": "", "special_on_hand_meals": ""},
            "Eval", at="2026-10-24T03:30:00+00:00")
        after = app_results()
    exp_after = expected_results(paths["shelter"], paths["inventory"], paths["commitments"])
    results.append({"case": "R2_pending_update", "description": "SH-02 has a newer pending report (80 people); then staff "
                    "approve an 80-person report through the normal intake function", "checks": [
        check("before: uses the validated 64-person report", before["needs"]["SH-02"]["general"]["people"] == 62,
              62, before["needs"]["SH-02"]["general"]["people"]),
        check("before: pending warning for SH-02", any(w.startswith("SH-02") and "pending" in w
                                                       for w in before["_raw"]["warnings"]), True,
              [w for w in before["_raw"]["warnings"] if w.startswith("SH-02")]),
        check("approval saved through intake", saved["status"] == "saved", "saved", saved["status"]),
        check("after: needs follow the new validated report (oracle)", compare(exp_after, after)["pass"], "match",
              compare(exp_after, after)["mismatches"] or "match"),
        check("after: SH-02 unmet 240-90-30 = 120", after["needs"]["SH-02"]["general"]["unmet"] == 120, 120,
              after["needs"]["SH-02"]["general"]["unmet"]),
        check("after: plan fingerprint changed", after["_raw"]["fingerprint"] != fp_before, "changed",
              "changed" if after["_raw"]["fingerprint"] != fp_before else "same"),
        check("after: no 'pending validation' warning for SH-02 (pending report is no longer newer)",
              not any(w.startswith("SH-02") and "pending validation" in w for w in after["_raw"]["warnings"]), [],
              [w for w in after["_raw"]["warnings"] if w.startswith("SH-02") and "pending validation" in w]),
        {"check": "observation: other SH-02 warnings after the update", "expected": None, "pass": None,
         "actual": [w for w in after["_raw"]["warnings"] if w.startswith("SH-02")]},
        *dashboard_check(paths)]})

    paths = new_case("R3_unknown_special_count")
    with pointed_at(paths):
        before = app_results()
        saved = approve_extracted_report(paths["shelter"], extraction_like("SH-03 12:00 210 people, halal 5", {}), {
            "shelter_id": "SH-03", "shelter_name": "Higashi Junior High Gym", "reported_at": "2026-10-24 12:00",
            "evacuee_count": "210", "general_on_hand_meals": "0", "special_needs": "halal:5",
            "special_on_hand_meals": ""}, "Eval", at="2026-10-24T03:30:00+00:00")
        after = app_results()
    exp_after = expected_results(paths["shelter"], paths["inventory"], paths["commitments"])
    results.append({"case": "R3_unknown_special_count", "description": "SH-03 halal count unknown; then a validated "
                    "report states halal 5", "checks": [
        check("before: halal status missing_info", before["special"]["halal"]["status"] == "missing_info",
              "missing_info", before["special"]["halal"]["status"]),
        check("before: halal procurement unknown (not 0)", before["special"]["halal"]["procurement"] == "unknown",
              "unknown", before["special"]["halal"]["procurement"]),
        check("before: no halal Plan A lines", before["special"]["halal"]["plan_a"] is None, None,
              before["special"]["halal"]["plan_a"]),
        check("before: general need uses all 210 people and is flagged as possibly overstated",
              before["needs"]["SH-03"]["general"]["people"] == 210 and any("overstated" in f for f in before["_raw"]["needs_flags"]),
              "210 + flag", [before["needs"]["SH-03"]["general"]["people"],
                             [f for f in before["_raw"]["needs_flags"] if "overstated" in f]]),
        check("approval saved", saved["status"] == "saved", "saved", saved["status"]),
        check("after: matches oracle (halal need 15, stock 0 -> shortage 15; general 205 people)",
              compare(exp_after, after)["pass"], "match", compare(exp_after, after)["mismatches"] or "match"),
        check("after: halal shortage requires procurement 15", after["special"]["halal"]["procurement"] == 15, 15,
              after["special"]["halal"]["procurement"]),
        {"check": "observation: app status for halal (need 15, stock 0)", "expected": "shortage or no_stock",
         "actual": after["special"]["halal"]["status"], "pass": None},
        *dashboard_check(paths, ["special_diet_shortage"])]})

    paths = new_case("R4_change_during_review_and_finalize")
    cfg = agent_tools.planning_config()
    with pointed_at(paths):
        reviewed = review_plan(paths["db"], paths["shelter"], paths["inventory"], paths["commitments"], cfg)
        append(paths["shelter"], f"eval-r4,{V},,SH-01,Minami Elementary School,2026-10-24T12:00+09:00,150,25,"
                                 "infant_formula:3,infant_formula:4,Eval,")
        stale = finalize_and_store(paths["db"], paths["shelter"], paths["inventory"], paths["commitments"], cfg,
                                   reviewed["fingerprint"], "Eval", "2026-10-24T03:40:00+00:00")
        plans_after_stale = list_finalized_plans(paths["db"])
        fresh = review_plan(paths["db"], paths["shelter"], paths["inventory"], paths["commitments"], cfg)
        acks = [{"warning_id": w["warning_id"], "reason": "evaluation: acknowledged"} for w in fresh["pending_data_warnings"]]
        no_ack = finalize_and_store(paths["db"], paths["shelter"], paths["inventory"], paths["commitments"], cfg,
                                    fresh["fingerprint"], "Eval", "2026-10-24T03:41:00+00:00")
        done = finalize_and_store(paths["db"], paths["shelter"], paths["inventory"], paths["commitments"], cfg,
                                  fresh["fingerprint"], "Eval", "2026-10-24T03:42:00+00:00", acknowledgements=acks)
        again = finalize_and_store(paths["db"], paths["shelter"], paths["inventory"], paths["commitments"], cfg,
                                   fresh["fingerprint"], "Eval", "2026-10-24T03:43:00+00:00", acknowledgements=acks)
        after = app_results()
    # Oracle view after finalization: the finalized general approvals are approved (reserved, on their way)
    stored = done.get("commitments")
    stored = [] if stored is None else stored[stored["status"] == "approved"].to_dict("records")  # the new approvals
    cm_copy = os.path.join(os.path.dirname(paths["db"]), "oracle_commitments_after_finalize.csv")
    shutil.copyfile(paths["commitments"], cm_copy)
    for c in stored:
        committed = c.get("committed_at")
        committed = committed.isoformat() if hasattr(committed, "isoformat") else (committed or "")
        append(cm_copy, f"{c['commitment_id']},{c['plan_id']},{c['shelter_id']},{c['diet_tag']},{_num(c['meals'])},"
                        f"approved,{committed},,,")
    exp_after = expected_results(paths["shelter"], paths["inventory"], cm_copy)
    results.append({"case": "R4_change_during_review_and_finalize", "description": "A validated SH-01 report arrives "
                    "after staff reviewed the plan; finalization must ask for reconfirmation; then finalize the fresh "
                    "plan in the isolated database", "checks": [
        check("stale review -> needs_confirmation", stale["status"] == "needs_confirmation", "needs_confirmation",
              stale["status"]),
        check("nothing stored after stale attempt", plans_after_stale == [], [], plans_after_stale),
        check("fresh plan reflects 150 evacuees (147 general people)",
              next(l for l in fresh["general"]["lines"] if l["shelter_id"] == "SH-01")["people"] == 147, 147,
              next(l for l in fresh["general"]["lines"] if l["shelter_id"] == "SH-01")["people"]),
        check("unacknowledged warnings block finalization", no_ack["status"] == "acknowledgement_required",
              "acknowledgement_required", no_ack["status"]),
        check("finalized with acknowledgements", done["status"] == "finalized", "finalized", done["status"]),
        check("repeat finalize -> already_finalized", again["status"] == "already_finalized", "already_finalized",
              again["status"]),
        check("after finalization the approvals are counted (oracle with approvals as reserved)",
              compare(exp_after, after)["pass"], "match", compare(exp_after, after)["mismatches"] or "match"),
        check("one plan stored", len(list_finalized_plans(paths["db"])) == 1, 1, len(list_finalized_plans(paths["db"]))),
        *dashboard_check(paths)]})

    paths = new_case("R5_rejected_and_pending_ignored")
    with pointed_at(paths):
        a = app_results()
    results.append({"case": "R5_rejected_and_pending_ignored", "description": "Rejected typos (SH-03 2100 people; WH-A "
                    "rice 3000) and a pending WH-A bread recount (6 cases) must not be used", "checks": [
        check("SH-03 uses 210 people, not 2100", a["needs"]["SH-03"]["general"]["people"] == 210, 210,
              a["needs"]["SH-03"]["general"]["people"]),
        check("general counted 660 (rice 300 + bread 240 + WH-B rice 120)", a["stock"]["general"]["counted"] == 660, 660,
              a["stock"]["general"]["counted"]),
        check("pending bread count flagged as pending", any("ITM-BREAD" in w for w in a["_raw"]["warnings"]), True,
              [w for w in a["_raw"]["warnings"] if "ITM-BREAD" in w]),
        *dashboard_check(paths, ["missing_report", "unknown_special_count", "pending_report", "pending_inventory_count"])]})

    paths = new_case("R6_invalid_staff_entry")
    before_hash = hashlib.sha256(open(paths["shelter"], "rb").read()).hexdigest()
    with pointed_at(paths):
        bad = approve_extracted_report(paths["shelter"], extraction_like("SH-01 report", {}), {
            "shelter_id": "SH-01", "shelter_name": "Minami Elementary School", "reported_at": "2026-10-24 12:00",
            "evacuee_count": "abc", "general_on_hand_meals": "10", "special_needs": "", "special_on_hand_meals": ""},
            "Eval", at="2026-10-24T03:30:00+00:00")
    unchanged = hashlib.sha256(open(paths["shelter"], "rb").read()).hexdigest() == before_hash
    results.append({"case": "R6_invalid_staff_entry", "description": "Staff approve a report with a non-numeric evacuee "
                    "count", "checks": [
        check("rejected as invalid", bad["status"] == "invalid", "invalid", [bad["status"], bad.get("errors")]),
        check("shelter log unchanged", unchanged, True, unchanged)]})

    paths = new_case("R7_no_validated_inventory")
    inv_pending = INV_HEADER + "".join(
        line.replace(",validated,", ",pending,", 1) + "\n"
        for line in open(os.path.join(SAMPLE, FILES["inventory"]), encoding="utf-8").read().splitlines()[1:])
    open(paths["inventory"], "w", encoding="utf-8").write(inv_pending)
    with pointed_at(paths):
        a = app_results()
    exp = expected_results(paths["shelter"], paths["inventory"], paths["commitments"])
    results.append({"case": "R7_no_validated_inventory", "description": "All inventory counts are pending (none "
                    "validated)", "checks": [
        check("general available 0", a["general"]["available"] == 0, 0, a["general"]["available"]),
        check("Plan A allocates nothing", a["general"]["plan_a_total"] == 0, 0, a["general"]["plan_a_total"]),
        check("procurement = total unmet", a["general"]["procurement"] == a["general"]["total_unmet"],
              a["general"]["total_unmet"], a["general"]["procurement"]),
        check("matches oracle", compare(exp, a)["pass"], "match", compare(exp, a)["mismatches"] or "match"),
        check("no-inventory note shown", bool(a["_raw"]["inventory_note"]), "note", a["_raw"]["inventory_note"]),
        *dashboard_check(paths)]})

    paths = new_case("R8_partial_recount_EXPLORATORY")
    append(paths["inventory"], f"eval-r8,{V},,WH-A,ITM-BREAD,Canned bread,ready_meal,general,case,6,24,"
                               "2026-10-24T12:00+09:00,2028-01-31,")
    with pointed_at(paths):
        a = app_results()
    exp = expected_results(paths["shelter"], paths["inventory"], paths["commitments"])
    results.append({"case": "R8_partial_recount_EXPLORATORY", "exploratory": True,
                    "description": "WH-A bread is recounted at 12:00 (6 cases); WH-A rice was last counted at 06:30; a "
                    "general dispatch left WH-A at 11:00. The documented rule ('dispatches after the warehouse's latest "
                    "count') does not say whether a recount of one item reflects a dispatch whose item is unknown.",
                    "app_follows": ("dispatch deducted (conservative)" if a["general"]["available"] == 500 else
                                    "dispatch not deducted" if a["general"]["available"] == exp["general"]["available"]
                                    else "neither reading"),
                    "checks": [
        {"check": "reading 1 (warehouse+diet latest count = 12:00, dispatch not deducted): available "
                  f"{exp['general']['available']}", "expected": exp["general"]["available"],
         "actual": a["general"]["available"], "pass": None},
        {"check": "reading 2 (the dispatched item's own count 06:30, dispatch deducted): available 500", "expected": 500,
         "actual": a["general"]["available"], "pass": None},
        *dashboard_check(paths)]})
    return results


# ---- efficiency ------------------------------------------------------------------------------------

def timed(fn, runs):
    fn()                                                      # warm-up (imports, caches)
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    return {"runs": runs, "median_ms": round(statistics.median(times), 2),
            "p95_ms": round(times[max(0, int(round(0.95 * runs)) - 1)], 2), "min_ms": round(times[0], 2),
            "max_ms": round(times[-1], 2)}


def planning_timings(runs=30):
    paths = new_case("E1_planning_timing")
    cfg = agent_tools.planning_config()
    with pointed_at(paths):
        out = {
            "calculate_shelter_needs": timed(agent_tools.calculate_shelter_needs, runs),
            "get_warehouse_inventory": timed(agent_tools.get_warehouse_inventory, runs),
            "calculate_allocation (Plan A + B)": timed(agent_tools.calculate_allocation, runs),
            "prepare_supply_request": timed(agent_tools.prepare_supply_request, runs),
            "review_plan (finalization review)": timed(
                lambda: review_plan(paths["db"], paths["shelter"], paths["inventory"], paths["commitments"], cfg), runs),
            "load_dashboard (all dashboard figures)": timed(load_dashboard, runs),
        }
        fin = []
        for i in range(5):
            db = os.path.join(os.path.dirname(paths["db"]), f"finalize_{i}.db")
            plan = review_plan(db, paths["shelter"], paths["inventory"], paths["commitments"], cfg)
            acks = [{"warning_id": w["warning_id"], "reason": "timing run"} for w in plan["pending_data_warnings"]]
            t0 = time.perf_counter()
            r = finalize_and_store(db, paths["shelter"], paths["inventory"], paths["commitments"], cfg, plan["fingerprint"],
                                   "Eval", "2026-10-24T03:45:00+00:00", acknowledgements=acks)
            fin.append((time.perf_counter() - t0) * 1000)
            assert r["status"] == "finalized", r["status"]
        fin.sort()
        out["finalize_and_store (SQLite, fresh DB each run)"] = {
            "runs": 5, "median_ms": round(statistics.median(fin), 2), "min_ms": round(fin[0], 2), "max_ms": round(fin[-1], 2)}
    return {"scope": "automated processing only, on the sample data size (4 shelters, 9 inventory rows, 5 commitments)",
            "machine": {"python": sys.version.split()[0], "platform": sys.platform}, "timings": out}


NEW_REPORTS = [
    ("N1", "Minami Elementary School (SH-01) report 24 Oct 2026 17:10 JST: 128 evacuees, 30 meals left. "
           "3 infants need formula, 2 formula packs left. Reporter: Sato"),
    ("N2", "Kita CC (SH-02) at 17:20 JST - 70 people tonight. About 40 meals. 2 allergy-free needed, none left."),
    ("N3", "東小学校体育館（SH-03）10月24日17時30分 避難者205名。食料なし。ハラール対応が必要な方は6名。報告者：小林"),
    ("N4", "Nishi Public Hall SH-04, 24/10 17:40 JST. Headcount 52 (some still arriving). Meals on hand: 12."),
    ("N5", "SH-01 Minami ES, 17:50 JST: correction to the 17:10 report, evacuees are 131 not 128. Meals unchanged at 30."),
]


def extraction_timings():
    from src.extraction import extract_shelter_report
    config.USAGE_LOG_PATH = os.path.join(OUT, "usage_log_impact.jsonl")
    log = config.USAGE_LOG_PATH
    sample = json.load(open(os.path.join(SAMPLE, "free_text_reports.json")))
    jobs = [("sample:" + r["id"], r["text"], sample["received_at"]) for r in sample["reports"]]
    jobs += [("new:" + k, text, "2026-10-24T18:00+09:00") for k, text in NEW_REPORTS]
    rows = []
    for job_id, text, received in jobs:
        before = len(open(log).read().splitlines()) if os.path.exists(log) else 0
        t0 = time.perf_counter()
        try:
            r = extract_shelter_report(text, received)
            error = None
        except Exception as exc:  # recorded as a failure, not hidden
            r, error = None, f"{type(exc).__name__}: {exc}"
        wall = (time.perf_counter() - t0) * 1000
        calls = [json.loads(x) for x in open(log).read().splitlines()[before:]] if os.path.exists(log) else []
        rows.append({
            "job": job_id, "wall_ms_total": round(wall), "error": error,
            "calls": [{"workflow": c["workflow"], "latency_ms": c["latency_ms"],
                       "portkey_cache_status": c["headers"].get("x-portkey-cache-status"),
                       "input_tokens": c["usage"]["input_tokens"], "output_tokens": c["usage"]["output_tokens"]}
                      for c in calls],
            "issues": len(r["issues"]) if r else None,
            "extracted_row": r["shelter_row"] if r else None,
        })
        print(job_id, round(wall), [(c["workflow"], c["headers"].get("x-portkey-cache-status"), c["latency_ms"])
                                    for c in calls], error or "")

    def summary(pred):
        sel = [x for x in rows if pred(x) and not x["error"]]
        walls = [x["wall_ms_total"] for x in sel]
        return {"reports": len(sel), "median_wall_ms": statistics.median(walls) if walls else None,
                "min_wall_ms": min(walls) if walls else None, "max_wall_ms": max(walls) if walls else None}
    all_miss = lambda x: x["calls"] and all(c["portkey_cache_status"] == "MISS" for c in x["calls"])  # noqa: E731
    any_hit = lambda x: any(c["portkey_cache_status"] == "HIT" for c in x["calls"])  # noqa: E731
    return {"scope": "automated processing per report: AI extraction + AI safety screen + code checks; staff review "
                     "and approval time NOT measured",
            "reports": rows,
            "summary_provider_calls_only (all calls MISS)": summary(all_miss),
            "summary_with_portkey_cache_hits (not model processing time)": summary(any_hit),
            "failures": [x for x in rows if x["error"]]}


def main():
    os.makedirs(CASES, exist_ok=True)
    guard_before = {"data/live": tree_hashes(LIVE), "data/sample": tree_hashes(SAMPLE)}
    live_db_before = os.path.exists(os.path.join(LIVE, "finalization.db"))
    result = {"date": "2026-10-24", "accuracy": accuracy(), "reliability": reliability(),
              "planning_efficiency": planning_timings()}
    if "--extraction" in sys.argv:
        result["extraction_efficiency"] = extraction_timings()
    guard_after = {"data/live": tree_hashes(LIVE), "data/sample": tree_hashes(SAMPLE)}
    result["isolation"] = {
        "data_live_unchanged": guard_before["data/live"] == guard_after["data/live"],
        "data_sample_unchanged": guard_before["data/sample"] == guard_after["data/sample"],
        "live_finalization_db_existed_before": live_db_before,
        "live_finalization_db_exists_after": os.path.exists(os.path.join(LIVE, "finalization.db")),
        "files_hashed": {k: len(v) for k, v in guard_after.items()}}
    result["human_review_time"] = "NOT MEASURED. No staff were timed reviewing extractions, acknowledging warnings, or " \
                                  "finalizing plans; no productivity comparison is made."
    json.dump(result, open(os.path.join(OUT, "impact_eval_results.json"), "w"), indent=2, ensure_ascii=False, default=str)
    acc = [(c["case"], c["pass"], len(c["mismatches"])) for c in result["accuracy"]]
    rel = [(c["case"], sum(1 for k in c["checks"] if k["pass"] is True), sum(1 for k in c["checks"] if k["pass"] is False),
            sum(1 for k in c["checks"] if k["pass"] is None)) for c in result["reliability"]]
    print("accuracy", acc)
    print("reliability (pass, fail, exploratory)", rel)
    print("isolation", result["isolation"])


if __name__ == "__main__":
    main()
