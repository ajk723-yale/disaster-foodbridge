"""Independent expected results for the impact evaluation (P40).

Written from the documented rules (data/sample/README.md, development_log.md stages 1-4, 10, 13, 16),
NOT from the application code: this module imports nothing from src/ and uses only the standard
library. It is the "oracle" the app's outputs are compared against.

Rules encoded:
- Only status == "validated" records count; per shelter the latest by reported_at; per
  (warehouse, item) the latest by counted_at. Pending and rejected records are ignored.
- special_needs "tag:n; tag:?" -> known counts; "?" = unknown.
- General people = evacuees - known special-diet people (unknown counts are not subtracted).
- Need = ceil(people * meals_per_person_per_day * window_hours / 24), per diet.
- Commitments (cancelled ignored), per shelter and diet:
  approved (not shipped) and dispatched (not delivered) = still on its way;
  delivered = counted only if delivered after the shelter's report time.
- Unmet = ceil(max(0, need - on hand at report - on its way - delivered after report)).
- Stock = sum of quantity * meals_per_unit of the latest validated counts, per diet (exact meal
  equivalents); minus dispatched/delivered commitments that left a warehouse AFTER that warehouse's
  latest validated count for the diet (earlier ones are already reflected in the count; a warehouse
  with no validated count for the diet has no counted stock to reduce); minus approved commitments
  not yet dispatched (reserved). Planning uses the stock rounded down to whole meals.

Corrections after run 1 (see evidence/impact/impact_eval_report.md): the oracle first subtracted
dispatches from warehouses with no validated count, and rounded the inventory meal equivalents
down (the documented rounding applies to planning). Both were errors in this oracle.
- Plan A general: if stock >= total unmet, each shelter gets its unmet; otherwise split stock by
  largest remainder in proportion to unmet (ties: larger unmet, then shelter_id).
- Special diets: complete counts and enough stock -> each gets its unmet; stock short -> staff
  decision (no Plan A lines); any unknown count -> missing information.
- Additional procurement (Plan B) = max(0, total unmet - stock) per diet; unknown if counts unknown.
"""
import csv
import math
from datetime import datetime
from fractions import Fraction

GENERAL = "general"


def _t(value):
    return datetime.fromisoformat(value) if value else None


def _rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _special(text):
    out = {}
    for part in (text or "").replace(",", ";").split(";"):
        if ":" in part:
            tag, n = (s.strip() for s in part.split(":", 1))
            out[tag] = None if n == "?" else Fraction(n)
    return out


def latest_shelters(path):
    latest = {}
    for r in _rows(path):
        if r["status"] != "validated":
            continue
        if r["shelter_id"] not in latest or _t(r["reported_at"]) > _t(latest[r["shelter_id"]]["reported_at"]):
            latest[r["shelter_id"]] = r
    return latest


def latest_counts(path):
    latest = {}
    for r in _rows(path):
        if r["status"] != "validated":
            continue
        k = (r["warehouse_id"], r["item_id"])
        if k not in latest or _t(r["counted_at"]) > _t(latest[k]["counted_at"]):
            latest[k] = r
    return latest


def commitments(path):
    return [r for r in _rows(path) if r["status"] in ("approved", "dispatched", "delivered")]


def shelter_needs(shelter_path, commit_path, meals_per_day, window_hours):
    shelters, commits = latest_shelters(shelter_path), commitments(commit_path)
    rate = Fraction(str(meals_per_day)) * Fraction(str(window_hours)) / 24
    out = {}
    for sid, r in sorted(shelters.items()):
        special = _special(r["special_needs"])
        on_hand_special = {k: v for k, v in _special(r["special_on_hand_meals"]).items()}
        report_time = _t(r["reported_at"])
        diets = {GENERAL: Fraction(r["evacuee_count"]) - sum(v for v in special.values() if v is not None)}
        diets.update(special)
        row = {}
        for diet, people in diets.items():
            on_hand = Fraction(r["general_on_hand_meals"] or 0) if diet == GENERAL else (on_hand_special.get(diet) or 0)
            way = after = Fraction(0)
            for c in commits:
                if c["shelter_id"] != sid or c["diet_tag"] != diet:
                    continue
                if c["status"] in ("approved", "dispatched"):
                    way += Fraction(c["meals"])
                elif c["status"] == "delivered" and _t(c["delivered_at"]) > report_time:
                    after += Fraction(c["meals"])
            if people is None:
                row[diet] = {"people": "unknown", "need": None, "unmet": None}
                continue
            need = math.ceil(people * rate)
            row[diet] = {"people": int(people), "need": need, "on_hand": int(on_hand), "on_its_way": int(way),
                         "delivered_after_report": int(after),
                         "unmet": math.ceil(max(Fraction(0), need - on_hand - way - after))}
        out[sid] = row
    return out


def available_stock(inventory_path, commit_path):
    counts, commits = latest_counts(inventory_path), commitments(commit_path)
    counted, last_count = {}, {}
    for (wh, _), r in counts.items():
        diet = r["diet_tag"]
        counted[diet] = counted.get(diet, Fraction(0)) + Fraction(r["quantity"]) * Fraction(r["meals_per_unit"])
        last_count[(wh, diet)] = max(last_count.get((wh, diet), _t(r["counted_at"])), _t(r["counted_at"]))
    out = {}
    for diet in sorted(set(counted) | {c["diet_tag"] for c in commits}):
        dispatched = reserved = Fraction(0)
        for c in commits:
            if c["diet_tag"] != diet:
                continue
            if c["status"] == "approved":
                reserved += Fraction(c["meals"])
            elif c["dispatched_at"] and c["warehouse_id"]:
                count_time = last_count.get((c["warehouse_id"], diet))
                if count_time is not None and _t(c["dispatched_at"]) > count_time:
                    dispatched += Fraction(c["meals"])
        total = counted.get(diet, Fraction(0))
        out[diet] = {"counted": _exact(total), "dispatched_since_count": _exact(dispatched),
                     "reserved": _exact(reserved), "available": _exact(max(Fraction(0), total - dispatched - reserved))}
    return out


def _exact(value):
    return int(value) if value.denominator == 1 else float(value)


def largest_remainder(demands, stock):
    """demands: {shelter_id: unmet}. Returns {shelter_id: meals}."""
    total = sum(demands.values())
    if total == 0:
        return {k: 0 for k in demands}
    if stock >= total:
        return dict(demands)
    quotas = {k: Fraction(stock) * v / total for k, v in demands.items()}
    alloc = {k: math.floor(q) for k, q in quotas.items()}
    left = stock - sum(alloc.values())
    order = sorted(demands, key=lambda k: (-(quotas[k] - alloc[k]), -demands[k], k))
    for k in order[:left]:
        alloc[k] += 1
    return alloc


def expected_results(shelter_path, inventory_path, commit_path, meals_per_day=3, window_hours=24):
    needs = shelter_needs(shelter_path, commit_path, meals_per_day, window_hours)
    stock = available_stock(inventory_path, commit_path)
    general_unmet = {sid: d[GENERAL]["unmet"] for sid, d in needs.items()}
    general_stock = math.floor(stock.get(GENERAL, {}).get("available", 0))           # planning rounds stock down
    plan_a = largest_remainder(general_unmet, general_stock)
    total_unmet = sum(general_unmet.values())
    special = {}
    for diet in sorted({k for d in needs.values() for k in d if k != GENERAL}):
        rows = {sid: d[diet] for sid, d in needs.items() if diet in d}
        unknown = any(r["unmet"] is None for r in rows.values())
        known = sum(r["unmet"] for r in rows.values() if r["unmet"] is not None)
        avail = math.floor(stock.get(diet, {}).get("available", 0))
        status = "missing_info" if unknown else ("shortage" if known > avail else "ok")
        special[diet] = {"status": status, "known_unmet": known, "available": avail,
                         "known_shortage": max(0, known - avail),
                         "plan_a": ({sid: r["unmet"] for sid, r in rows.items()} if status == "ok" else None),
                         "procurement": "unknown" if unknown else max(0, known - avail)}
    return {
        "needs": needs,
        "stock": stock,
        "general": {"available": general_stock, "total_unmet": total_unmet, "plan_a": plan_a,
                    "plan_a_total": sum(plan_a.values()),
                    "shortfall": {k: general_unmet[k] - plan_a[k] for k in plan_a},
                    "procurement": max(0, total_unmet - general_stock)},
        "special": special,
    }
