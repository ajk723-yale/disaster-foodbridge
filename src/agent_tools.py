"""Tools the FoodBridge agent can call. Each returns plain JSON-safe data."""
import pandas as pd

from src import config
from src.drafts import (  # noqa: F401  (re-exported for callers of the tools module)
    _iso,
    _num,
    allocation_from_logs,
    shelter_needs_from_logs,
    supply_request_from_allocation,
)
from src.finalization import load_finalized_commitments
from src.records import inventory_position, latest_validated, newer_pending
from src.schemas import GENERAL_TAG
from src.store import load_commitments, load_inventory_log, load_shelter_log


def _load_all_commitments():
    """Dispatch log (CSV) plus approvals from finalized plans (SQLite). Returns (df, csv_issues)."""
    csv_commitments, issues = load_commitments(config.COMMITMENTS_LOG_PATH)
    finalized = load_finalized_commitments(config.FINALIZATION_DB_PATH)
    frames = [f for f in (csv_commitments, finalized) if not f.empty]
    return (pd.concat(frames, ignore_index=True) if frames else csv_commitments), issues


def shelter_reports_from_log(log):
    """Summarize the latest validated report per shelter and newer pending ones."""
    latest = latest_validated(log, ["shelter_id"], "reported_at")
    pending = newer_pending(log, latest, ["shelter_id"], "reported_at")

    shelters = []
    for r in ([] if latest is None or latest.empty else latest.to_dict("records")):
        shelters.append({
            "shelter_id": r["shelter_id"],
            "shelter_name": r["shelter_name"],
            "evacuee_count": r["evacuee_count"],
            "general_food_on_hand_meals": _num(r["general_on_hand_meals"]),
            "special_food_on_hand_meals": {k: _num(v) for k, v in r["special_on_hand_meals"].items()},
            "special_needs_people": {k: ("unknown" if v is None else v) for k, v in r["special_needs"].items()},
            "reported_at": _iso(r["reported_at"]),
            "validated_by": r["validated_by"],
        })
    pending_out = [{
        "shelter_id": r["shelter_id"],
        "shelter_name": r["shelter_name"],
        "reported_at": _iso(r["reported_at"]),
        "source": r["source"],
        "has_validated_report": any(s["shelter_id"] == r["shelter_id"] for s in shelters),
    } for r in ([] if pending is None or pending.empty else pending.to_dict("records"))]

    result = {"validated_shelters": shelters, "newer_reports_pending_validation": pending_out}
    if not shelters:
        result["note"] = "No validated shelter reports are available."
    return result


def get_shelter_reports() -> dict:
    """Get the latest staff-validated report for each evacuation shelter.

    Returns each shelter's ID, name, evacuee count, food on hand (general meals and
    special-diet meals), special-needs counts, and report timestamp. Also lists newer
    reports that are still pending staff validation; their figures are not included
    because they are not yet confirmed.
    """
    log, _ = load_shelter_log(config.SHELTER_LOG_PATH)
    return shelter_reports_from_log(log)


def warehouse_inventory_from_log(log, commitments, commitment_issues=()):
    """Summarize the latest validated count per (warehouse, item), counted vs available
    meals per diet tag after approved/dispatched allocations, and newer pending counts."""
    key, time = ["warehouse_id", "item_id"], "counted_at"
    latest = latest_validated(log, key, time)
    pending = newer_pending(log, latest, key, time)
    rows = [] if latest is None or latest.empty else latest.to_dict("records")

    items = []
    for r in rows:
        meals = r["quantity"] * r["meals_per_unit"]
        items.append({
            "warehouse_id": r["warehouse_id"],
            "item_id": r["item_id"],
            "item_name": r["item_name"],
            "diet_category": r["diet_tag"],
            "food_type": r["category"],
            "quantity": _num(r["quantity"]),
            "unit": r["unit"],
            "meals_per_unit": _num(r["meals_per_unit"]),
            "meal_equivalents": _num(meals),
            "counts_as_meals": meals > 0,
            "counted_at": _iso(r["counted_at"]),
            "expiry_date": r["expiry_date"].isoformat() if r["expiry_date"] else None,
        })

    positions, deductions, flags = inventory_position(latest, commitments)
    totals = {tag: {"type": "general meals" if tag == GENERAL_TAG else "special diet",
                    "counted_meal_equivalents": _num(pos["counted"]),
                    "dispatched_since_count": _num(pos["dispatched_since_count"]),
                    "reserved_approved_not_dispatched": _num(pos["reserved_not_dispatched"]),
                    "available_meal_equivalents": _num(pos["available"]),
                    "items": sorted({i["item_name"] for i in items
                                     if i["diet_category"] == tag and i["counts_as_meals"]})}
              for tag, pos in positions.items()}
    commitments_out = [{
        "commitment_id": d["commitment_id"],
        "diet_category": d["diet_tag"],
        "meals": d["meals"],
        "status": d["status"],
        "source_warehouse": d["warehouse_id"] or None,
        "dispatched_at": _iso(d["dispatched_at"]),
        "treatment": d["treatment"],
    } for d in deductions]

    pending_out = [{
        "warehouse_id": r["warehouse_id"],
        "item_id": r["item_id"],
        "item_name": r["item_name"],
        "counted_at": _iso(r["counted_at"]),
    } for r in ([] if pending is None or pending.empty else pending.to_dict("records"))]

    result = {
        "meal_totals_by_diet_category": totals,
        "items": items,
        "approved_and_dispatched_allocations": commitments_out,
        "newer_counts_pending_validation": pending_out,
        "flags": [f["message"] for f in flags] + [f"dispatch log row {i['row']}: {i['message']}"
                                                  for i in commitment_issues],
    }
    if not items:
        result["note"] = "No validated warehouse inventory counts are available."
    return result


def get_warehouse_inventory() -> dict:
    """Get warehouse food inventory: counted stock and actually available stock.

    Per diet category: counted meal equivalents (latest staff-validated counts), meals
    dispatched since those counts, meals approved but not yet dispatched (reserved), and
    available meal equivalents (counted minus both). 'general' meals are separate from
    special-diet categories such as infant_formula or allergy_free; they are not
    interchangeable. Also returns each item's warehouse, name, quantity, unit, meal
    equivalents, diet category, count timestamp and expiry date; how each approved or
    dispatched allocation was treated (a dispatch already reflected in a newer recount is
    not subtracted again); and newer counts still pending validation (not included).
    Items with 0 meals per unit (e.g. water) are listed but not counted as meals.
    """
    log, _ = load_inventory_log(config.INVENTORY_LOG_PATH)
    commitments, issues = _load_all_commitments()
    return warehouse_inventory_from_log(log, commitments, issues)


def planning_config():
    return {"meals_per_person_per_day": config.MEALS_PER_PERSON_PER_DAY,
            "planning_window_hours": config.PLANNING_WINDOW_HOURS}


def calculate_shelter_needs() -> dict:
    """Calculate each shelter's food need and unmet demand for the planning window.

    Uses the latest staff-validated shelter reports and the configured meal rate and
    planning window. Per shelter: meals needed; meals on hand at its latest report; food
    still on its way, split into approved_not_shipped (committed, not yet shipped) and
    shipped_not_confirmed (dispatched, delivery not confirmed; deliveries can be
    delayed); delivered_after_report (confirmed delivered after the latest report, so
    already at the shelter but not in the reported on-hand figure; NOT on its way); and
    unmet demand = need - on hand at report - still on its way - delivered after report,
    never below 0. Delivery is never assumed; confirmed deliveries at or before the
    report are already in its on-hand figure. General meals and each special-diet
    category are reported separately. Unknown special-needs counts give 'unknown' instead
    of a number and are flagged; shelters with a newer pending report or with no
    validated report are flagged too. Does not allocate warehouse stock.
    """
    log, _ = load_shelter_log(config.SHELTER_LOG_PATH)
    commitments, _ = _load_all_commitments()
    return shelter_needs_from_logs(log, commitments, planning_config())


def calculate_allocation() -> dict:
    """Draft a food distribution plan from the latest validated shelter reports and
    available warehouse stock (after approved/dispatched food). Returns a DRAFT, not a
    finalized allocation.

    General meals (separate from special diets):
    - Plan A: proportional split of currently available general meals by unmet demand,
      feasible with stock on hand, with each shelter's remaining shortfall.
    - Plan B: the allocation that meets all validated unmet demand, plus the additional
      meals that must be procured (the shortage).
    Special diets are planned per category and never mixed with general meals: when
    stock covers every known need, Plan A suggests it in full; when stock is short or a
    count is unknown, Plan A gives no split and staff must decide. Plan B is each known
    unmet need. Also returns unresolved data warnings.
    """
    shelter_log, _ = load_shelter_log(config.SHELTER_LOG_PATH)
    inventory_log, _ = load_inventory_log(config.INVENTORY_LOG_PATH)
    commitments, issues = _load_all_commitments()
    return allocation_from_logs(shelter_log, inventory_log, commitments, planning_config(), issues)


def prepare_supply_request() -> dict:
    """Gather the facts for a DRAFT food supply request to the prefectural or national
    government, from the current calculate_allocation draft. Read-only: sends nothing and
    finalizes nothing.

    Returns the planning period, general meals to request (Plan B shortage) with each
    shelter's shortfall after Plan A, special-diet requirements per category (additional
    meals to request, or 'to be confirmed' where counts are unknown), pending or uncertain
    data, and placeholders to use for municipality, recipient, sender, contact, and
    delivery details, which are not known to the system.
    """
    return supply_request_from_allocation(calculate_allocation())
