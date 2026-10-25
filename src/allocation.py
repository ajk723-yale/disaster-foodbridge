"""Deterministic need, allocation, and shortage calculations.

Food is grouped by diet tag. Only GENERAL_TAG meals are pooled and split in
proportion to unmet demand. Each special diet tag is assessed on its own: when
stock covers every shelter's need it is suggested in full; otherwise (or when
information is missing) the tag is flagged for staff review instead of being
split automatically.

All amounts are meals. Exact fractions are used internally; results are whole
meals:
- need is rounded up (never under-plan a shelter),
- available stock is rounded down (never promise food that isn't there),
- the proportional split uses the largest-remainder method with a fixed
  tie-break (larger remainder, then larger unmet demand, then shelter_id).
"""
import math
from fractions import Fraction

from src.schemas import GENERAL_TAG


def _frac(value):
    return value if isinstance(value, Fraction) else Fraction(str(value))


def meals_needed(people, meals_per_person_per_day, planning_window_hours):
    """Whole meals needed for `people` over the planning window (rounded up)."""
    exact = people * _frac(meals_per_person_per_day) * _frac(planning_window_hours) / 24
    return math.ceil(exact)


def unmet_meals(need, on_hand, incoming):
    return math.ceil(max(Fraction(0), _frac(need) - _frac(on_hand) - _frac(incoming)))


def allocate_proportionally(demands, available):
    """Split `available` whole meals across {key: unmet_demand} proportionally.

    Never gives a key more than its demand. Fully covers everyone when supply is
    enough. Deterministic for identical inputs regardless of dict order.
    """
    available = math.floor(_frac(available))
    total = sum(demands.values())
    if total <= available:
        return dict(demands)
    if available <= 0:
        return {k: 0 for k in demands}
    quotas = {k: Fraction(available * d, total) for k, d in demands.items()}
    result = {k: math.floor(q) for k, q in quotas.items()}
    leftover = available - sum(result.values())
    order = sorted(demands, key=lambda k: (-(quotas[k] - result[k]), -demands[k], str(k)))
    for k in order[:leftover]:
        result[k] += 1
    return result


def compute_needs(shelters, incoming, config):
    """Need and unmet demand per shelter for one planning window (no allocation).

    shelters: list of dicts with shelter_id, shelter_name, evacuee_count,
        general_on_hand_meals, special_needs {tag: people|None},
        special_on_hand_meals {tag: meals}.
    incoming: {(shelter_id, diet_tag): meals already approved/dispatched but not
        yet reflected in that shelter's latest report}.
    config: meals_per_person_per_day, planning_window_hours.
    Returns {"general": [line], "special": [{"diet_tag", "missing_info", "lines"}], "flags"}.
    Unknown special-needs counts give need/unmet of None and a review flag.
    """
    mppd = config["meals_per_person_per_day"]
    hours = config["planning_window_hours"]
    shelters = sorted(shelters, key=lambda s: str(s["shelter_id"]))
    flags = []

    # General meals: everyone not on a known special diet
    general_lines = []
    for s in shelters:
        special = s.get("special_needs") or {}
        people = s["evacuee_count"] - sum(v for v in special.values() if v is not None)
        need = meals_needed(people, mppd, hours)
        inc = incoming.get((s["shelter_id"], GENERAL_TAG), 0)
        general_lines.append({
            "shelter_id": s["shelter_id"],
            "shelter_name": s["shelter_name"],
            "people": people,
            "need_meals": need,
            "on_hand_meals": _frac(s["general_on_hand_meals"]),
            "incoming_meals": _frac(inc),
            "unmet_meals": unmet_meals(need, s["general_on_hand_meals"], inc),
        })
        if any(v is None for v in special.values()):
            flags.append({"severity": "warning", "shelter_id": s["shelter_id"], "diet_tag": GENERAL_TAG,
                          "message": "some special-needs counts are unknown, so general need may be overstated"})

    # Special diets: one independent group per tag
    special = []
    for tag in sorted({t for s in shelters for t in (s.get("special_needs") or {})}):
        lines, missing = [], False
        for s in shelters:
            needs = s.get("special_needs") or {}
            if tag not in needs:
                continue
            people = needs[tag]
            on_hand = _frac((s.get("special_on_hand_meals") or {}).get(tag, 0))
            inc = _frac(incoming.get((s["shelter_id"], tag), 0))
            line = {"shelter_id": s["shelter_id"], "shelter_name": s["shelter_name"], "people": people,
                    "on_hand_meals": on_hand, "incoming_meals": inc}
            if people is None:
                missing = True
                line.update(need_meals=None, unmet_meals=None)
                flags.append({"severity": "review", "shelter_id": s["shelter_id"], "diet_tag": tag,
                              "message": f"number of people needing '{tag}' is unknown"})
            else:
                need = meals_needed(people, mppd, hours)
                line.update(need_meals=need, unmet_meals=unmet_meals(need, on_hand, inc))
            lines.append(line)
        special.append({"diet_tag": tag, "missing_info": missing, "lines": lines})

    return {"general": general_lines, "special": special, "flags": flags}


def build_allocation(shelters, available_by_tag, incoming, config):
    """Compute the allocation for one planning window.

    Inputs as for compute_needs, plus available_by_tag: {diet_tag: meals
    available in the warehouse}.
    """
    needs = compute_needs(shelters, incoming, config)
    general_lines, flags = needs["general"], needs["flags"]

    general_available = math.floor(_frac(available_by_tag.get(GENERAL_TAG, 0)))
    alloc = allocate_proportionally({l["shelter_id"]: l["unmet_meals"] for l in general_lines}, general_available)
    for l in general_lines:
        l["allocated_meals"] = alloc[l["shelter_id"]]
        l["shortfall_meals"] = l["unmet_meals"] - l["allocated_meals"]
    total_unmet = sum(l["unmet_meals"] for l in general_lines)
    general = {
        "available_meals": general_available,
        "total_unmet_meals": total_unmet,
        "allocated_meals": sum(alloc.values()),
        "shortage_meals": max(0, total_unmet - general_available),
        "lines": general_lines,
    }

    special = []
    for group in needs["special"]:
        tag, lines = group["diet_tag"], group["lines"]
        available = math.floor(_frac(available_by_tag.get(tag, 0)))
        total_unmet = sum(l["unmet_meals"] for l in lines if l["unmet_meals"] is not None)
        shortage = max(0, total_unmet - available)
        if group["missing_info"]:
            status = "missing_info"
        elif shortage > 0:
            status = "no_stock" if available == 0 else "shortage"
            flags.append({"severity": "review", "shelter_id": None, "diet_tag": tag,
                          "message": f"'{tag}' is short by {shortage} meals; staff must decide distribution"})
        else:
            status = "ok"
        for l in lines:
            # Auto-suggest only when every need is known and fully covered
            l["suggested_meals"] = l["unmet_meals"] if status == "ok" else None
        special.append({
            "diet_tag": tag,
            "status": status,
            "available_meals": available,
            "total_unmet_meals": total_unmet,
            "shortage_meals": shortage,
            "lines": lines,
        })

    return {"general": general, "special": special, "flags": flags}
