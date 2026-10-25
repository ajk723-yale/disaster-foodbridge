"""P31: evaluate the prompt-injection screen with real model calls.

1. The exact P30 inputs (baseline + attacks A and B), compared with the saved P30 run ("before").
2. Benign reports (evidence/safety/benign_reports_p31.json) to check for false positives.
Extraction, validation, and approval rules are the same as in P30; only the screen was added.
Writes evidence/safety/injection_defense_run_<UTC>.json. Live data is hashed before and after.

    .venv/bin/python scripts/run_injection_defense_eval.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.run_injection_eval import checks, live_hashes  # noqa: E402
from src import config  # noqa: E402
from src.extraction import extract_shelter_report  # noqa: E402
from src.timeutil import utc_now  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P30_RUN = "evidence/safety/injection_run_20261024T212735Z.json"
ROW_FIELDS = ["shelter_id", "shelter_name", "evacuee_count", "general_food_on_hand_meals", "special_needs",
              "special_food_on_hand", "reported_at_local", "reported_at_timezone"]


def layer_summary(screen):
    findings = screen["findings"] if screen else []
    return {
        "flagged": bool(findings),
        "pattern_flagged": any("pattern" in f["source"] for f in findings),
        "model_flagged": any("model" in f["source"] for f in findings),
        "categories": sorted({c for f in findings for c in f["categories"]}),
        "findings": [{"source": f["source"], "categories": f["categories"], "quote": f["quote"],
                      **({"quote_found_in_text": f["quote_found_in_text"]} if "quote_found_in_text" in f else {})}
                     for f in findings],
        "model_screen_error": (screen or {}).get("model_screen_error"),
    }


def run_case(case, received_at, expect_flag, facts=None, before=None):
    try:
        result = extract_shelter_report(case["text"], received_at)
    except Exception as exc:
        return {"id": case["id"], "input_text": case["text"], "error": f"{type(exc).__name__}: {exc}"}
    entry = {"id": case["id"], "title": case.get("title") or case.get("attack") or "baseline",
             "input_text": case["text"], "expected_flagged": expect_flag,
             "detection": layer_summary(result["safety_screen"]), "output": result,
             "usage": result["usage"], "usage_breakdown": result["usage_breakdown"]}
    entry["detection_correct"] = entry["detection"]["flagged"] == expect_flag
    if facts:
        entry["checks"] = checks(result, facts)
    if before:
        b = before["output"]["extracted"]
        a = result["extracted"]
        entry["before_after"] = {
            "before_flagged": False, "before_had_screen": False,
            "after_flagged": entry["detection"]["flagged"],
            "extracted_fields_differing_from_p30": [f for f in ROW_FIELDS if a[f] != b[f]],
            "shelter_row_same_as_p30": result["shelter_row"] == before["output"]["shelter_row"],
            "p30_model_issue_count": before["checks"]["model_issue_count"],
            "p31_model_issue_count": entry["checks"]["model_issue_count"],
        }
    return entry


def main():
    p30_inputs = json.load(open(os.path.join(ROOT, "evidence/safety/injection_inputs_p30.json"), encoding="utf-8"))
    benign = json.load(open(os.path.join(ROOT, "evidence/safety/benign_reports_p31.json"), encoding="utf-8"))
    p30_run = {r["id"]: r for r in json.load(open(os.path.join(ROOT, P30_RUN), encoding="utf-8"))["results"]}
    before = {"live_files": live_hashes(), "finalization_db_exists": os.path.exists(config.FINALIZATION_DB_PATH)}
    started = utc_now()
    run = {"run_started_at": started.isoformat(), "model": config.MODEL, "compared_with": P30_RUN,
           "defense": "src/injection_guard.py (pattern layer + model screen); extraction/validation/approval unchanged",
           "p30_cases": [], "benign_cases": []}
    for case in p30_inputs["cases"]:
        run["p30_cases"].append(run_case(case, p30_inputs["received_at"], case["attack"] is not None,
                                         p30_inputs["facts"], p30_run.get(case["id"])))
        print(case["id"], "done", flush=True)
    for case in benign["cases"]:
        run["benign_cases"].append(run_case(case, benign["received_at"], False))
        print(case["id"], "done", flush=True)
    after = {"live_files": live_hashes(), "finalization_db_exists": os.path.exists(config.FINALIZATION_DB_PATH)}
    run["isolation"] = {"before": before, "after": after, "live_data_unchanged": before == after}
    allc = run["p30_cases"] + run["benign_cases"]
    run["summary"] = {
        "attacks_detected": sum(1 for c in run["p30_cases"] if c.get("expected_flagged") and c["detection"]["flagged"]),
        "attacks_total": sum(1 for c in run["p30_cases"] if c.get("expected_flagged")),
        "false_positives": [c["id"] for c in allc if "detection" in c and c["detection"]["flagged"]
                            and not c["expected_flagged"]],
        "false_positives_by_layer": {
            "pattern": [c["id"] for c in allc if "detection" in c and not c["expected_flagged"]
                        and c["detection"]["pattern_flagged"]],
            "model": [c["id"] for c in allc if "detection" in c and not c["expected_flagged"]
                      and c["detection"]["model_flagged"]]},
        "errors": [c["id"] for c in allc if "error" in c],
        "total_usage": {k: sum(c.get("usage", {}).get(k, 0) for c in allc) for k in ("requests", "input_tokens",
                                                                                      "output_tokens")},
    }
    run["run_finished_at"] = utc_now().isoformat()
    out = os.path.join(ROOT, "evidence/safety", f"injection_defense_run_{started.strftime('%Y%m%dT%H%M%SZ')}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(run, f, ensure_ascii=False, indent=2, default=str)
    print(out)


if __name__ == "__main__":
    main()
