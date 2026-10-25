"""P45: save the evidence of ONE app execution (run_id ddf9fc62fb5a) used for the report's agent trace.

The run was made in the running app (port 8050) by asking, in Chat:
  "Please draft a food allocation plan for the next 24 hours."
Sources, all from that same execution:
- data/live/usage_log.jsonl lines with run_id ddf9fc62fb5a (copied here),
- server log lines (agent usage, tool call, tool return), transcribed below verbatim except the long tool-return
  JSON, which is identified by its plan_fingerprint and re-verified by recomputing the tool on the same data,
- the reply and tool-activity text read from the page (DOM) after the run,
- screenshots S39 (top of reply) and S40 (end of reply + tool activity).
Also records that two other app runs of the earlier wording were Portkey cache HITs (replays).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from src import agent_tools  # noqa: E402

RUN = "ddf9fc62fb5a"
OUT = os.path.join(ROOT, "evidence", "report")
live = [json.loads(x) for x in open(os.path.join(ROOT, "data", "live", "usage_log.jsonl"))]
calls = [e for e in live if e["run_id"] == RUN]
with open(os.path.join(OUT, "agent_app_run_p45_usage.jsonl"), "w") as f:
    for e in calls:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")

SERVER_LOG = [
    "2026-10-25 04:04:44,194 httpx2 INFO HTTP Request: POST https://api.portkey.ai/v1/responses \"HTTP/1.1 200 OK\"",
    "2026-10-25 04:04:48,879 httpx2 INFO HTTP Request: POST https://api.portkey.ai/v1/responses \"HTTP/1.1 200 OK\"",
    "2026-10-25 04:04:48,909 src.agent INFO agent usage: {'requests': 2, 'input_tokens': 4467, 'output_tokens': 577, 'tool_calls': 1}",
    "2026-10-25 04:04:48,909 src.agent INFO tool call: calculate_allocation args={}",
    "2026-10-25 04:04:48,909 src.agent INFO tool return: calculate_allocation {...  \"plan_fingerprint\": \"9ac32e325eae451cf65f27a9590e1808f80140a60e11966579c48e583be7d894\"}",
]
LOGGED_FINGERPRINT = "9ac32e325eae451cf65f27a9590e1808f80140a60e11966579c48e583be7d894"
REPLY_DOM = open(os.path.join(OUT, "agent_app_run_p45_reply.txt"), encoding="utf-8").read()

recomputed = agent_tools.calculate_allocation()          # same working data (identical to data/sample)
assert recomputed["plan_fingerprint"] == LOGGED_FINGERPRINT, "tool output differs from the logged run"
g = recomputed["general_meals"]
checks = {
    "usage log totals equal server log totals": (sum(c["usage"]["input_tokens"] for c in calls),
                                                 sum(c["usage"]["output_tokens"] for c in calls)) == (4467, 577),
    "both calls reached the model (Portkey MISS)": all(c["headers"].get("x-portkey-cache-status") == "MISS"
                                                        for c in calls),
}
for fig in ("596", "1,003", "407", "206", "141", "39", "27", "351", "239", "347", "66", "590"):
    checks[f"reply contains {fig}"] = fig in REPLY_DOM
checks["reply says DRAFT and nothing approved/reserved/dispatched"] = (
    "DRAFT" in REPLY_DOM and "Nothing has been approved, reserved, or dispatched." in REPLY_DOM)
checks["reply keeps halal unknown"] = "unknown until counts are confirmed" in REPLY_DOM

record = {
    "run_id": RUN, "question": "Please draft a food allocation plan for the next 24 hours.",
    "sent_at_utc": "2026-10-25T08:04:41.250Z (browser clock)", "app": "Dash app on port 8050, working data = data/sample copies",
    "steps": [
        {"actor": "staff", "what": "asks the question in Chat (Show tool activity on)"},
        {"actor": "AI model", "call": 1, "what": "decides to call calculate_allocation with no arguments",
         **{k: calls[0]["usage"][k] for k in ("input_tokens", "cached_read_tokens", "cache_write_tokens",
                                               "reasoning_tokens", "output_tokens")},
         "latency_ms": calls[0]["latency_ms"], "portkey": calls[0]["headers"].get("x-portkey-cache-status")},
        {"actor": "code", "what": "calculate_allocation reads the latest validated records",
         "result": {"available": g["available_meals"], "unmet": g["total_unmet_meals"],
                    "plan_a": {s["shelter_id"]: s["plan_a_meals"] for s in g["shelters"]},
                    "shortage": g["shortage_meals"], "warnings": len(recomputed["data_warnings"]),
                    "plan_fingerprint": LOGGED_FINGERPRINT}},
        {"actor": "AI model", "call": 2, "what": "writes the DRAFT reply from the tool result",
         **{k: calls[1]["usage"][k] for k in ("input_tokens", "cached_read_tokens", "cache_write_tokens",
                                               "reasoning_tokens", "output_tokens")},
         "latency_ms": calls[1]["latency_ms"], "portkey": calls[1]["headers"].get("x-portkey-cache-status")},
        {"actor": "staff", "what": "reads the draft; nothing is saved"},
    ],
    "server_log_lines": SERVER_LOG, "reply_text_from_page": REPLY_DOM,
    "screenshots": ["evidence/screenshots/S39_p45_stage38_traced-run-ddf9fc62-reply-top.jpg",
                    "evidence/screenshots/S40_p45_stage38_traced-run-ddf9fc62-warnings-tool-activity.jpg"],
    "checks": checks,
    "note_on_other_runs": ("Two app runs of the earlier wording 'Prepare a food allocation plan for the next 24 hours.' "
                           "(P44 screenshots S35/S36; P45 screenshots S37/S38) were Portkey cache HITs: their response IDs "
                            "equal the scripted P44 trace run (agent_trace_p44.json), so their model output and tokens are "
                           "replays of that run. The tools were executed again by the app in those runs."),
}
json.dump(record, open(os.path.join(OUT, "agent_app_run_p45.json"), "w"), indent=2, ensure_ascii=False)
print(json.dumps(checks, indent=1)); print("all checks pass:", all(checks.values()))
