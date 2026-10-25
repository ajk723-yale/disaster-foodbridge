"""Tokenomics calculations: rates x tokens, caching bounds, record inventory, scaling (no model calls)."""
import json
import os

import pytest

from src import config
from src.tokenomics import (call_cost, cost_range, load_pricing, load_usage_records, mark_possible_cache_repeats,
                            scale, summarize)

ROOT = config.PROJECT_ROOT
PRICING = load_pricing(os.path.join(ROOT, "evidence", "tokenomics", "pricing_gpt-6-luna_2026-10-24.json"))


def test_pricing_file_records_source_date_and_caveats():
    assert PRICING["model"] == "gpt-6-luna" and PRICING["date_checked"] == "2026-10-24"
    assert PRICING["sources"]["pricing_page"].startswith("https://developers.openai.com/")
    assert PRICING["rates"]["standard"]["short_context"] == {"input": 0.10, "cached_input": 0.01,
                                                             "cache_write_30m": 0.125, "cache_write_12h": 0.25,
                                                             "output": 0.50}
    assert any("Portkey" in n for n in PRICING["not_verified"])
    assert PRICING["caching_conditions_from_guide"]["minimum_cacheable_prompt_tokens"] == 1024


def test_call_cost_uses_published_rates_per_million():
    assert call_cost(100_000, 0, PRICING) == pytest.approx(0.010)        # below the 272K long-context threshold
    assert call_cost(0, 1_000_000, PRICING) == pytest.approx(0.50)
    assert call_cost(1_000_000, 0, PRICING) == pytest.approx(0.20)       # above it: long-context input rate
    assert call_cost(976, 334, PRICING) == pytest.approx((976 * 0.10 + 334 * 0.50) / 1e6)


def test_cached_reads_and_writes_are_priced_separately():
    cost = call_cost(2000, 100, PRICING, cached_read_tokens=1000, cache_write_30m_tokens=500, cache_write_12h_tokens=200)
    assert cost == pytest.approx((300 * 0.10 + 1000 * 0.01 + 500 * 0.125 + 200 * 0.25 + 100 * 0.50) / 1e6)
    with pytest.raises(ValueError):
        call_cost(100, 0, PRICING, cached_read_tokens=101)


def test_long_context_rates_apply_above_the_threshold():
    assert call_cost(272_000, 0, PRICING) == pytest.approx(272_000 * 0.10 / 1e6)
    assert call_cost(272_001, 0, PRICING) == pytest.approx(272_001 * 0.20 / 1e6)     # whole request


def test_caching_bounds_only_for_prompts_of_at_least_1024_tokens():
    short = cost_range(976, 334, PRICING)
    assert short["low"] == short["point"] == short["high"]
    long = cost_range(1867, 704, PRICING)
    assert long["low"] == pytest.approx((1867 * 0.01 + 704 * 0.5) / 1e6)
    assert long["high"] == pytest.approx((1867 * 0.125 + 704 * 0.5) / 1e6)
    assert long["low"] < long["point"] < long["high"]
    two_requests = cost_range(2000, 300, PRICING, requests=2)          # 1,000 per request: not cacheable
    assert two_requests["low"] == two_requests["point"]


def test_inventory_counts_each_real_call_once():
    records = load_usage_records(ROOT)
    by = {}
    for r in records:
        by[r["workflow"]] = by.get(r["workflow"], 0) + 1
    assert by == {"extraction": 17, "safety_screen": 9, "photo_analysis": 8, "photo_followup": 8, "chat": 13,
                  "chat_probe": 1}
    assert not any("analyses/" in r["source"] or "_rechecked" in r["source"] or "_recompared" in r["source"]
                   for r in records)
    assert all(r["measured"] for r in records if not r["workflow"].startswith("chat"))
    assert not any(r["measured"] for r in records if r["workflow"].startswith("chat"))


def test_identical_repeats_are_flagged_not_dropped():
    records = mark_possible_cache_repeats(load_usage_records(ROOT))
    analyses = [r for r in records if r["workflow"] == "photo_analysis"]
    assert len(analyses) == 8 and sum(r["possible_cache_repeat"] for r in analyses) == 6


def test_summary_matches_a_direct_calculation():
    records = load_usage_records(ROOT)
    summary = summarize(records, PRICING)
    screen = [r for r in records if r["workflow"] == "safety_screen"]
    expected = sum(call_cost(r["input_tokens"], r["output_tokens"], PRICING) for r in screen)
    assert summary["safety_screen"]["total_cost_usd_point"] == pytest.approx(expected)
    assert summary["chat"]["data_quality"] == "observed in logs, not saved"


def test_scaling_is_plain_arithmetic_and_requires_unit_costs():
    unit = {"chat": 0.0005, "extraction": 0.0003}
    assert scale({"chat": 10, "extraction": 5}, unit, users=100) == pytest.approx(100 * (10 * 0.0005 + 5 * 0.0003))
    assert scale({"chat": 1}, unit, users=10_000, days=30) == pytest.approx(10_000 * 30 * 0.0005)
    with pytest.raises(KeyError):
        scale({"photo_analysis": 1}, unit, users=1)


def test_generated_report_and_json_exist_and_agree():
    path = os.path.join(ROOT, "evidence", "tokenomics", "tokenomics_2026-10-24.json")
    result = json.load(open(path))
    recomputed = summarize(load_usage_records(ROOT), PRICING)
    for wf, s in recomputed.items():
        assert result["summary_by_workflow"][wf]["total_cost_usd_point"] == pytest.approx(s["total_cost_usd_point"])
    assert "hypothetical" in result["illustrative_scaling_usd_per_day"]["warning"].lower()
