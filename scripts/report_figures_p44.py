"""P44: every number used in report.html, computed from saved evidence (no model calls).

    .venv/bin/python scripts/report_figures_p44.py   -> evidence/report/report_figures_p44.json

Sources: evidence/tokenomics (P34 per-call log pricing, P35 follow-up cache test, pricing file),
evidence/report/agent_trace_p44.json (agent trace), evidence/impact (P40/P41 evaluation).
Monthly scenarios use HYPOTHETICAL activity profiles (same as P32) and a 30-day month: assumptions,
not measurements. Costs are estimates at OpenAI's published standard rates, not bills.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from src.tokenomics import load_pricing, load_usage_log, price_logged_call  # noqa: E402

EV = os.path.join(ROOT, "evidence")
J = lambda *p: json.load(open(os.path.join(EV, *p)))  # noqa: E731

pricing = load_pricing(os.path.join(EV, "tokenomics", "pricing_gpt-6-luna_2026-10-24.json"))
p34 = J("tokenomics", "tokenomics_p34_2026-10-24.json")
p35 = J("tokenomics", "p35_followup_cache", "comparison_p35.json")
trace = J("report", "agent_app_run_p45.json")
trace["calls"] = [{"call": i + 1, "latency_ms": c["latency_ms"], "portkey_cache_status": c["portkey"],
                   **{k: c[k] for k in ("input_tokens", "cached_read_tokens", "cache_write_tokens", "reasoning_tokens",
                                        "output_tokens")}} for i, c in enumerate(st for st in trace["steps"] if "call" in st)]
trace["usage_total"] = {"requests": 2, "input_tokens": sum(c["input_tokens"] for c in trace["calls"]),
                        "output_tokens": sum(c["output_tokens"] for c in trace["calls"]), "tool_calls": 1}
impact = J("impact", "impact_eval_results.json")
rerun = J("impact", "impact_eval_results_p41_rerun_after_fix.json")

s = p34["summary_by_workflow"]
tokens = {wf: {**s[wf]["mean_tokens_provider_calls"], "reasoning": s[wf]["mean_reasoning_tokens"],
               "provider_calls": s[wf]["provider_calls"], "portkey_hits": s[wf]["portkey_hits"]}
          for wf in ("chat", "extraction", "safety_screen", "photo_analysis", "photo_followup")}

# Trace run, priced with the same function as the usage log analysis
trace_entries = load_usage_log(os.path.join(EV, "report", "agent_app_run_p45_usage.jsonl"))   # P45: the one traced app run
trace_cost = {w: sum(price_logged_call(e, pricing, w) for e in trace_entries) for w in ("W30", "W12")}

chat_q = {w: sum(p34["chat_cost_per_question"][w]) / len(p34["chat_cost_per_question"][w]) for w in ("W30", "W12")}
unit = {
    "chat question (P34 mean of 5)": chat_q,
    "report intake (extraction + safety screen)": {w: s["extraction"]["mean_cost_provider_call_usd"][w]
                                                   + s["safety_screen"]["mean_cost_provider_call_usd"][w]
                                                   for w in ("W30", "W12")},
    "photo analysis": s["photo_analysis"]["mean_cost_provider_call_usd"],
    "photo follow-up, before P35 change": s["photo_followup"]["mean_cost_provider_call_usd"],
}
later = p35["comparison"]["photo A, later questions"]
n_later = later["optimized"]["provider_calls"]
unit["photo follow-up, 2nd+ on same photo, after P35 change"] = {
    "W30": later["optimized"]["cost_W30"] / n_later, "W12": later["optimized"]["cost_W12"] / n_later}

PROFILES = {"light (hypothetical)": {"chat": 10, "intake": 5, "photo": 1, "followup": 1},
            "heavy (hypothetical)": {"chat": 60, "intake": 30, "photo": 10, "followup": 20}}
DAYS = 30


def per_user_month(profile, w, optimized):
    fu_first = unit["photo follow-up, before P35 change"][w]
    fu_later = unit["photo follow-up, 2nd+ on same photo, after P35 change"][w] if optimized else fu_first
    photos, followups = profile["photo"], profile["followup"]
    first = min(photos, followups)                      # one first question per analyzed photo
    fu = first * fu_first + (followups - first) * fu_later
    day = (profile["chat"] * unit["chat question (P34 mean of 5)"][w]
           + profile["intake"] * unit["report intake (extraction + safety screen)"][w]
           + photos * unit["photo analysis"][w] + fu)
    return day * DAYS


scenarios = {}
for name, prof in PROFILES.items():
    for w in ("W30", "W12"):
        for opt in (False, True):
            m = per_user_month(prof, w, opt)
            scenarios[f"{name} | {w} | follow-up cache {'on' if opt else 'off'}"] = {
                "per_user_month": m, "100_users_month": m * 100, "10000_users_month": m * 10000}

acc = impact["accuracy"]
rel_after = rerun["reliability"]
count = lambda cases, v: sum(1 for c in cases for k in c["checks"] if k["pass"] is v)  # noqa: E731
figures = {
    "sources": ["evidence/tokenomics/tokenomics_p34_2026-10-24.json",
                "evidence/tokenomics/p35_followup_cache/comparison_p35.json",
                "evidence/report/agent_app_run_p45.json", "evidence/impact/impact_eval_results.json",
                "evidence/impact/impact_eval_results_p41_rerun_after_fix.json"],
    "rates_per_million_usd": pricing["rates"]["standard"]["short_context"],
    "tokens_mean_per_provider_call_p34": tokens,
    "trace": {"calls": trace["calls"], "cost_estimate_usd": trace_cost, "usage_total": trace["usage_total"]},
    "unit_costs_usd": unit,
    "p34_all_calls_scenarios_usd": p34["scenario_totals_usd"],
    "monthly_scenarios_usd (30 days, hypothetical profiles)": scenarios,
    "profiles_per_user_per_day": PROFILES,
    "p35": {g: {k: v for k, v in x.items()} for g, x in p35["comparison"].items()},
    "p35_checks": {k: v for k, v in p35["checks"].items() if k != "failures"},
    "accuracy": {"cases": len(acc), "fields": sum(c["fields_compared"] for c in acc),
                 "mismatches": sum(len(c["mismatches"]) for c in acc)},
    "reliability_p40": {"pass": count(impact["reliability"], True), "fail": count(impact["reliability"], False),
                        "exploratory": count(impact["reliability"], None)},
    "reliability_after_fix_p41": {"pass": count(rel_after, True), "fail": count(rel_after, False),
                                  "exploratory": count(rel_after, None)},
    "planning_timings_ms": impact["planning_efficiency"]["timings"],
    "plan_ab_median_ms_across_saved_runs": sorted(
        J("impact", f)["planning_efficiency"]["timings"]["calculate_allocation (Plan A + B)"]["median_ms"]
        for f in ("impact_eval_results_run1.json", "impact_eval_results.json",
                  "impact_eval_results_p41_rerun_after_fix.json")),
    "extraction_timing": {k: v for k, v in impact["extraction_efficiency"].items() if k.startswith("summary")},
}
os.makedirs(os.path.join(EV, "report"), exist_ok=True)
json.dump(figures, open(os.path.join(EV, "report", "report_figures_p44.json"), "w"), indent=2)
print(json.dumps({"unit": unit, "trace_cost": trace_cost,
                  "scenarios": {k: {kk: round(vv, 4) for kk, vv in v.items()} for k, v in scenarios.items()},
                  "acc": figures["accuracy"], "rel": [figures["reliability_p40"], figures["reliability_after_fix_p41"]]},
                 indent=1))
