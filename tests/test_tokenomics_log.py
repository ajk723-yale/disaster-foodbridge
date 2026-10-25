"""P34: pricing per-call usage-log entries under labeled scenarios (no model calls)."""
import json
import os

import pytest

from src import config
from src.tokenomics import (cache_write_reuse, call_kind, load_pricing, load_usage_log, per_run_costs,
                            price_logged_call, summarize_log, token_categories)

ROOT = config.PROJECT_ROOT
EV = os.path.join(ROOT, "evidence", "tokenomics")
PRICING = load_pricing(os.path.join(EV, "pricing_gpt-6-luna_2026-10-24.json"))


def entry(workflow="chat", run_id="r1", call_id="c1", status="MISS", ok=True, inp=2000, out=100, read=1500,
          write=400, reasoning=40):
    usage = {"input_tokens": inp, "output_tokens": out, "cached_read_tokens": read, "cache_write_tokens": write,
             "reasoning_tokens": reasoning}
    headers = {} if status is None else {"x-portkey-cache-status": status}
    return {"call_id": call_id, "run_id": run_id, "workflow": workflow, "ok": ok, "headers": headers,
            "usage": usage}


def test_call_kind_separates_portkey_hits_from_provider_calls():
    assert call_kind(entry(status="MISS")) == "provider_call"
    assert call_kind(entry(status="DISABLED")) == "provider_call"
    assert call_kind(entry(status="HIT")) == "portkey_hit"
    assert call_kind(entry(status=None)) == "unknown_cache_status"
    assert call_kind(entry(ok=False)) == "failed"


def test_token_categories_split_input_and_keep_unknown_as_none():
    c = token_categories(entry()["usage"])
    assert c == {"uncached_input": 100, "cached_read": 1500, "cache_write": 400, "output": 100,
                 "reasoning_within_output": 40}
    u = entry()["usage"]
    u["cache_write_tokens"] = None
    assert token_categories(u) is None                                  # unknown is not priced as 0
    with pytest.raises(ValueError):
        token_categories(entry(inp=100, read=90, write=20)["usage"])


def test_price_logged_call_per_category_and_ttl_scenario():
    w30 = (100 * 0.10 + 1500 * 0.01 + 400 * 0.125 + 100 * 0.50) / 1e6
    w12 = (100 * 0.10 + 1500 * 0.01 + 400 * 0.25 + 100 * 0.50) / 1e6
    assert price_logged_call(entry(), PRICING, "W30") == pytest.approx(w30)
    assert price_logged_call(entry(), PRICING, "W12") == pytest.approx(w12)
    assert price_logged_call(entry(ok=False), PRICING) is None          # failed calls not priced


def test_portkey_hit_is_free_or_replayed_only_by_named_scenario():
    hit = entry(status="HIT")
    assert price_logged_call(hit, PRICING, "W30", "HIT_FREE") == 0.0
    assert price_logged_call(hit, PRICING, "W30", "HIT_AS_REPLAYED") == pytest.approx(
        price_logged_call(entry(), PRICING, "W30"))


def test_summarize_log_excludes_hits_from_provider_means_and_totals_scenarios():
    es = [entry(call_id="a"), entry(call_id="b", inp=1000, read=0, write=0, out=50), entry(call_id="h", status="HIT")]
    s = summarize_log(es, PRICING)["chat"]
    assert (s["calls"], s["provider_calls"], s["portkey_hits"], s["failed"]) == (3, 2, 1, 0)
    assert s["mean_tokens_provider_calls"]["cached_read"] == 750
    p_a, p_b = price_logged_call(es[0], PRICING), price_logged_call(es[1], PRICING)
    assert s["mean_cost_provider_call_usd"]["W30"] == pytest.approx((p_a + p_b) / 2)
    assert s["total_cost_usd"]["W30+HIT_FREE"] == pytest.approx(p_a + p_b)
    assert s["total_cost_usd"]["W30+HIT_AS_REPLAYED"] == pytest.approx(2 * p_a + p_b)


def test_per_run_costs_sum_calls_of_one_question():
    es = [entry(call_id="1", run_id="q1"), entry(call_id="2", run_id="q1"), entry(call_id="3", run_id="q2"),
          entry(call_id="4", run_id="q3", status="HIT")]
    one = price_logged_call(es[0], PRICING)
    assert sorted(per_run_costs(es, PRICING, "chat")) == pytest.approx([one, 2 * one])


def test_cache_write_reuse_reports_unread_write_premium():
    es = [entry(workflow="photo_followup", call_id=str(i), inp=1600, read=0, write=1550) for i in range(3)]
    r = cache_write_reuse(es, PRICING)["photo_followup"]
    assert (r["cache_write_tokens"], r["cached_read_tokens"]) == (4650, 0)
    assert r["write_premium_usd_w30"] == pytest.approx(4650 * (0.125 - 0.10) / 1e6)


def test_load_usage_log_dedupes_by_call_id_and_skips_missing(tmp_path):
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    a.write_text(json.dumps(entry(call_id="x")) + "\n" + json.dumps(entry(call_id="y")) + "\n")
    b.write_text(json.dumps(entry(call_id="y")) + "\n")
    es = load_usage_log(str(a), str(b), str(tmp_path / "missing.jsonl"))
    assert [e["call_id"] for e in es] == ["x", "y"]


def test_saved_p34_evidence_matches_recomputation_from_snapshot():
    saved = json.load(open(os.path.join(EV, "tokenomics_p34_2026-10-24.json")))
    es = load_usage_log(*[os.path.join(ROOT, p) for p in saved["sources"]])
    assert len(es) == saved["entries"]
    assert json.loads(json.dumps(summarize_log(es, PRICING))) == saved["summary_by_workflow"]
    assert cache_write_reuse(es, PRICING) == saved["cache_write_reuse"]
    hits = [e for e in es if call_kind(e) == "portkey_hit"]
    assert hits and all("x-ms-served-model" not in e["headers"] for e in hits)   # HITs lack Azure headers
