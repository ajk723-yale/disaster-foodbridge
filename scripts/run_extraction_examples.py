"""Run AI extraction on the sample free-text reports and save the full results as evidence.

Makes real model calls (gpt-6-luna via Portkey). Writes only to evidence/extraction/;
nothing is added to the record logs or treated as validated data.

    .venv/bin/python scripts/run_extraction_examples.py
    .venv/bin/python scripts/run_extraction_examples.py --recheck evidence/extraction/<run>.json

--recheck re-applies the current code-side checks to the model outputs saved in a run
(no model calls) and writes <run>_rechecked.json next to it.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.extraction import (  # noqa: E402
    ShelterReportExtraction,
    check_extraction,
    extract_shelter_report,
    to_shelter_row,
)
from src.timeutil import utc_now  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    with open(os.path.join(ROOT, "data/sample/free_text_reports.json"), encoding="utf-8") as f:
        sample = json.load(f)
    started = utc_now()
    results = []
    for report in sample["reports"]:
        try:
            result = extract_shelter_report(report["text"], sample["received_at"])
            results.append({"id": report["id"], "case": report["case"], **result})
        except Exception as exc:  # record failures as evidence too
            results.append({"id": report["id"], "case": report["case"], "source_text": report["text"],
                            "error": f"{type(exc).__name__}: {exc}"})
        print(f"{report['id']}: done", flush=True)
    run = {"run_started_at": started.isoformat(), "run_finished_at": utc_now().isoformat(),
           "received_at": sample["received_at"], "results": results,
           "total_usage": {k: sum(r.get("usage", {}).get(k, 0) for r in results)
                           for k in ("requests", "input_tokens", "output_tokens")}}
    path = os.path.join(ROOT, "evidence/extraction", f"extraction_run_{started.strftime('%Y%m%dT%H%M%SZ')}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(run, f, ensure_ascii=False, indent=2)
    print(path)


def recheck(path):
    with open(path, encoding="utf-8") as f:
        run = json.load(f)
    for r in run["results"]:
        if "extracted" not in r:
            continue
        extraction = ShelterReportExtraction(**r["extracted"])
        reported_at, issues = check_extraction(extraction, r["source_text"], run["received_at"])
        r.update(reported_at_utc=reported_at, issues=issues, shelter_row=to_shelter_row(extraction, reported_at))
    run["rechecked_at"] = utc_now().isoformat()
    run["recheck_note"] = "model outputs unchanged; code-side checks re-applied without model calls"
    out = path.replace(".json", "_rechecked.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(run, f, ensure_ascii=False, indent=2)
    print(out)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--recheck":
        recheck(sys.argv[2])
    else:
        main()
