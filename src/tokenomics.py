"""Tokenomics: measured token usage x published API rates -> estimated cost (with stated assumptions).

Kept separate on purpose:
- measured usage: token counts recorded by the app (PydanticAI usage), read from evidence files;
- observed usage: chat counts seen in server logs but not saved (lower confidence);
- published rates: evidence/tokenomics/pricing_gpt-6-luna_<date>.json (OpenAI's page, with source and date);
- estimated cost: computed here, never billed amounts;
- assumptions: listed with every estimate.

Read-only analysis: nothing here changes agent behavior.
"""
import glob
import json
import math
import os
import statistics

PER_MILLION = 1_000_000

ASSUMPTIONS = [
    "A1 Rates: OpenAI's published standard-tier rates for gpt-6-luna (checked 2026-10-24). Our calls go through "
    "Portkey to an Azure OpenAI deployment; the course account's actual billing (rates, markups, credits) is unknown.",
    "A2 Caching: cached-read and cache-write token counts were never recorded, so the point estimate bills all input "
    "at the uncached rate. Bounds: for prompts of at least 1,024 tokens (the guide's minimum for GPT-5.6 and later), "
    "the low bound bills all input as cached reads (0.1x) and the high bound as 30-minute cache writes (1.25x); "
    "shorter prompts cannot be cached and use the uncached rate in all three figures.",
    "A3 Images: photo-analysis input_tokens are assumed to include the image tokens (the guide does not say for "
    "gpt-6-luna). Output tokens are assumed to include any reasoning tokens (not recorded separately).",
    "A4 Context: every recorded call is far below the 272,000-token long-context threshold, so short-context rates "
    "apply.",
    "A5 Repeats: identical prompts that returned identical outputs and token counts may have been served from a "
    "Portkey cache; whether those were billed is unknown, so they are counted as billed.",
]


def load_pricing(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def call_cost(input_tokens, output_tokens, pricing, cached_read_tokens=0, cache_write_30m_tokens=0,
              cache_write_12h_tokens=0, tier="standard"):
    """USD cost of one request from token counts and published per-1M rates."""
    context = "long_context" if input_tokens > pricing["long_context_threshold_input_tokens"] else "short_context"
    r = pricing["rates"][tier][context]
    uncached = input_tokens - cached_read_tokens - cache_write_30m_tokens - cache_write_12h_tokens
    if uncached < 0:
        raise ValueError("cached and cache-write tokens exceed input tokens")
    return (uncached * r["input"] + cached_read_tokens * r["cached_input"]
            + cache_write_30m_tokens * r["cache_write_30m"] + cache_write_12h_tokens * r["cache_write_12h"]
            + output_tokens * r["output"]) / PER_MILLION


def cost_range(input_tokens, output_tokens, pricing, requests=1):
    """Point estimate (no caching) and caching bounds for one recorded call (assumption A2).

    input_tokens may be summed over several requests; the per-request average decides cacheability.
    """
    minimum = pricing["caching_conditions_from_guide"]["minimum_cacheable_prompt_tokens"]
    point = call_cost(input_tokens, output_tokens, pricing)
    if requests and input_tokens / requests >= minimum:
        low = call_cost(input_tokens, output_tokens, pricing, cached_read_tokens=input_tokens)
        high = call_cost(input_tokens, output_tokens, pricing, cache_write_30m_tokens=input_tokens)
    else:
        low = high = point
    return {"point": point, "low": low, "high": high}


# ---- usage records ------------------------------------------------------------

def _rec(workflow, source, call_id, usage, measured=True, note=""):
    return {"workflow": workflow, "source": source, "call_id": call_id, "requests": usage["requests"],
            "input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"],
            "measured": measured, "note": note}


def load_usage_records(root):
    """One record per real model call. Copies of the same calls (vision/analyses/, *_rechecked.json,
    *_recompared.json) are excluded so nothing is counted twice."""
    ev = os.path.join(root, "evidence")
    records = []
    for path in sorted(glob.glob(os.path.join(ev, "extraction", "extraction_run_*.json"))):
        if path.endswith(("_rechecked.json", "_recompared.json")):
            continue
        for r in json.load(open(path, encoding="utf-8"))["results"]:
            if "usage" in r:
                records.append(_rec("extraction", os.path.relpath(path, root), r["id"], r["usage"]))
    for path in sorted(glob.glob(os.path.join(ev, "vision", "vision_run_*.json"))):
        if path.endswith("_recompared.json"):
            continue
        run = json.load(open(path, encoding="utf-8"))
        for r in run["results"]:
            if "usage" in r:
                records.append(_rec("photo_analysis", os.path.relpath(path, root), r["analysis_id"], r["usage"]))
        for i, f in enumerate(run.get("followups", [])):
            if "usage" in f:
                records.append(_rec("photo_followup", os.path.relpath(path, root), f"followup-{i}", f["usage"]))
    for folder in sorted(glob.glob(os.path.join(ev, "vision", "browser_p29", "photo-*"))):
        a = json.load(open(os.path.join(folder, "analysis.json"), encoding="utf-8"))
        records.append(_rec("photo_analysis", os.path.relpath(folder, root), a["analysis_id"], a["usage"]))
        fpath = os.path.join(folder, "followups.jsonl")
        if os.path.exists(fpath):
            for i, line in enumerate(open(fpath, encoding="utf-8")):
                records.append(_rec("photo_followup", os.path.relpath(fpath, root), f"{a['analysis_id']}-q{i}",
                                    json.loads(line)["usage"]))
    for path in sorted(glob.glob(os.path.join(ev, "safety", "injection_run_*.json"))):
        for r in json.load(open(path, encoding="utf-8"))["results"]:
            if "output" in r:
                records.append(_rec("extraction", os.path.relpath(path, root), r["id"], r["output"]["usage"],
                                    note="P30 (no screen)"))
    for path in sorted(glob.glob(os.path.join(ev, "safety", "injection_defense_run_*.json"))):
        run = json.load(open(path, encoding="utf-8"))
        for r in run["p30_cases"] + run["benign_cases"]:
            if "usage_breakdown" in r:
                records.append(_rec("extraction", os.path.relpath(path, root), r["id"], r["usage_breakdown"]["extraction"],
                                    note="P31"))
                records.append(_rec("safety_screen", os.path.relpath(path, root), r["id"],
                                    r["usage_breakdown"]["safety_screen"], note="P31"))
    chat = os.path.join(ev, "tokenomics", "chat_usage_observed.json")
    if os.path.exists(chat):
        for i, r in enumerate(json.load(open(chat, encoding="utf-8"))["records"]):
            workflow = "chat_probe" if r["kind"] == "probe" else "chat"
            records.append(_rec(workflow, os.path.relpath(chat, root), f"{r['prompt']}-{i}", r, measured=False,
                                note=r["question"]))
    return records


def mark_possible_cache_repeats(records):
    """Flag calls whose (workflow, input, output) exactly repeats an earlier call (assumption A5)."""
    seen = set()
    for r in records:
        key = (r["workflow"], r["input_tokens"], r["output_tokens"])
        r["possible_cache_repeat"] = key in seen
        seen.add(key)
    return records


def summarize(records, pricing):
    """Per-workflow token statistics and estimated cost per call (point estimate and caching bounds)."""
    out = {}
    for wf in sorted({r["workflow"] for r in records}):
        rs = [r for r in records if r["workflow"] == wf]
        costs = [cost_range(r["input_tokens"], r["output_tokens"], pricing, r["requests"]) for r in rs]
        ins, outs = [r["input_tokens"] for r in rs], [r["output_tokens"] for r in rs]
        out[wf] = {
            "calls": len(rs), "requests": sum(r["requests"] for r in rs),
            "data_quality": "measured (saved files)" if all(r["measured"] for r in rs)
            else "observed in logs, not saved",
            "possible_cache_repeats": sum(1 for r in rs if r.get("possible_cache_repeat")),
            "input_tokens": {"mean": statistics.mean(ins), "min": min(ins), "max": max(ins), "total": sum(ins)},
            "output_tokens": {"mean": statistics.mean(outs), "min": min(outs), "max": max(outs), "total": sum(outs)},
            "cost_per_call_usd": {"point_mean": statistics.mean(c["point"] for c in costs),
                                  "point_min": min(c["point"] for c in costs),
                                  "point_max": max(c["point"] for c in costs),
                                  "low_mean": statistics.mean(c["low"] for c in costs),
                                  "high_mean": statistics.mean(c["high"] for c in costs)},
            "total_cost_usd_point": sum(c["point"] for c in costs),
        }
    return out


def scale(per_user_calls, unit_cost, users, days=1):
    """Cost for `users` users over `days` days: sum(calls per user per day x cost per call).

    per_user_calls and unit_cost are dicts keyed by workflow. Pure arithmetic: every input is an assumption
    until per-user call volumes are measured."""
    missing = [w for w in per_user_calls if w not in unit_cost]
    if missing:
        raise KeyError(f"no unit cost for {missing}")
    return users * days * sum(n * unit_cost[w] for w, n in per_user_calls.items())


def round_up_cents(usd):
    return math.ceil(usd * 100) / 100


# ---- per-call usage log (P33+) -------------------------------------------------

WRITE_TTL_SCENARIOS = {
    "W30": "cache writes at the 30-minute rate (the guide's default; the app sets no TTL)",
    "W12": "cache writes at the 12-hour rate (upper bound)",
}
HIT_SCENARIOS = {
    "HIT_FREE": "Portkey response-cache HITs are not billed by the model provider ($0); consistent with the HIT "
                "responses lacking Azure headers, not verified",
    "HIT_AS_REPLAYED": "HITs billed as if their replayed usage were new (upper bound)",
}
LOG_ASSUMPTIONS = [
    "L1 Rates: OpenAI's published standard-tier rates (pricing file); Portkey/Azure billing to the course account is "
    "not verified and Portkey's own fees, if any, are not included.",
    "L2 Token categories per call: uncached input = input_tokens - cached_read_tokens - cache_write_tokens; reasoning "
    "tokens are part of output_tokens and are not added again.",
    "L3 Cache-write duration: the API did not return the 30-minute / 12-hour split, so writes are priced under two "
    "scenarios (W30, W12).",
    "L4 Portkey HITs (header x-portkey-cache-status = HIT) replay the original call's usage and are priced under two "
    "scenarios (HIT_FREE, HIT_AS_REPLAYED); they are never counted as provider usage by default.",
    "L5 Calls without a usable usage object (failed calls) are counted but not priced.",
]


def load_usage_log(*paths):
    """Entries from one or more usage logs, de-duplicated by call_id (missing files are skipped)."""
    seen, entries = set(), []
    for path in paths:
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                e = json.loads(line)
                if e["call_id"] not in seen:
                    seen.add(e["call_id"])
                    entries.append({**e, "_source": path})
    return entries


def call_kind(entry):
    """provider_call (reached the model provider), portkey_hit, failed, or unknown_cache_status."""
    if not entry.get("ok"):
        return "failed"
    status = (entry.get("headers") or {}).get("x-portkey-cache-status")
    if status == "HIT":
        return "portkey_hit"
    if status in ("MISS", "DISABLED", "SEMANTIC MISS"):
        return "provider_call"
    return "unknown_cache_status"


def token_categories(usage):
    """Split one call's input into uncached / cached-read / cache-write; None if anything needed is unknown."""
    needed = ("input_tokens", "output_tokens", "cached_read_tokens", "cache_write_tokens")
    if any(usage.get(k) is None for k in needed):
        return None
    uncached = usage["input_tokens"] - usage["cached_read_tokens"] - usage["cache_write_tokens"]
    if uncached < 0:
        raise ValueError("cached and cache-write tokens exceed input tokens")
    return {"uncached_input": uncached, "cached_read": usage["cached_read_tokens"],
            "cache_write": usage["cache_write_tokens"], "output": usage["output_tokens"],
            "reasoning_within_output": usage.get("reasoning_tokens")}


def price_logged_call(entry, pricing, write_ttl="W30", hit_scenario="HIT_FREE"):
    """Estimated USD for one logged call under the named scenarios, or None if not priceable."""
    kind = call_kind(entry)
    if kind == "failed":
        return None
    if kind == "portkey_hit" and hit_scenario == "HIT_FREE":
        return 0.0
    cats = token_categories(entry["usage"])
    if cats is None:
        return None
    writes = {"cache_write_30m_tokens": cats["cache_write"]} if write_ttl == "W30" else \
        {"cache_write_12h_tokens": cats["cache_write"]}
    return call_cost(entry["usage"]["input_tokens"], cats["output"], pricing,
                     cached_read_tokens=cats["cached_read"], **writes)


def summarize_log(entries, pricing):
    """Per workflow: call kinds, mean token categories and mean cost of provider calls (W30 / W12),
    and the cost of HITs under both HIT scenarios."""
    out = {}
    for wf in sorted({e["workflow"] for e in entries}):
        es = [e for e in entries if e["workflow"] == wf]
        provider = [e for e in es if call_kind(e) == "provider_call"]
        hits = [e for e in es if call_kind(e) == "portkey_hit"]
        cats = [token_categories(e["usage"]) for e in provider]
        mean = (lambda k: statistics.mean(c[k] for c in cats)) if cats else (lambda k: None)
        out[wf] = {
            "calls": len(es), "provider_calls": len(provider), "portkey_hits": len(hits),
            "failed": sum(1 for e in es if call_kind(e) == "failed"),
            "unknown_cache_status": sum(1 for e in es if call_kind(e) == "unknown_cache_status"),
            "mean_tokens_provider_calls": {k: mean(k) for k in ("uncached_input", "cached_read", "cache_write",
                                                                 "output")} if cats else None,
            "mean_reasoning_tokens": statistics.mean(c["reasoning_within_output"] or 0 for c in cats) if cats else None,
            "mean_cost_provider_call_usd": {s: statistics.mean(price_logged_call(e, pricing, s) for e in provider)
                                            for s in WRITE_TTL_SCENARIOS} if provider else None,
            "hit_cost_usd": {h: sum(price_logged_call(e, pricing, "W30", h) for e in hits) for h in HIT_SCENARIOS},
            "total_cost_usd": {f"{w}+{h}": sum(price_logged_call(e, pricing, w, h) or 0 for e in es)
                               for w in WRITE_TTL_SCENARIOS for h in HIT_SCENARIOS},
        }
    return out


def per_run_costs(entries, pricing, workflow, write_ttl="W30"):
    """Cost per agent run (e.g. one chat question = all its API calls), provider runs only."""
    runs = {}
    for e in entries:
        if e["workflow"] == workflow and call_kind(e) == "provider_call":
            runs.setdefault(e["run_id"], 0.0)
            runs[e["run_id"]] += price_logged_call(e, pricing, write_ttl)
    return list(runs.values())


def cache_write_reuse(entries, pricing):
    """Per workflow: tokens written to the prompt cache vs tokens read back by provider calls, and the
    write premium paid over the uncached rate (W30), which is wasted if the prefix is never read."""
    r = pricing["rates"]["standard"]["short_context"]
    out = {}
    for wf in sorted({e["workflow"] for e in entries}):
        provider = [token_categories(e["usage"]) for e in entries
                    if e["workflow"] == wf and call_kind(e) == "provider_call"]
        written = sum(c["cache_write"] for c in provider)
        read = sum(c["cached_read"] for c in provider)
        out[wf] = {"cache_write_tokens": written, "cached_read_tokens": read,
                   "write_premium_usd_w30": written * (r["cache_write_30m"] - r["input"]) / PER_MILLION}
    return out
