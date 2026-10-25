"""Tokenomics analysis: measured usage x published rates -> estimated costs, with assumptions.

Reads saved usage records (evidence/), the observed chat figures, and the pricing file; writes
evidence/tokenomics/tokenomics_<date>.json and tokenomics_report_<date>.md. No model calls.

    .venv/bin/python scripts/run_tokenomics.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tokenomics import (  # noqa: E402
    ASSUMPTIONS, load_pricing, load_usage_records, mark_possible_cache_repeats, scale, summarize)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRICING = "evidence/tokenomics/pricing_gpt-6-luna_2026-10-24.json"
DATE = "2026-10-24"

FIELDS = {
    "measured": ["requests", "input_tokens", "output_tokens (PydanticAI RunUsage, per agent run)"],
    "missing (available in PydanticAI/OpenAI usage but never recorded)": [
        "cached input tokens (input_tokens_details.cached_tokens / RunUsage.cache_read_tokens)",
        "cache-write tokens and their TTL (cache_write_tokens; ttl_30m / ttl_12h)",
        "reasoning tokens (output_reasoning_tokens)", "tool_calls for extraction/vision/screen runs",
        "per-request breakdown inside multi-request runs (chat tool calls)",
        "provider cost (RunUsage.cost) and Portkey's billed amount", "latency per call",
        "image token count separate from text tokens"],
    "uncertain": [
        "whether identical repeated calls were served from a Portkey cache and billed (A5)",
        "whether photo input_tokens include image tokens and how gpt-6-luna counts them (A3)",
        "chat figures: observed in server logs and transcribed, raw logs not saved",
        "actual rates applied by Portkey / Azure to the course account (A1)"],
}
KNOWN_UNRECORDED_CALLS = [
    "P7 first chat call (succeeded, then the app crashed reading usage)",
    "P8 first tool call (HTTP 400 from Azure; billing unknown)",
    "P26 and P27 browser intake extractions (944 / 283 shown in the UI each; not saved)",
    "P29 follow-up that failed with HTTP 500 (cross-event-loop error)",
    "P31 browser intake check of Attack A (1,520 / 879 shown in the UI; extraction + screen)",
    "Any calls made outside the app (none known)",
]
# Illustrative only: hypothetical daily activity per staff user, NOT measured
ILLUSTRATIVE_PROFILES = {
    "light (hypothetical)": {"chat": 10, "extraction": 5, "safety_screen": 5, "photo_analysis": 1, "photo_followup": 1},
    "heavy (hypothetical)": {"chat": 60, "extraction": 30, "safety_screen": 30, "photo_analysis": 10,
                             "photo_followup": 20},
}
WORKFLOW_GROUPS = {
    "Chat / tool calling": ["chat"],
    "Shelter report extraction": ["extraction"],
    "Safety screening": ["safety_screen"],
    "Warehouse photo analysis": ["photo_analysis", "photo_followup"],
}
MEASUREMENTS_NEEDED = [
    "Record cached_tokens, cache_write_tokens (with TTL), and reasoning tokens for every call; today the caching "
    "bounds in this report are wide only because these are missing.",
    "Save chat usage per question to a file (it is only in server logs), with tool calls and the per-request split.",
    "Obtain the course Portkey account's actual billing (rates, markups, credits) for the same period and reconcile "
    "it with the estimate.",
    "Measure real activity per staff user per day: chat questions, reports extracted, photos analyzed, follow-ups.",
    "Measure how chat input grows with data size: tool outputs list every shelter and item, so tokens per question "
    "rise with the number of shelters, warehouses, and history (up to 20 messages).",
    "Measure image tokens with real photos at real resolutions (synthetic 1280×820 images only so far).",
    "Count retries, failures, and repeated identical requests (cache hits) in normal use.",
    "Measure latency and peak concurrency (requests per minute) to check rate limits at 100 and 10,000 users.",
    "Decide the service tier (standard vs batch/flex) per workflow; batch/flex halves the published rates but adds "
    "delay.",
]


def main():
    pricing = load_pricing(os.path.join(ROOT, PRICING))
    records = mark_possible_cache_repeats(load_usage_records(ROOT))
    summary = summarize(records, pricing)
    unit = {wf: s["cost_per_call_usd"]["point_mean"] for wf, s in summary.items()}
    composite = {
        "one report through Report intake (extraction + safety screen)": unit["extraction"] + unit["safety_screen"],
        "one chat question (observed mean; tool-using questions cost more)": unit["chat"],
        "one photo analysis + one follow-up": unit["photo_analysis"] + unit["photo_followup"],
    }
    illustration = {name: {users: scale(profile, unit, users) for users in (1, 100, 10_000)}
                    for name, profile in ILLUSTRATIVE_PROFILES.items()}
    measured = [r for r in records if r["measured"]]
    result = {
        "date": DATE, "pricing_file": PRICING, "pricing_sources": pricing["sources"],
        "assumptions": ASSUMPTIONS, "token_fields": FIELDS, "known_unrecorded_calls": KNOWN_UNRECORDED_CALLS,
        "records": records, "summary_by_workflow": summary, "composite_unit_costs_usd": composite,
        "development_spend_estimate_usd": {
            "measured_calls": len(measured),
            "measured_point_estimate": sum(s["total_cost_usd_point"] for w, s in summary.items()
                                           if s["data_quality"].startswith("measured")),
            "observed_chat_point_estimate": sum(s["total_cost_usd_point"] for w, s in summary.items()
                                                if not s["data_quality"].startswith("measured")),
            "note": "Excludes the known unrecorded calls; not a billed amount."},
        "illustrative_scaling_usd_per_day": {"profiles": ILLUSTRATIVE_PROFILES, "cost": illustration,
                                             "warning": "Hypothetical activity levels, not measurements."},
        "measurements_needed": MEASUREMENTS_NEEDED,
    }
    out_json = os.path.join(ROOT, "evidence/tokenomics", f"tokenomics_{DATE}.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with open(os.path.join(ROOT, "evidence/tokenomics", f"tokenomics_report_{DATE}.md"), "w", encoding="utf-8") as f:
        f.write(report(result, pricing))
    print(out_json)


def out_share(summary, rates):
    o = summary["output_tokens"]["mean"] * rates["output"]
    i = summary["input_tokens"]["mean"] * rates["input"]
    return o / (o + i)


def usd(x):
    return f"${x:.6f}" if x < 0.01 else (f"${x:.4f}" if x < 1 else f"${x:,.2f}")


def report(r, p):
    s = r["summary_by_workflow"]
    rates = p["rates"]["standard"]["short_context"]
    lines = [f"# Tokenomics — Disaster FoodBridge ({r['date']})", "",
             "Generated by `scripts/run_tokenomics.py` from saved usage records and the pricing file. All costs are "
             "**estimates** (measured or observed tokens × published API rates), **not billed amounts**.", "",
             "## 1. Published rates used (gpt-6-luna, standard tier, short context ≤ 272K input tokens)", "",
             "| Input | Cached input | Cache write 30 min | Cache write 12 h | Output |", "|---|---|---|---|---|",
             f"| ${rates['input']} | ${rates['cached_input']} | ${rates['cache_write_30m']} | "
             f"${rates['cache_write_12h']} | ${rates['output']} |", "",
             f"Per 1M tokens, USD. Source: {p['sources']['pricing_page']} (checked {p['date_checked']}). Caching "
             f"conditions: {p['sources']['prompt_caching_guide']} (minimum cacheable prompt 1,024 tokens for GPT-5.6 "
             "and later; reads 0.1×, 30-minute writes 1.25×, 12-hour writes 2.5× the input rate; gpt-6-luna is not "
             "named in the guide). Batch/Flex and Fast tiers and long-context rates are in the pricing file.", "",
             "**Not verified:** " + "; ".join(p["not_verified"]) + ".", "",
             "## 2. Usage records: what is measured", ""]
    for k, v in r["token_fields"].items():
        lines += [f"**{k.capitalize()}:**", *[f"- {x}" for x in v], ""]
    lines += ["**Known calls without saved usage (not in the totals):**",
              *[f"- {x}" for x in r["known_unrecorded_calls"]], "",
              "## 3. Assumptions", "", *[f"- {a}" for a in r["assumptions"]], "",
              "## 4. Estimated cost per call, by workflow", "",
              "| Workflow | Data | Calls (requests) | Possible cache repeats | Input tokens mean (min–max) | "
              "Output tokens mean (min–max) | Cost per call: point (caching bounds) |",
              "|---|---|---|---|---|---|---|"]
    names = {"chat": "Chat / tool calling", "extraction": "Shelter report extraction", "safety_screen":
             "Safety screening (P31+)", "photo_analysis": "Warehouse photo analysis", "photo_followup":
             "Photo follow-up question", "chat_probe": "Probe (P7, not a workflow)"}
    for wf in ["chat", "extraction", "safety_screen", "photo_analysis", "photo_followup", "chat_probe"]:
        x = s[wf]
        c, i, o = x["cost_per_call_usd"], x["input_tokens"], x["output_tokens"]
        lines.append(f"| {names[wf]} | {x['data_quality']} | {x['calls']} ({x['requests']}) | "
                     f"{x['possible_cache_repeats']} | {i['mean']:,.0f} ({i['min']:,}–{i['max']:,}) | "
                     f"{o['mean']:,.0f} ({o['min']:,}–{o['max']:,}) | {usd(c['point_mean'])} "
                     f"({usd(c['low_mean'])}–{usd(c['high_mean'])}) |")
    lines += ["", "Point = all input at the uncached rate. Bounds = all input as cached reads (low) or as 30-minute "
              "cache writes (high), only for prompts of at least 1,024 tokens per request (assumption A2).", "",
              "## 5. Composite unit costs (point estimates)", "", "| Unit | Estimated cost |", "|---|---|",
              *[f"| {k} | {usd(v)} |" for k, v in r["composite_unit_costs_usd"].items()], "",
              "## 6. Estimated development spend so far (recorded calls only)", "",
              f"- Measured calls ({r['development_spend_estimate_usd']['measured_calls']}): "
              f"{usd(r['development_spend_estimate_usd']['measured_point_estimate'])}",
              f"- Observed chat calls: {usd(r['development_spend_estimate_usd']['observed_chat_point_estimate'])}",
              f"- {r['development_spend_estimate_usd']['note']}", "",
              "## 7. Scaling: formula and an illustration (hypothetical, not an estimate)", "",
              "Daily cost = users × Σ (calls per user per day × cost per call). The cost per call is from section 4; "
              "**calls per user per day have not been measured**, so the rows below only show orders of magnitude "
              "for two made-up activity levels.", "",
              "| Profile (calls per user per day) | 1 user | 100 users | 10,000 users |", "|---|---|---|---|"]
    for name, costs in r["illustrative_scaling_usd_per_day"]["cost"].items():
        prof = r["illustrative_scaling_usd_per_day"]["profiles"][name]
        desc = ", ".join(f"{k} {v}" for k, v in prof.items())
        lines.append(f"| {name}: {desc} | {usd(costs[1])} | {usd(costs[100])} | {usd(costs[10000])} |")
    ext, scr = s["extraction"]["cost_per_call_usd"]["point_mean"], s["safety_screen"]["cost_per_call_usd"]["point_mean"]
    pa = s["photo_analysis"]
    lines += ["", "## 8. Key findings", "",
              f"- Every workflow costs well under a tenth of a cent per call at published rates: from "
              f"{usd(scr)} (safety screen) to {usd(pa['cost_per_call_usd']['point_mean'])} (photo analysis).",
              f"- The P31 safety screen adds {scr / ext:.0%} to the cost of extracting one report "
              f"({usd(ext)} → {usd(ext + scr)}).",
              "- Output is billed 5× input. Share of the point cost from output tokens: "
              + ", ".join(f"{names[w].lower()} {out_share(s[w], rates):.0%}" for w in
                          ("photo_analysis", "extraction", "safety_screen", "photo_followup", "chat")) + ".",
              "- Caching matters only above 1,024 tokens per request: extraction (~976 input tokens) and the screen "
              "(~410) are below it, so caching cannot change their cost; chat and photo calls are above it, which is "
              "why their bounds are wide.",
              "- Chat figures are the weakest data (observed, not saved) and also the most variable: input grows with "
              "tool outputs and conversation history.",
              f"- {s['photo_analysis']['possible_cache_repeats']} of 8 photo analyses and "
              f"{s['extraction']['possible_cache_repeats']} of 17 extractions exactly repeat earlier calls; whether "
              "Portkey served and billed them is unknown.", "",
              "## 9. Measurements needed before per-user and scale estimates", "",
              *[f"{i}. {m}" for i, m in enumerate(r["measurements_needed"], 1)], ""]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
