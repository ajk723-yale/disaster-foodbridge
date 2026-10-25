"""Pure builders for draft needs, allocation, and supply-request facts.

No file or database access: callers pass already-loaded logs. Used by the agent's
read-only tools (current drafts) and by finalization (the request snapshot saved
with a finalized plan), so both share one implementation.
"""
from fractions import Fraction

from src.allocation import compute_needs
from src.planning import build_plan
from src.records import incoming_breakdown, latest_validated, newer_pending
from src.schemas import GENERAL_TAG


def _num(value):
    if isinstance(value, Fraction):
        return int(value) if value.denominator == 1 else float(value)
    return value


def _iso(ts):
    return ts.isoformat() if ts is not None and ts == ts else None  # ts == ts filters NaT


def shelter_needs_from_logs(shelter_log, commitments, plan_config):
    """Need, food on hand or on its way, and unmet demand per shelter, from the latest
    validated reports. General meals and each special diet are kept separate."""
    latest = latest_validated(shelter_log, ["shelter_id"], "reported_at")
    pending = newer_pending(shelter_log, latest, ["shelter_id"], "reported_at")
    rows = [] if latest is None or latest.empty else latest.to_dict("records")
    pending_rows = [] if pending is None or pending.empty else pending.to_dict("records")
    validated_ids = {r["shelter_id"] for r in rows}
    pending_ids = {r["shelter_id"] for r in pending_rows}
    reported = {r["shelter_id"]: _iso(r["reported_at"]) for r in rows}

    breakdown, incoming_flags = incoming_breakdown(latest, commitments)
    incoming = {key: sum(states.values()) for key, states in breakdown.items()}
    needs = compute_needs(rows, incoming, plan_config)
    no_incoming = {"committed_not_shipped": 0, "shipped_not_confirmed": 0, "delivered_after_report": 0}

    def line_out(l, tag):
        states = breakdown.get((l["shelter_id"], tag), no_incoming)
        return {
            "shelter_id": l["shelter_id"],
            "shelter_name": l["shelter_name"],
            "report_time": reported[l["shelter_id"]],
            "people": "unknown" if l["people"] is None else l["people"],
            "need_meals": l["need_meals"],
            "on_hand_at_report_meals": _num(l["on_hand_meals"]),
            "approved_not_shipped_meals": states["committed_not_shipped"],
            "shipped_not_confirmed_meals": states["shipped_not_confirmed"],
            "still_on_its_way_meals": states["committed_not_shipped"] + states["shipped_not_confirmed"],
            "delivered_after_report_meals": states["delivered_after_report"],
            "unmet_meals": l["unmet_meals"],
            "newer_report_pending_validation": l["shelter_id"] in pending_ids,
        }

    general = [line_out(l, GENERAL_TAG) for l in needs["general"]]
    special = []
    for group in needs["special"]:
        lines = [line_out(l, group["diet_tag"]) for l in group["lines"]]
        special.append({
            "diet_category": group["diet_tag"],
            "total_unmet_meals_known": sum(l["unmet_meals"] for l in lines if l["unmet_meals"] is not None),
            "complete": not group["missing_info"],
            "shelters": lines,
        })

    flags = [f"{f['shelter_id']} ({f['diet_tag']}): {f['message']}" for f in needs["flags"] + incoming_flags]
    for sid in sorted(pending_ids & validated_ids):
        flags.append(f"{sid}: a newer report is pending validation; figures use the last validated report")
    not_included = [{"shelter_id": r["shelter_id"], "shelter_name": r["shelter_name"],
                     "reported_at": _iso(r["reported_at"])}
                    for r in pending_rows if r["shelter_id"] not in validated_ids]
    for r in not_included:
        flags.append(f"{r['shelter_id']}: no validated report yet, so its needs are not calculated")

    result = {
        "planning": {**plan_config, "need_rounding": "need rounded up to whole meals",
                     "unmet_formula": "need - on hand at report - still on its way - delivered after report"},
        "general_meals": {"total_unmet_meals": sum(l["unmet_meals"] for l in general), "shelters": general},
        "special_diets": special,
        "shelters_without_validated_report": not_included,
        "flags": flags,
    }
    if not rows:
        result["note"] = "No validated shelter reports are available, so needs cannot be calculated."
    return result


DRAFT_NOTICE = ("DRAFT for staff review. Not a finalized allocation: nothing has been approved, "
                "reserved, or dispatched.")


def allocation_from_logs(shelter_log, inventory_log, commitments, plan_config, commitment_issues=()):
    """Plan A (feasible now) and Plan B (meet all validated unmet demand) from build_plan."""
    plan = build_plan(shelter_log, inventory_log, commitments, plan_config)
    g = plan["general"]

    general_lines = [{
        "shelter_id": l["shelter_id"],
        "shelter_name": l["shelter_name"],
        "unmet_meals": l["unmet_meals"],
        "plan_a_meals": l["allocated_meals"],
        "plan_a_shortfall_meals": l["shortfall_meals"],
        "plan_b_meals": l["unmet_meals"],
    } for l in g["lines"]]

    reasons = {"ok": None,
               "shortage": "stock is short; staff must decide how to distribute (not split automatically)",
               "no_stock": "no stock available; staff must decide and procure",
               "missing_info": "special-needs count is unknown; confirm before planning"}
    special, plan_b_procurement = [], {"general": g["shortage_meals"]}
    for group in plan["special"]:
        tag = group["diet_tag"]
        special.append({
            "diet_category": tag,
            "status": group["status"],
            "available_meals": group["available_meals"],
            "total_unmet_meals_known": group["total_unmet_meals"],
            "shortage_meals_known": group["shortage_meals"],
            "staff_action": reasons[group["status"]],
            "shelters": [{
                "shelter_id": l["shelter_id"],
                "shelter_name": l["shelter_name"],
                "people": "unknown" if l["people"] is None else l["people"],
                "unmet_meals": l["unmet_meals"],
                "plan_a_meals": l["suggested_meals"],   # None: staff decision needed
                "plan_b_meals": l["unmet_meals"],       # None: unknown until confirmed
            } for l in group["lines"]],
        })
        plan_b_procurement[tag] = group["shortage_meals"] if group["status"] != "missing_info" else \
            f"unknown until counts are confirmed (known shortage: {group['shortage_meals']})"

    # Data warnings: shelter-side flags (incl. pending reports and delivery states) from the
    # needs calculation, then stock/special-diet flags and pending inventory counts from the
    # plan that the shelter-side flags don't already cover
    needs = shelter_needs_from_logs(shelter_log, commitments, plan_config)
    warnings = list(needs["flags"])
    for f in plan["flags"]:
        if not any(f["message"] in w for w in warnings):
            where = f" at {f['shelter_id']}" if f["shelter_id"] else ""
            warnings.append(f"{f['diet_tag']}{where}: {f['message']}")
    warnings += [w for w in plan["warnings"] if "inventory count" in w]
    warnings += [f"dispatch log row {i['row']}: {i['message']}" for i in commitment_issues]

    result = {
        "status": DRAFT_NOTICE,
        "planning": {**plan_config, "rounding": "need rounded up; stock rounded down; Plan A split by "
                                                "largest remainder (ties: larger unmet, then shelter_id)"},
        "general_meals": {
            "available_meals": g["available_meals"],
            "total_unmet_meals": g["total_unmet_meals"],
            "plan_a_total_meals": g["allocated_meals"],
            "shortage_meals": g["shortage_meals"],
            "shelters": general_lines,
        },
        "plan_b_additional_procurement_meals": plan_b_procurement,
        "special_diets": special,
        "data_warnings": warnings,
        "plan_fingerprint": plan["fingerprint"],
    }
    if not g["lines"]:
        result["note"] = "No validated shelter reports are available, so no allocation can be drafted."
    return result


REQUEST_NOTICE = ("DRAFT requiring staff review. Not sent to anyone. No allocation has been finalized, "
                  "approved, reserved, or dispatched.")
REQUEST_PLACEHOLDERS = {
    "date": "[DATE]",
    "reference_number": "[REFERENCE NUMBER]",
    "municipality": "[MUNICIPALITY NAME]",
    "recipient": "[RECIPIENT: PREFECTURAL DISASTER HEADQUARTERS OR NATIONAL GOVERNMENT CONTACT]",
    "sender": "[SENDER NAME, TITLE, DEPARTMENT]",
    "contact": "[CONTACT PHONE / EMAIL]",
    "planning_period_start": "[PLANNING PERIOD START DATE/TIME]",
    "delivery_location": "[DELIVERY LOCATION / RECEIVING WAREHOUSE]",
    "delivery_deadline": "[REQUESTED DELIVERY DATE/TIME]",
}


def supply_request_from_allocation(allocation):
    """Facts for a supply request, taken only from a calculate_allocation result."""
    g = allocation["general_meals"]
    special = []
    for s in allocation["special_diets"]:
        if s["status"] == "missing_info":
            additional = f"to be confirmed (counts unknown; known shortage {s['shortage_meals_known']})"
        else:
            additional = s["shortage_meals_known"]
        special.append({
            "diet_category": s["diet_category"],
            "status": s["status"],
            "known_unmet_meals": s["total_unmet_meals_known"],
            "available_meals": s["available_meals"],
            "additional_meals_to_request": additional,
            "shelters": [{"shelter_id": l["shelter_id"], "shelter_name": l["shelter_name"], "people": l["people"],
                          "unmet_meals": l["unmet_meals"]} for l in s["shelters"]],
        })
    result = {
        "status": REQUEST_NOTICE,
        "planning_period": {
            "window_hours": allocation["planning"]["planning_window_hours"],
            "meals_per_person_per_day": allocation["planning"]["meals_per_person_per_day"],
            "start": REQUEST_PLACEHOLDERS["planning_period_start"],
        },
        "basis": "calculate_allocation draft: Plan B (meet all validated unmet demand) minus available stock",
        "general_meals": {
            "total_unmet_meals": g["total_unmet_meals"],
            "available_meals": g["available_meals"],
            "additional_meals_to_request": g["shortage_meals"],
            "shortfall_by_shelter_after_plan_a": [
                {"shelter_id": l["shelter_id"], "shelter_name": l["shelter_name"],
                 "shortfall_meals": l["plan_a_shortfall_meals"]} for l in g["shelters"]],
        },
        "special_diet_requirements": special,
        "pending_or_uncertain_data": allocation["data_warnings"],
        "placeholders": REQUEST_PLACEHOLDERS,
        "allocation_plan_fingerprint": allocation["plan_fingerprint"],
    }
    nothing_known = g["shortage_meals"] == 0 and all(s["additional_meals_to_request"] == 0 for s in special)
    if allocation.get("note"):
        result["note"] = allocation["note"] + " A supply request cannot be drafted from data."
    elif nothing_known:
        result["note"] = "No additional supplies are needed based on current validated data."
    return result
