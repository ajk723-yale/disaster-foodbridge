"""Usage logger: one line per API call, unknown != 0, no secrets or content (offline, mocked HTTP)."""
import json
import os

import httpx2
import pytest
from openai import DefaultAsyncHttpxClient
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from src import config, llm
from src.usage_log import normalize_usage

FAKE_KEY = "sk-test-NOT-A-REAL-KEY-123"
SECRET_TEXT = "Shelter SH-09 private note: 3 patients on dialysis"
FULL_USAGE = {"input_tokens": 1200, "input_tokens_details": {"cached_tokens": 1024, "cache_write_tokens": 0},
              "output_tokens": 50, "output_tokens_details": {"reasoning_tokens": 20}, "total_tokens": 1250}


def message_response(text="ok", usage=FULL_USAGE, rid="resp_a"):
    body = {"id": rid, "object": "response", "created_at": 1, "model": "gpt-6-luna-global", "status": "completed",
            "output": [{"type": "message", "id": "msg_1", "role": "assistant", "status": "completed",
                        "content": [{"type": "output_text", "text": text, "annotations": []}]}],
            "parallel_tool_calls": True, "tool_choice": "auto", "tools": []}
    if usage is not None:
        body["usage"] = usage
    return body


def tool_call_response(rid="resp_t"):
    body = message_response(rid=rid)
    body["output"] = [{"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "count_meals",
                       "arguments": "{}", "status": "completed"}]
    return body


@pytest.fixture
def api(monkeypatch, tmp_path):
    """Route the real client through a mock transport; responses are served from a queue."""
    queue, seen_requests = [], []

    def handler(request):
        seen_requests.append(request)
        status, body = queue.pop(0)
        return httpx2.Response(status, json=body, headers={
            "x-portkey-cache-status": "MISS", "x-portkey-trace-id": "trace-1", "x-ratelimit-key": "secret-ish",
            "x-ms-served-model": "gpt-6-luna-global", "set-cookie": "a=b"})

    monkeypatch.setattr(config, "PORTKEY_API_KEY", FAKE_KEY)
    monkeypatch.setattr(config, "USAGE_LOG_PATH", str(tmp_path / "usage_log.jsonl"))
    real = llm.DefaultAsyncHttpxClient
    monkeypatch.setattr(llm, "DefaultAsyncHttpxClient",
                        lambda event_hooks: real(event_hooks=event_hooks, transport=httpx2.MockTransport(handler)))
    return queue, seen_requests


def log_lines():
    with open(config.USAGE_LOG_PATH) as f:
        return [json.loads(line) for line in f]


def test_unknown_fields_stay_null_and_zero_stays_zero():
    assert all(v is None for k, v in normalize_usage(None).items() if k != "other_usage_fields")
    partial = normalize_usage({"input_tokens": 10, "output_tokens": 0})
    assert partial["input_tokens"] == 10 and partial["output_tokens"] == 0
    assert partial["cached_read_tokens"] is None and partial["cache_write_tokens"] is None
    assert partial["reasoning_tokens"] is None
    full = normalize_usage({**FULL_USAGE, "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0,
                                                                    "audio_tokens": 3}})
    assert full["cached_read_tokens"] == 0 and full["cache_write_tokens"] == 0
    assert full["other_usage_fields"] == {"input_tokens_details.audio_tokens": 3}


def test_one_line_per_call_with_usage_and_no_secrets(api):
    queue, _ = api
    queue.append((200, message_response(text="model output must not be logged")))
    result = llm.run_with_fresh_model(Agent(None, name="report_extractor"), SECRET_TEXT)
    assert result.output == "model output must not be logged"
    [line] = log_lines()
    assert line["workflow"] == "extraction" and line["ok"] is True and line["model_reported"] == "gpt-6-luna-global"
    u = line["usage"]
    assert (u["input_tokens"], u["output_tokens"], u["cached_read_tokens"], u["cache_write_tokens"],
            u["reasoning_tokens"]) == (1200, 50, 1024, 0, 20)
    assert u["cache_write_ttl_30m_tokens"] is None                         # not reported -> unknown
    assert line["usage_raw"] == FULL_USAGE
    assert line["headers"] == {"x-portkey-cache-status": "MISS", "x-portkey-trace-id": "trace-1",
                               "x-ms-served-model": "gpt-6-luna-global"}
    text = open(config.USAGE_LOG_PATH).read()
    for forbidden in (FAKE_KEY, SECRET_TEXT, "model output must not be logged", "secret-ish", "set-cookie"):
        assert forbidden not in text
    assert "cost" not in json.dumps(line["usage"]).lower()


def test_tool_calling_run_logs_each_api_call_once(api):
    queue, seen = api
    queue.extend([(200, tool_call_response("resp_1")), (200, message_response("done", rid="resp_2"))])
    agent = Agent(None, name="foodbridge")

    @agent.tool_plain
    def count_meals() -> int:
        return 42

    assert llm.run_with_fresh_model(agent, "how many meals?").output == "done"
    lines = log_lines()
    assert len(seen) == len(lines) == 2                                     # HTTP calls == log lines
    assert [l["call_index_in_run"] for l in lines] == [0, 1] and len({l["run_id"] for l in lines}) == 1
    assert [l["response_id"] for l in lines] == ["resp_1", "resp_2"] and {l["workflow"] for l in lines} == {"chat"}
    assert all(l["pydantic_ai_request_usage"] is not None for l in lines)


def test_failed_call_is_logged_without_usage_or_error_message(api):
    queue, _ = api
    queue.extend([(400, {"error": {"type": "invalid_request_error", "code": "bad", "message": SECRET_TEXT}})] * 2)
    with pytest.raises(Exception):
        llm.run_with_fresh_model(Agent(None, name="photo_analyzer"), "x")
    lines = log_lines()
    assert lines and all(not l["ok"] and l["http_status"] == 400 for l in lines)
    assert all(l["usage"]["input_tokens"] is None for l in lines)
    assert lines[0]["error"] == {"type": "invalid_request_error", "code": "bad"}
    assert lines[0]["run_outcome"].startswith("error:") and SECRET_TEXT not in open(config.USAGE_LOG_PATH).read()


def test_response_without_details_keeps_cache_fields_unknown(api):
    queue, _ = api
    queue.append((200, message_response(usage={"input_tokens": 7, "output_tokens": 3, "total_tokens": 10})))
    llm.run_with_fresh_model(Agent(None, name="instruction_screen"), "x")
    [line] = log_lines()
    assert line["workflow"] == "safety_screen"
    assert line["usage"]["cached_read_tokens"] is None and line["usage"]["reasoning_tokens"] is None
    assert line["pydantic_ai_request_usage"]["cache_read_tokens"] == 0     # why PydanticAI isn't the source


def test_log_is_append_only(api):
    queue, _ = api
    queue.append((200, message_response(rid="resp_1")))
    llm.run_with_fresh_model(Agent(None, name="photo_followup"), "x")
    first = open(config.USAGE_LOG_PATH, "rb").read()
    queue.append((200, message_response(rid="resp_2")))
    llm.run_with_fresh_model(Agent(None, name="photo_followup"), "y")
    assert open(config.USAGE_LOG_PATH, "rb").read().startswith(first) and len(log_lines()) == 2


def test_logging_failure_never_changes_agent_behavior(api, monkeypatch):
    queue, _ = api
    queue.append((200, message_response(text="still works")))
    monkeypatch.setattr(config, "USAGE_LOG_PATH", os.path.join(config.SEED_DATA_DIR, "usage_log.jsonl"))
    assert llm.run_with_fresh_model(Agent(None, name="report_extractor"), "x").output == "still works"
    assert not os.path.exists(os.path.join(config.SEED_DATA_DIR, "usage_log.jsonl"))


def test_agents_with_their_own_model_are_not_logged(api):
    llm.run_with_fresh_model(Agent(TestModel(custom_output_text="t"), name="report_extractor"), "x")
    assert not os.path.exists(config.USAGE_LOG_PATH)
