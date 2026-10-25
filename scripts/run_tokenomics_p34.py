"""P34: recompute tokenomics from per-call usage logs and compare with the P32 estimates.

Sources: data/live/usage_log.jsonl (normal operation; P34 sample) and evidence/usage/usage_log_p33.jsonl.
Writes, under evidence/tokenomics/: a snapshot of the live log, tokenomics_p34_2026-10-24.json, and
tokenomics_p34_report_2026-10-24.md. No model calls.

    .venv/bin/python scripts/run_tokenomics_p34.py
"""
import json
import os
import shutil
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config  # noqa: E402
from src.tokenomics import (  # noqa: E402
    HIT_SCENARIOS, LOG_ASSUMPTIONS, WRITE_TTL_SCENARIOS, cache_write_reuse, call_kind, load_pricing, load_usage_log,
    per_run_costs, price_logged_call, summarize_log)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV = os.path.join(ROOT, "evidence", "tokenomics")
PRICING = os.path.join(EV, "pricing_gpt-6-luna_2026-10-24.json")
P32 = os.path.join(EV, "tokenomics_2026-10-24.json")
SNAPSHOT = os.path.join(EV, "usage_log_snapshot_p34.jsonl")
P33_LOG = os.path.join(ROOT, "evidence", "usage", "usage_log_p33.jsonl")


def usd(x):
    return "n/a" if x is None else (f"${x:.6f}" if x < 0.01 else f"${x:.4f}")


def main():
    shutil.copyfile(config.USAGE_LOG_PATH, SNAPSHOT)              # data/live is not in git
    pricing = load_pricing(PRICING)
    entries = load_usage_log(SNAPSHOT, P33_LOG)
    summary = summarize_log(entries, pricing)
    reuse = cache_write_reuse(entries, pricing)
    chat_runs = {s: per_run_costs(entries, pricing, "chat", s) for s in WRITE_TTL_SCENARIOS}
    p32 = json.load(open(P32))["summary_by_workflow"]
    new_unit = {
        "chat (per question)": {s: statistics.mean(chat_runs[s]) for s in WRITE_TTL_SCENARIOS},
        "extraction (per call)": summary["extraction"]["mean_cost_provider_call_usd"],
        "safety_screen (per call)": summary["safety_screen"]["mean_cost_provider_call_usd"],
        "photo_analysis (per call)": summary["photo_analysis"]["mean_cost_provider_call_usd"],
        "photo_followup (per call)": summary["photo_followup"]["mean_cost_provider_call_usd"],
    }
    p32_unit = {"chat (per question)": p32["chat"], "extraction (per call)": p32["extraction"],
                "safety_screen (per call)": p32["safety_screen"], "photo_analysis (per call)": p32["photo_analysis"],
                "photo_followup (per call)": p32["photo_followup"]}
    comparison = {k: {"p32_point": p32_unit[k]["cost_per_call_usd"]["point_mean"],
                      "p32_bounds": [p32_unit[k]["cost_per_call_usd"]["low_mean"], p32_unit[k]["cost_per_call_usd"]["high_mean"]],
                      "p34_W30": new_unit[k]["W30"], "p34_W12": new_unit[k]["W12"],
                      "change_W30_pct": (new_unit[k]["W30"] / p32_unit[k]["cost_per_call_usd"]["point_mean"] - 1) * 100}
                  for k in new_unit}
    # Optimization candidate: let later follow-ups on the same photo read the shared prefix instead of rewriting it
    r = pricing["rates"]["standard"]["short_context"]
    fu = [e for e in entries if e["workflow"] == "photo_followup" and call_kind(e) == "provider_call"]
    mean_write = statistics.mean(e["usage"]["cache_write_tokens"] for e in fu)
    saving_per_later_followup = mean_write * (r["cache_write_30m"] - r["cached_input"]) / 1e6
    optimization = {
        "name": "Make photo follow-ups reuse the prompt cache",
        "observation": f"{len(fu)} provider follow-up calls each wrote about {mean_write:,.0f} tokens to the prompt "
                       "cache and read 0, although the questions on the same photo share the instructions, earlier "
                       "analysis, and image. Today the stable content and the question are sent as one user message.",
        "change_to_test": "Send the stable part (earlier analysis + image) as its own message before the question, so "
                          "the cached prefix ends before the part that changes; measure cached_read_tokens on the "
                          "2nd and later questions about the same photo.",
        "estimated_saving_per_later_followup_usd": saving_per_later_followup,
        "estimated_saving_pct_of_followup_W30": saving_per_later_followup / summary["photo_followup"][
            "mean_cost_provider_call_usd"]["W30"] * 100,
        "quality_and_safety": "Same content and instructions, only split into messages; prompt caching returns fresh "
                              "model outputs (unlike Portkey's response cache), so answers should not go stale. Must "
                              "be checked by re-asking the same questions and comparing answers, and by confirming the "
                              "image is still treated as untrusted content. The first question on a photo still pays "
                              "the write.",
        "not_chosen": [
            "Skipping or sampling the safety screen: about 19% of a report-intake cost at P34 rates, but it would "
            "weaken the P31 defense.",
            "Leaning on Portkey's response cache: free repeats, but a cached answer can be stale when the shelter or "
            "inventory data behind an identical question has changed.",
            "Lower reasoning effort or shorter outputs: savings on output tokens, but extraction and vision accuracy "
            "would need re-evaluation first."],
    }
    changes = why_changed(entries, json.load(open(P32))["summary_by_workflow"], summary)
    scenario_totals = {f"{w}+{h}": sum(price_logged_call(e, pricing, w, h) or 0 for e in entries)
                       for w in WRITE_TTL_SCENARIOS for h in HIT_SCENARIOS}
    result = {"sources": [os.path.relpath(SNAPSHOT, ROOT), os.path.relpath(P33_LOG, ROOT)],
              "entries": len(entries), "assumptions": LOG_ASSUMPTIONS, "write_ttl_scenarios": WRITE_TTL_SCENARIOS,
              "hit_scenarios": HIT_SCENARIOS, "summary_by_workflow": summary, "cache_write_reuse": reuse,
              "chat_cost_per_question": chat_runs, "comparison_with_p32": comparison, "why_changed": changes,
              "scenario_totals_usd": scenario_totals, "optimization_to_test": optimization}
    with open(os.path.join(EV, "tokenomics_p34_2026-10-24.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    with open(os.path.join(EV, "tokenomics_p34_report_2026-10-24.md"), "w", encoding="utf-8") as f:
        f.write(report(result, pricing))
    print("written")


def run_tokens(entries, workflow):
    """Mean input/output tokens and provider requests per agent run (provider calls only)."""
    runs = {}
    for e in entries:
        if e["workflow"] == workflow and call_kind(e) == "provider_call":
            t = runs.setdefault(e["run_id"], [0, 0, 0])
            t[0] += e["usage"]["input_tokens"]
            t[1] += e["usage"]["output_tokens"]
            t[2] += 1
    return {"runs": len(runs), "input": statistics.mean(t[0] for t in runs.values()),
            "output": statistics.mean(t[1] for t in runs.values()),
            "requests": statistics.mean(t[2] for t in runs.values())}


def why_changed(entries, p32, summary):
    c = run_tokens(entries, "chat")
    cs = summary["chat"]["mean_tokens_provider_calls"]
    cached_share = cs["cached_read"] / (cs["uncached_input"] + cs["cached_read"] + cs["cache_write"]) * 100
    out = [
        "Method: P32 had only per-question totals, so it priced all input at the uncached rate (point) with "
        "all-cached / all-written bounds, and counted possible Portkey repeats as billed (A2, A5). P34 prices each "
        "logged call from the token categories the API reported, and separates Portkey HITs (priced only in "
        "scenarios).",
        f"Chat (-): P34 questions used more input ({c['input']:,.0f} vs {p32['chat']['input_tokens']['mean']:,.0f} "
        f"tokens per question, {c['requests']:.1f} requests each) but {cached_share:.0f}% of chat input was a cached "
        f"read at 0.1x; output fell from {p32['chat']['output_tokens']['mean']:,.0f} to {c['output']:,.0f} tokens. "
        "Different questions were asked, so part of the change is the question mix.",
    ]
    for wf, label in (("extraction", "Extraction"), ("safety_screen", "Safety screen")):
        t = run_tokens(entries, wf)
        out.append(f"{label} (-): no caching in either run (prompts below 1,024 tokens); output was lower "
                   f"({t['output']:,.0f} vs {p32[wf]['output_tokens']['mean']:,.0f} tokens). Most P32 records came from the P30/P31 "
                   "injection evaluation (attack reports produced long outputs); P34 used three ordinary reports.")
    for wf, label in (("photo_analysis", "Photo analysis"), ("photo_followup", "Photo follow-up")):
        t = run_tokens(entries, wf)
        m = summary[wf]["mean_tokens_provider_calls"]
        out.append(f"{label}: most input ({m['cache_write']:,.0f} of {t['input']:,.0f} tokens) was a cache write "
                   "at 1.25x (W30) or 2.5x (W12) and none was read back, so input cost is above P32's all-uncached "
                   f"point estimate; the net change also reflects output ({t['output']:,.0f} vs "
                   f"{p32[wf]['output_tokens']['mean']:,.0f} tokens). Under W12 both photo workflows cost more than "
                   "P32's point estimate.")
    out.append("Sample size: P34 has 2-5 provider calls per workflow; differences of this size can come from the "
               "inputs chosen, not only from pricing method.")
    return out


def report(r, p):
    s = r["summary_by_workflow"]
    L = ["# Tokenomics from per-call usage logs (P34, 2026-10-24)", "",
         f"Sources: `{r['sources'][0]}` (snapshot of `data/live/usage_log.jsonl`) and `{r['sources'][1]}`; "
         f"{r['entries']} API calls. All costs are **estimates at OpenAI's published standard rates**, not billed "
         "amounts.", "", "## Assumptions and scenarios", "", *[f"- {a}" for a in r["assumptions"]], "",
         *[f"- **{k}**: {v}" for k, v in {**r["write_ttl_scenarios"], **r["hit_scenarios"]}.items()], "",
         "## Calls by kind", "",
         "| Workflow | Calls | Reached provider (MISS) | Portkey HIT (replayed usage) | Failed |", "|---|---|---|---|---|"]
    for wf, x in s.items():
        L.append(f"| {wf} | {x['calls']} | {x['provider_calls']} | {x['portkey_hits']} | {x['failed']} |")
    L += ["", "## Measured token categories (mean per provider call)", "",
          "| Workflow | Uncached input | Cached read | Cache write | Output (incl. reasoning) | Reasoning |",
          "|---|---|---|---|---|---|"]
    for wf, x in s.items():
        m = x["mean_tokens_provider_calls"]
        L.append(f"| {wf} | {m['uncached_input']:,.0f} | {m['cached_read']:,.0f} | {m['cache_write']:,.0f} | "
                 f"{m['output']:,.0f} | {x['mean_reasoning_tokens']:,.0f} |")
    L += ["", "## Estimated cost: P32 vs P34", "",
          "| Unit | P32 point (P32 caching bounds) | P34, writes at 30 min (W30) | P34, writes at 12 h (W12) | Change (W30 vs P32 point) |",
          "|---|---|---|---|---|"]
    for k, c in r["comparison_with_p32"].items():
        L.append(f"| {k} | {usd(c['p32_point'])} ({usd(c['p32_bounds'][0])}–{usd(c['p32_bounds'][1])}) | "
                 f"{usd(c['p34_W30'])} | {usd(c['p34_W12'])} | {c['change_W30_pct']:+.0f}% |")
    L += ["", "P34 costs are for calls that reached the provider (MISS); Portkey HITs are excluded here and shown "
          "below.", "", "## What changed and why", "", *[f"- {x}" for x in r["why_changed"]], "", "## All logged calls under each scenario (total USD)", "",
          "| Scenario | Total |", "|---|---|", *[f"| {k} | {usd(v)} |" for k, v in r["scenario_totals_usd"].items()],
          "", "## Prompt-cache writes vs reads (provider calls)", "",
          "| Workflow | Tokens written | Tokens read | Write premium paid (W30) |", "|---|---|---|---|"]
    for wf, x in r["cache_write_reuse"].items():
        L.append(f"| {wf} | {x['cache_write_tokens']:,} | {x['cached_read_tokens']:,} | {usd(x['write_premium_usd_w30'])} |")
    o = r["optimization_to_test"]
    L += ["", f"## Optimization worth testing next: {o['name']}", "", f"- **Observed:** {o['observation']}",
          f"- **Change to test:** {o['change_to_test']}",
          f"- **Estimated saving:** about {usd(o['estimated_saving_per_later_followup_usd'])} per 2nd-or-later "
          f"follow-up on the same photo (~{o['estimated_saving_pct_of_followup_W30']:.0f}% of a follow-up's W30 "
          "cost), if the prefix is read at the cached rate instead of written. Not yet measured.",
          f"- **Quality and safety:** {o['quality_and_safety']}", "- **Considered but not chosen:**",
          *[f"  - {x}" for x in o["not_chosen"]], ""]
    return "\n".join(L)


if __name__ == "__main__":
    main()
