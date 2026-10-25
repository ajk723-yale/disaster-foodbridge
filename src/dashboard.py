"""Dashboard view model: combines the outputs of the existing calculations for display.

No new business logic. Every figure comes from the same functions the chat agent uses
(src.agent_tools: get_shelter_reports, get_warehouse_inventory, calculate_shelter_needs,
calculate_allocation), which read the latest validated data. This module only regroups
those outputs into three sections (current situation, actions required, allocation plan)
and adds display ratios (bar shares, percent covered).

Action items are derived from the structured tool outputs (pending reports, missing reports,
unknown special-diet counts, pending inventory counts, special-diet shortages). Any data
warning they do not cover is still listed as a generic note, so no warning is dropped.
"""
from src import agent_tools
from src.timeutil import display_time

DIET_NAMES = {"allergy_free": "allergy-free", "halal": "halal", "infant_formula": "infant formula"}

# Order in the action list (lower first). Shortages need a decision; then data that is missing,
# unknown, or not yet validated, by how much of the plan it can change.
# Allocation statuses that mean "not enough stock" (no_stock = none at all). P41 fix F2.
SHORTAGE_STATUSES = ("shortage", "no_stock")

PRIORITY = {"special_diet_shortage": 1, "missing_report": 2, "unknown_special_count": 3,
            "pending_report": 4, "pending_inventory_count": 5, "other_note": 6}


def diet_name(category):
    return DIET_NAMES.get(category, category.replace("_", " "))


def when(value):
    """Short display time (display timezone) for messages; unparseable values are shown as given."""
    try:
        return display_time(value, fmt="%b %d %H:%M") if value else "an earlier time"
    except (ValueError, TypeError):
        return str(value)


def _share(part, whole):
    return part / whole if whole else 0.0


def _action(kind, severity, title, why, next_step, tab=None, covers=(), places=()):
    """places: shelter or warehouse IDs the item is about (used by the map's details panel)."""
    return {"kind": kind, "priority": PRIORITY[kind], "severity": severity, "title": title, "why": why,
            "next_step": next_step, "tab": tab, "covers": list(covers), "places": list(places)}


def _actions(reports, inventory, needs, allocation):
    actions = []
    for d in allocation["special_diets"]:
        if d["status"] in SHORTAGE_STATUSES:
            shelters = ", ".join(s["shelter_name"] for s in d["shelters"])
            stock = (f"None in stock for {d['total_unmet_meals_known']:,} needed" if not d["available_meals"] else
                     f"{d['available_meals']:,} in stock for {d['total_unmet_meals_known']:,} needed")
            actions.append(_action(
                "special_diet_shortage", "shortage",
                f"Not enough {diet_name(d['diet_category'])} meals: {d['shortage_meals_known']:,} short",
                f"{stock} ({shelters}). "
                "Special-diet meals cannot be replaced with general meals, so neither plan can cover this.",
                d.get("staff_action") or "Decide how to share the stock and request more before finalizing.",
                "review", covers=[d["diet_category"]], places=[s["shelter_id"] for s in d["shelters"]]))
    for m in needs.get("shelters_without_validated_report", []):
        waiting = f" A report from {when(m['reported_at'])} is waiting." if m.get("reported_at") else ""
        actions.append(_action(
            "missing_report", "uncertain", f"{m['shelter_name']} ({m['shelter_id']}) has no validated report",
            "Its evacuees are not counted, so this shelter receives nothing in either plan." + waiting,
            "Confirm the report with the shelter, then enter and approve it in Report intake.", "intake",
            covers=[m["shelter_id"]], places=[m["shelter_id"]]))
    for d in allocation["special_diets"]:
        for s in d["shelters"]:
            if s["people"] == "unknown":
                actions.append(_action(
                    "unknown_special_count", "uncertain",
                    f"{s['shelter_name']} ({s['shelter_id']}): number of people needing "
                    f"{diet_name(d['diet_category'])} meals is unknown",
                    f"No {diet_name(d['diet_category'])} meals can be planned for them, and the shelter's general-meal "
                    "need may be overstated.",
                    "Ask the shelter for the count, then enter a corrected report in Report intake.", "intake",
                    covers=[s["shelter_id"], d["diet_category"]], places=[s["shelter_id"]]))
    validated_at = {r["shelter_id"]: r["reported_at"] for r in reports["validated_shelters"]}
    for p in reports["newer_reports_pending_validation"]:
        if not p.get("has_validated_report"):
            continue                                     # listed above as a missing validated report
        actions.append(_action(
            "pending_report", "uncertain",
            f"{p['shelter_name']} ({p['shelter_id']}): newer report waiting for validation",
            f"Figures use the validated report from {when(validated_at.get(p['shelter_id']))}; the "
            f"newer one from {when(p['reported_at'])} may change this shelter's need.",
            "Check the newer report and, if correct, enter and approve it in Report intake.", "intake",
            covers=[p["shelter_id"]], places=[p["shelter_id"]]))
    last_count = {}
    for item in inventory.get("items", []):
        last_count[(item["warehouse_id"], item["item_id"])] = item.get("counted_at")
    waiting = {}                                     # one action per item, even with several waiting counts
    for c in inventory.get("newer_counts_pending_validation", []):
        waiting.setdefault((c["warehouse_id"], c["item_id"]), []).append(c)
    for (wh, item_id), counts in waiting.items():
        c = counts[-1]
        times = ", ".join(when(x["counted_at"]) for x in counts)
        previous = last_count.get((wh, item_id))
        if previous:
            title = f"Newer stock count for {c['item_name']} at {wh} is not validated"
            why = (f"Available meals use the earlier count from {when(previous)}; the newer count from {times} "
                   "may change the stock.")
        else:                                        # P41: no validated count exists, so nothing is "earlier"
            title = f"No validated stock count for {c['item_name']} at {wh}"
            why = (f"This item is not included in available meals until a count is validated (waiting count"
                   f"{'s' if len(counts) > 1 else ''}: {times}).")
        actions.append(_action(
            "pending_inventory_count", "uncertain", title, why,
            "Confirm the count with the warehouse. (Inventory counts cannot be validated in this app yet.)",
            None, covers=[wh, item_id], places=[wh]))
    covered_markers = {
        "missing_report": "no validated report", "unknown_special_count": "unknown",
        "pending_report": "newer report is pending", "pending_inventory_count": "newer inventory count",
        "special_diet_shortage": "short"}
    for w in allocation.get("data_warnings", []):
        w = str(w)
        # Only specific actions can cover a warning; generic notes never do (P41 fix F1: "other_note"
        # has no marker, which raised KeyError once a second unmatched warning arrived).
        if any(covered_markers.get(a["kind"]) and covered_markers[a["kind"]] in w
               and all(k in w for k in a["covers"][:1]) for a in actions):
            continue
        place = w.split(" ", 1)[0].split(":", 1)[0]
        actions.append(_action("other_note", "uncertain", f"Data note: {w}",
                               "This warning does not match a specific action type, so it is shown as written.",
                               "Check this before finalizing the plan.", "review",
                               places=[place] if place[:3] in ("SH-", "WH-") else []))
    actions.sort(key=lambda a: a["priority"])
    for i, a in enumerate(actions, 1):
        a["rank"] = i
    return actions


def build_dashboard(reports, inventory, needs, allocation):
    """Pure function over the four tool outputs. Returns a dict for the dashboard view."""
    general = allocation["general_meals"]
    available, unmet = general["available_meals"], general["total_unmet_meals"]
    additional = allocation["plan_b_additional_procurement_meals"].get("general", general["shortage_meals"])

    need_rows = {r["shelter_id"]: r for r in needs["general_meals"]["shelters"]}
    report_rows = {r["shelter_id"]: r for r in reports["validated_shelters"]}
    pending = {r["shelter_id"]: r for r in reports["newer_reports_pending_validation"]}
    scale = max([max(r["unmet_meals"], r["plan_b_meals"]) for r in general["shelters"]] or [1]) or 1
    plan_rows, details = [], []
    for r in general["shelters"]:
        plan_rows.append({
            "shelter_id": r["shelter_id"], "shelter_name": r["shelter_name"], "unmet_meals": r["unmet_meals"],
            "plan_a_meals": r["plan_a_meals"], "plan_a_shortfall_meals": r["plan_a_shortfall_meals"],
            "plan_b_meals": r["plan_b_meals"],
            "plan_a_share": _share(r["plan_a_meals"], scale), "plan_a_short_share": _share(r["plan_a_shortfall_meals"], scale),
            "plan_b_share": _share(r["plan_b_meals"], scale)})
        n, rep = need_rows.get(r["shelter_id"], {}), report_rows.get(r["shelter_id"], {})
        details.append({
            "shelter_id": r["shelter_id"], "shelter_name": r["shelter_name"], "evacuees": rep.get("evacuee_count"),
            "general_people": n.get("people"), "need_meals": n.get("need_meals"),
            "on_hand_meals": n.get("on_hand_at_report_meals"),
            "on_its_way_meals": (n.get("still_on_its_way_meals") or 0) + (n.get("delivered_after_report_meals") or 0),
            "unmet_meals": r["unmet_meals"], "reported_at": rep.get("reported_at") or n.get("report_time"),
            "validated_by": rep.get("validated_by"),
            "newer_report_at": pending.get(r["shelter_id"], {}).get("reported_at")})

    special_by_shelter = {}
    for d in allocation["special_diets"]:
        for s in d["shelters"]:
            special_by_shelter.setdefault(s["shelter_id"], []).append({
                "diet_category": d["diet_category"], "people": s["people"], "unmet_meals": s["unmet_meals"],
                "plan_a_meals": s["plan_a_meals"], "diet_status": d["status"]})
    for row in details:
        row["special_diets"] = special_by_shelter.get(row["shelter_id"], [])

    warehouses = {}
    for item in inventory.get("items", []):
        w = warehouses.setdefault(item["warehouse_id"], {"warehouse_id": item["warehouse_id"], "items": [],
                                                         "pending_counts": []})
        w["items"].append({k: item.get(k) for k in ("item_name", "diet_category", "quantity", "unit",
                                                     "meal_equivalents", "counts_as_meals", "counted_at")})
    for c in inventory.get("newer_counts_pending_validation", []):
        warehouses.setdefault(c["warehouse_id"], {"warehouse_id": c["warehouse_id"], "items": [],
                                                  "pending_counts": []})["pending_counts"].append(c)

    special = []
    for d in allocation["special_diets"]:
        unknown = any(s["people"] == "unknown" for s in d["shelters"]) or d["status"] == "missing_info"
        special.append({"diet_category": d["diet_category"], "status": d["status"],
                        "needed_meals_known": d["total_unmet_meals_known"], "available_meals": d["available_meals"],
                        "shortage_meals_known": d["shortage_meals_known"],
                        "unknown_counts": unknown,
                        # unknown demand is never shown as 0; confirmed zero is its own state (P41 fix F2)
                        "demand": "unknown" if unknown else ("zero" if not d["total_unmet_meals_known"] else "known"),
                        "shelters": [s["shelter_name"] for s in d["shelters"]]})

    count_times = {}
    for item in inventory.get("items", []):
        if item.get("counted_at"):
            count_times[item["warehouse_id"]] = max(count_times.get(item["warehouse_id"], ""), item["counted_at"])

    return {
        "status": allocation["status"],
        "situation": {"available_meals": available, "unmet_meals": unmet, "additional_meals_needed": additional,
                      "covered_meals": min(available, unmet), "covered_share": min(1.0, _share(available, unmet)),
                      "not_covered_meals": max(0, unmet - available)},
        "actions": _actions(reports, inventory, needs, allocation),
        "plans": {"available_meals": available, "total_unmet_meals": unmet,
                  "plan_a_total_meals": general["plan_a_total_meals"], "shortage_meals": general["shortage_meals"],
                  "plan_b_procurement_meals": additional, "rows": plan_rows, "special_diets": special},
        "missing_shelters": [{"shelter_id": m["shelter_id"], "shelter_name": m["shelter_name"],
                              "pending_report_at": m.get("reported_at")}
                             for m in needs.get("shelters_without_validated_report", [])],
        "details": {"shelters": details, "warehouses": sorted(warehouses.values(), key=lambda w: w["warehouse_id"]),
                    "assumptions": {**allocation["planning"],
                                    "unmet_formula": needs["planning"].get("unmet_formula"),
                                    "plan_fingerprint": allocation.get("plan_fingerprint")},
                    "inventory_counted_at": count_times,
                    "data_warnings": list(allocation.get("data_warnings", []))},
    }


def load_dashboard():
    """Dashboard from the current working data (same reads as the chat agent's tools)."""
    return build_dashboard(agent_tools.get_shelter_reports(), agent_tools.get_warehouse_inventory(),
                           agent_tools.calculate_shelter_needs(), agent_tools.calculate_allocation())
