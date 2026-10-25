"""P33: one real call per workflow through the shared usage logger; report which usage fields the API returns.

Logs to evidence/usage/usage_log_p33.jsonl (not data/live). Photo analyses are stored in a temporary
folder. Writes evidence/usage/usage_fields_p33.json. Live data is hashed before and after.

    .venv/bin/python scripts/run_usage_logging_check.py
"""
import base64
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.run_injection_eval import live_hashes  # noqa: E402
from src import config  # noqa: E402
from src.agent import run_agent  # noqa: E402
from src.extraction import extract_shelter_report  # noqa: E402
from src.usage_log import KNOWN_USAGE_PATHS  # noqa: E402
from src.vision import analyze_warehouse_photo, ask_about_photo  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "evidence", "usage", "usage_log_p33.jsonl")


def main():
    config.USAGE_LOG_PATH = LOG
    config.PHOTO_DIR = tempfile.mkdtemp(prefix="p33-photos-")
    before = live_hashes()
    start = sum(1 for _ in open(LOG)) if os.path.exists(LOG) else 0
    benign = json.load(open(os.path.join(ROOT, "evidence/safety/benign_reports_p31.json"), encoding="utf-8"))
    report = benign["cases"][5]["text"]
    photo = os.path.join(ROOT, "data/sample_photos/synthetic_wh_a_aisle2.png")
    steps = {}
    steps["chat"] = run_agent("Which warehouse has the most allergy-free meals available?", [])["usage"]
    steps["extraction+screen"] = extract_shelter_report(report, benign["received_at"])["usage_breakdown"]
    record = analyze_warehouse_photo(photo, "WH-A")
    steps["photo_analysis"] = record["usage"]
    steps["photo_followup"] = ask_about_photo(record["analysis_id"], "How many shelves are visible?")["usage"]

    lines = [json.loads(l) for l in open(LOG, encoding="utf-8")][start:]
    text = "".join(open(LOG, encoding="utf-8").readlines()[start:])
    image_b64_head = base64.b64encode(open(photo, "rb").read())[:40].decode()
    fields = list(KNOWN_USAGE_PATHS) + ["other_usage_fields"]
    by_workflow = {}
    for l in lines:
        w = by_workflow.setdefault(l["workflow"], {"api_calls": 0, "present": {f: 0 for f in fields},
                                                   "raw_keys": set(), "headers": {}})
        w["api_calls"] += 1
        for f in fields:
            if l["usage"].get(f) not in (None, {}):
                w["present"][f] += 1
        w["raw_keys"].update(k for k in _flat(l["usage_raw"] or {}))
        for h, v in l["headers"].items():
            w["headers"].setdefault(h, set()).add(v if h in ("x-portkey-cache-status", "x-ms-served-model",
                                                              "x-portkey-provider", "cf-cache-status") else "(present)")
    summary = {
        "log_file": os.path.relpath(LOG, ROOT), "new_lines": len(lines),
        "agent_reported_requests": {k: v for k, v in steps.items()},
        "by_workflow": {w: {**d, "raw_keys": sorted(d["raw_keys"]),
                            "headers": {h: sorted(v) for h, v in d["headers"].items()}} for w, d in by_workflow.items()},
        "all_ok": all(l["ok"] for l in lines),
        "secrets_or_content_found": {"api_key": bool(config.PORTKEY_API_KEY) and config.PORTKEY_API_KEY in text,
                                     "report_text": report[:30] in text, "image_base64": image_b64_head in text},
        "live_data_unchanged": live_hashes() == before,
    }
    with open(os.path.join(ROOT, "evidence", "usage", "usage_fields_p33.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


def _flat(d, p=""):
    for k, v in d.items():
        if isinstance(v, dict):
            yield from _flat(v, f"{p}{k}.")
        else:
            yield f"{p}{k}"


if __name__ == "__main__":
    main()
