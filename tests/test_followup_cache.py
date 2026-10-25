"""P35: photo follow-ups put a prompt-cache breakpoint after the stable analysis + image (offline, mocked HTTP)."""
import hashlib
import json
import os

import httpx2
import pytest
from pydantic_ai import BinaryContent, CachePoint

from src import config, llm, vision

PHOTO_A = os.path.join(config.PROJECT_ROOT, "data", "sample_photos", "synthetic_wh_a_aisle2.png")
PHOTO_B = os.path.join(config.PROJECT_ROOT, "data", "sample_photos", "synthetic_wh_b_bay1.png")


def store(analysis_id, image_path, facts):
    data = open(image_path, "rb").read()
    record = {"analysis_id": analysis_id, "analysis": {"observed_facts": facts, "items": []},
              "image": {"original_name": os.path.basename(image_path), "media_type": "image/png",
                        "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}}
    vision.save_photo_analysis(image_path, record)
    return data


@pytest.fixture
def photos(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PHOTO_DIR", str(tmp_path / "photos"))
    return {"A": store("photo-a", PHOTO_A, ["six cases of canned bread"]),
            "B": store("photo-b", PHOTO_B, ["36 cartons of curry rice"])}


@pytest.fixture
def captured(monkeypatch):
    calls = []

    class Result:
        output = "answer"

        class usage:
            requests, input_tokens, output_tokens = 1, 0, 0

    def fake_run(agent, content):
        calls.append(content)
        return Result()
    monkeypatch.setattr(vision, "_run", fake_run)
    return calls


def test_question_comes_after_a_cache_point_that_follows_the_image(photos, captured):
    vision.ask_about_photo("photo-a", "How many cases?")
    analysis, image, point, question = captured[0]
    assert analysis.startswith("Earlier analysis (JSON):") and "six cases" in analysis
    assert isinstance(image, BinaryContent) and image.data == photos["A"]
    assert isinstance(point, CachePoint)
    assert question == "Staff question: How many cases?"


def test_same_photo_shares_the_prefix_and_another_photo_does_not(photos, captured):
    vision.ask_about_photo("photo-a", "Question one?")
    vision.ask_about_photo("photo-a", "Question two?")
    vision.ask_about_photo("photo-b", "Question one?")
    a1, a2, b1 = captured
    assert a1[:2] == a2[:2] and a1[3] != a2[3]                       # stable prefix identical, question differs
    assert b1[0] != a1[0] and b1[1].data == photos["B"] != a1[1].data  # photo B carries only its own context
    assert "curry rice" in b1[0] and "canned bread" not in b1[0]


def test_breakpoint_is_sent_on_the_image_not_on_the_question(photos, monkeypatch, tmp_path):
    """The real client/serializer (PydanticAI -> OpenAI Responses) through a mock transport."""
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx2.Response(200, json={
            "id": "resp_1", "object": "response", "created_at": 1, "model": "gpt-6-luna", "status": "completed",
            "output": [{"type": "message", "id": "m", "role": "assistant", "status": "completed",
                        "content": [{"type": "output_text", "text": "Six.", "annotations": []}]}],
            "parallel_tool_calls": True, "tool_choice": "auto", "tools": [],
            "usage": {"input_tokens": 1966, "input_tokens_details": {"cached_tokens": 1951, "cache_write_tokens": 0},
                      "output_tokens": 5, "output_tokens_details": {"reasoning_tokens": 0}, "total_tokens": 1971}},
            headers={"x-portkey-cache-status": "MISS"})

    monkeypatch.setattr(config, "PORTKEY_API_KEY", "sk-test-NOT-A-REAL-KEY")
    monkeypatch.setattr(config, "USAGE_LOG_PATH", str(tmp_path / "usage_log.jsonl"))
    real = llm.DefaultAsyncHttpxClient
    monkeypatch.setattr(llm, "DefaultAsyncHttpxClient",
                        lambda event_hooks: real(event_hooks=event_hooks, transport=httpx2.MockTransport(handler)))
    assert vision.ask_about_photo("photo-a", "How many cases?")["answer"] == "Six."
    parts = [p for item in bodies[0]["input"] if item.get("role") == "user" for p in item["content"]]
    kinds = [p["type"] for p in parts]
    image_index = kinds.index("input_image")
    assert parts[image_index].get("prompt_cache_breakpoint") == {"mode": "explicit"}
    after = parts[image_index + 1:]
    assert after and all("prompt_cache_breakpoint" not in p for p in after)
    assert after[-1]["text"] == "Staff question: How many cases?"
    assert "Staff question" not in json.dumps(parts[:image_index + 1])  # question is outside the cached prefix
    assert "prompt_cache_options" not in bodies[0]                       # no TTL or cache-mode setting changed
    [logged] = [json.loads(x) for x in open(config.USAGE_LOG_PATH)]
    assert logged["workflow"] == "photo_followup" and logged["usage"]["cached_read_tokens"] == 1951


def test_saved_p35_comparison_counts_only_provider_calls():
    path = os.path.join(config.PROJECT_ROOT, "evidence", "tokenomics", "p35_followup_cache", "comparison_p35.json")
    r = json.load(open(path))
    checks = r["checks"]
    assert checks["contamination_check_q1_reads_zero"] == {"baseline2": True, "optimized2": True}
    assert checks["photo_B_reads_no_photo_A_context"] == {"baseline2": True, "optimized2": True}
    for phase, side in (("baseline2", "baseline"), ("optimized2", "optimized")):
        calls = r["phases"][phase]["calls"]
        provider = [c for c in calls if c["kind"] == "provider_call"]
        assert [c for c in calls if c["kind"] == "portkey_hit"]          # the deliberate repeat was a HIT ...
        totals = r["comparison"]["all provider calls"][side]              # ... and is not in the totals
        assert totals["provider_calls"] == len(provider)
        assert sum(c["cost_W30"] for c in provider) == pytest.approx(totals["cost_W30"])
    later = r["comparison"]["photo A, later questions"]
    assert later["optimized"]["cached_read_tokens"] > 0 == later["baseline"]["cached_read_tokens"]
