"""Run warehouse photo analysis on the synthetic sample images (real model calls) and save evidence.

Analyses (with exact image copies) are stored under evidence/vision/analyses/ instead of
data/live/photos/, so the report can cite them. Inventory records are only read.

    .venv/bin/python scripts/run_vision_examples.py
    .venv/bin/python scripts/run_vision_examples.py --recompare evidence/vision/<run>.json

--recompare re-applies the current comparison rules to the model outputs saved in a run
(no model calls) and writes <run>_recompared.json next to it.
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config, vision  # noqa: E402
from src.timeutil import utc_now  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHOTOS = [("synthetic_wh_a_aisle2.png", "WH-A"), ("synthetic_wh_b_bay1.png", "WH-B")]
FOLLOWUP = ("synthetic_wh_a_aisle2.png", "Is there any item whose label you could not read? Where is it, and what "
                                         "would staff need to check?")


def main():
    config.PHOTO_DIR = os.path.join(ROOT, "evidence", "vision", "analyses")
    inventory_hash = hashlib.sha256(open(config.INVENTORY_LOG_PATH, "rb").read()).hexdigest()
    started = utc_now()
    run = {"run_started_at": started.isoformat(), "inventory_log": os.path.relpath(config.INVENTORY_LOG_PATH, ROOT),
           "inventory_sha256_before": inventory_hash, "results": [], "followups": []}
    ids = {}
    for name, warehouse in PHOTOS:
        path = os.path.join(ROOT, "data", "sample_photos", name)
        try:
            record = vision.analyze_warehouse_photo(path, warehouse, taken_at="2026-10-24T15:30+09:00")
            ids[name] = record["analysis_id"]
            record["stored_in"] = os.path.relpath(record["stored_in"], ROOT)
            run["results"].append(record)
        except Exception as exc:
            run["results"].append({"image": name, "error": f"{type(exc).__name__}: {exc}"})
        print(name, "done", flush=True)
    if FOLLOWUP[0] in ids:
        try:
            run["followups"].append({"analysis_id": ids[FOLLOWUP[0]],
                                     **vision.ask_about_photo(ids[FOLLOWUP[0]], FOLLOWUP[1])})
        except Exception as exc:
            run["followups"].append({"error": f"{type(exc).__name__}: {exc}"})
    run["inventory_sha256_after"] = hashlib.sha256(open(config.INVENTORY_LOG_PATH, "rb").read()).hexdigest()
    run["run_finished_at"] = utc_now().isoformat()
    usages = [r.get("usage", {}) for r in run["results"]] + [f.get("usage", {}) for f in run["followups"]]
    run["total_usage"] = {k: sum(u.get(k, 0) for u in usages) for k in ("requests", "input_tokens", "output_tokens")}
    out = os.path.join(ROOT, "evidence", "vision", f"vision_run_{started.strftime('%Y%m%dT%H%M%SZ')}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(run, f, ensure_ascii=False, indent=2)
    print(out)


def recompare(path):
    from src.store import load_inventory_log
    with open(path, encoding="utf-8") as f:
        run = json.load(f)
    inventory_log, _ = load_inventory_log(config.INVENTORY_LOG_PATH)
    for r in run["results"]:
        if "analysis" in r:
            r["comparison"] = vision.compare_with_inventory(vision.PhotoAnalysis(**r["analysis"]), inventory_log,
                                                            r["warehouse_id"])
    run["recompared_at"] = utc_now().isoformat()
    run["recompare_note"] = "model outputs unchanged; comparison rules re-applied without model calls"
    out = path.replace(".json", "_recompared.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(run, f, ensure_ascii=False, indent=2)
    print(out)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--recompare":
        recompare(sys.argv[2])
    else:
        main()
