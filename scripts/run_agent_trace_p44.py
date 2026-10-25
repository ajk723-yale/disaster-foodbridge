"""P44: record one complete chat-agent run for the report (real model call, isolated data).

    .venv/bin/python scripts/run_agent_trace_p44.py

Same call as src.agent.run_agent (same agent, instructions, tools, request limit), but the full
message list is kept: each model request, each tool call with its arguments, each tool result, the
final reply, and the per-call usage log. Data: copies of data/sample in evidence/report/trace_case/.
Writes evidence/report/agent_trace_p44.json and agent_trace_usage_p44.jsonl. No app code changes.
"""
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart  # noqa: E402
from pydantic_ai.usage import UsageLimits  # noqa: E402

from src import agent, config  # noqa: E402
from src.llm import run_with_fresh_model  # noqa: E402

OUT = os.path.join(ROOT, "evidence", "report")
QUESTION = "Prepare a food allocation plan for the next 24 hours."


def main():
    case = os.path.join(OUT, "trace_case")
    if os.path.exists(case):
        shutil.rmtree(case)
    os.makedirs(case)
    for name in ("shelter_log.csv", "inventory_log.csv", "commitments_log.csv"):
        shutil.copyfile(os.path.join(ROOT, "data", "sample", name), os.path.join(case, name))
    config.SHELTER_LOG_PATH = os.path.join(case, "shelter_log.csv")
    config.INVENTORY_LOG_PATH = os.path.join(case, "inventory_log.csv")
    config.COMMITMENTS_LOG_PATH = os.path.join(case, "commitments_log.csv")
    config.FINALIZATION_DB_PATH = os.path.join(case, "finalization.db")
    log = os.path.join(OUT, "agent_trace_usage_p44.jsonl")
    if os.path.exists(log):
        os.remove(log)
    config.USAGE_LOG_PATH = log

    result = run_with_fresh_model(agent._agent(), QUESTION, message_history=[],
                                  usage_limits=UsageLimits(request_limit=config.AGENT_REQUEST_LIMIT))
    steps = []
    for msg in result.new_messages():
        for part in msg.parts:
            if isinstance(part, ToolCallPart):
                steps.append({"actor": "AI model", "step": "decides to call a tool", "tool": part.tool_name,
                              "args": part.args_as_json_str()})
            elif isinstance(part, ToolReturnPart):
                steps.append({"actor": "code (deterministic)", "step": "tool result", "tool": part.tool_name,
                              "summary": agent._summarize(part.content), "content": part.content})
            elif isinstance(part, TextPart) and isinstance(msg, ModelResponse):
                steps.append({"actor": "AI model", "step": "writes the reply", "text": part.content})
    calls = [json.loads(x) for x in open(log)]
    trace = {"question": QUESTION, "model": config.MODEL, "data": os.path.relpath(case, ROOT),
             "steps": steps, "tool_events_as_shown_in_ui": agent._tool_events(result.new_messages()),
             "usage_total": {"requests": result.usage.requests, "input_tokens": result.usage.input_tokens,
                             "output_tokens": result.usage.output_tokens, "tool_calls": result.usage.tool_calls},
             "calls": [{"call": i + 1, "latency_ms": c["latency_ms"],
                        "portkey_cache_status": c["headers"].get("x-portkey-cache-status"),
                        **{k: c["usage"][k] for k in ("input_tokens", "cached_read_tokens", "cache_write_tokens",
                                                      "reasoning_tokens", "output_tokens")}}
                       for i, c in enumerate(calls)]}
    json.dump(trace, open(os.path.join(OUT, "agent_trace_p44.json"), "w"), indent=2, ensure_ascii=False, default=str)
    for s in steps:
        print(s["actor"], "|", s["step"], "|", s.get("tool", ""), s.get("args", ""), s.get("summary", ""),
              (s.get("text") or "")[:120].replace("\n", " "))
    print(trace["calls"])


if __name__ == "__main__":
    main()
