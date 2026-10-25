"""Build a plan from the record logs, and finalize it with a recalculation check.

Finalization always recomputes from the latest validated data. If the result
differs from the plan staff last reviewed (compared by fingerprint), nothing is
finalized: the updated plan is returned and staff must confirm it.

Pending data (newer shelter reports or warehouse counts awaiting validation, and
shelters with no validated report) produce warnings with stable IDs. The set of
warning IDs is part of the fingerprint, so any change in pending data requires a
fresh review. While warnings exist, finalization stops until staff acknowledge
every current warning with a reason; acknowledgements are kept in the snapshot.
"""
import hashlib
import json
import uuid
from fractions import Fraction

import pandas as pd

from src.allocation import build_allocation
from src.records import (
    COMMITTED,
    add_commitments,
    available_by_tag,
    incoming_by_shelter,
    latest_validated,
    newer_pending,
)

SHELTER_KEY, SHELTER_TIME = ["shelter_id"], "reported_at"
INVENTORY_KEY, INVENTORY_TIME = ["warehouse_id", "item_id"], "counted_at"


def _jsonable(value):
    if isinstance(value, Fraction):
        return int(value) if value.denominator == 1 else float(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


MIN_REASON_LENGTH = 10


def fingerprint(plan):
    """Stable hash of everything that defines the plan's result and its pending-data warnings."""
    content = {k: plan[k] for k in ("config", "inputs", "general", "special")}
    content["pending_data_warning_ids"] = sorted(w["warning_id"] for w in plan["pending_data_warnings"])
    blob = json.dumps(content, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def _warning(kind, subject, record_ids, message):
    key = json.dumps([kind, subject, sorted(record_ids)])
    return {"warning_id": f"{kind}:{subject}:" + hashlib.sha256(key.encode()).hexdigest()[:10],
            "kind": kind, "subject": subject, "pending_record_ids": sorted(record_ids), "message": message}


def pending_data_warnings(shelter_log, shelters, inventory_log, inventory):
    """Warnings for data the plan can't use yet, each with a stable warning_id."""
    warnings = []
    validated_shelters = set() if shelters is None or shelters.empty else set(shelters["shelter_id"])
    newer = newer_pending(shelter_log, shelters, SHELTER_KEY, SHELTER_TIME)
    pending_by_shelter = {}
    for row in ([] if newer is None or newer.empty else newer.to_dict("records")):
        pending_by_shelter.setdefault(row["shelter_id"], []).append(row)
    known = set() if shelter_log is None or shelter_log.empty else set(shelter_log["shelter_id"])
    for sid in sorted(known | set(pending_by_shelter)):
        rows = pending_by_shelter.get(sid, [])
        ids = [r["record_id"] for r in rows]
        times = ", ".join(sorted(pd.Timestamp(r["reported_at"]).isoformat() for r in rows))
        if sid not in validated_shelters:
            detail = f"; report(s) pending validation: {times}" if rows else "; it has only rejected reports"
            warnings.append(_warning("shelter_without_validated_report", sid, ids,
                                     f"shelter {sid} has no validated report, so it is not in this plan{detail}"))
        elif rows:
            warnings.append(_warning("pending_shelter_report", sid, ids,
                                     f"newer shelter report for {sid} is still pending validation ({times}); "
                                     "the plan uses its last validated report"))
    newer = newer_pending(inventory_log, inventory, INVENTORY_KEY, INVENTORY_TIME)
    validated_items = set() if inventory is None or inventory.empty else \
        set(zip(inventory["warehouse_id"], inventory["item_id"]))
    pending_by_item = {}
    for row in ([] if newer is None or newer.empty else newer.to_dict("records")):
        pending_by_item.setdefault((row["warehouse_id"], row["item_id"]), []).append(row)
    for (wh, item), rows in sorted(pending_by_item.items()):
        times = ", ".join(sorted(pd.Timestamp(r["counted_at"]).isoformat() for r in rows))
        note = "the plan uses its last validated count" if (wh, item) in validated_items else \
            "there is no validated count yet, so it is not in this plan"
        warnings.append(_warning("pending_inventory_count", f"{wh}/{item}", [r["record_id"] for r in rows],
                                 f"newer inventory count for {wh}/{item} is still pending validation ({times}); {note}"))
    return warnings


def build_plan(shelter_log, inventory_log, commitments, config):
    shelters = latest_validated(shelter_log, SHELTER_KEY, SHELTER_TIME)
    inventory = latest_validated(inventory_log, INVENTORY_KEY, INVENTORY_TIME)
    available, stock_flags = available_by_tag(inventory, commitments)
    incoming = incoming_by_shelter(shelters, commitments)

    records = [] if shelters is None or shelters.empty else shelters.to_dict("records")
    result = build_allocation(records, available, incoming, config)

    pending = pending_data_warnings(shelter_log, shelters, inventory_log, inventory)

    plan = _jsonable({
        "config": dict(config),
        "inputs": {
            "shelter_record_ids": sorted([] if shelters is None or shelters.empty else shelters["record_id"]),
            "inventory_record_ids": sorted([] if inventory is None or inventory.empty else inventory["record_id"]),
            "committed_ids": sorted([] if commitments is None or commitments.empty
                                    else commitments.loc[commitments["status"].isin(COMMITTED), "commitment_id"]),
        },
        "general": result["general"],
        "special": result["special"],
        "flags": stock_flags + result["flags"],
        "pending_data_warnings": pending,
        "warnings": [w["message"] for w in pending],
    })
    plan["fingerprint"] = fingerprint(plan)
    return plan


def check_acknowledgements(plan, acknowledgements):
    """Return (accepted, problems). Every current pending-data warning needs an
    acknowledgement with a reason of at least MIN_REASON_LENGTH characters, and no
    acknowledgement may refer to a warning that isn't current."""
    current = {w["warning_id"]: w for w in plan["pending_data_warnings"]}
    given = {}
    problems = []
    for ack in acknowledgements or []:
        wid, reason = ack.get("warning_id"), (ack.get("reason") or "").strip()
        if wid not in current:
            problems.append({"warning_id": wid, "problem": "not a current warning (data may have changed)"})
        elif wid in given:
            problems.append({"warning_id": wid, "problem": "acknowledged more than once"})
        elif len(reason) < MIN_REASON_LENGTH:
            problems.append({"warning_id": wid, "problem": f"reason must be at least {MIN_REASON_LENGTH} characters"})
        else:
            given[wid] = reason
    problems += [{"warning_id": wid, "problem": "not acknowledged"} for wid in current if wid not in given
                 and not any(p["warning_id"] == wid for p in problems)]
    accepted = [{**{k: current[wid][k] for k in ("warning_id", "kind", "subject", "pending_record_ids", "message")},
                 "reason": reason} for wid, reason in given.items()]
    return (accepted if not problems else []), problems


def finalize_plan(shelter_log, inventory_log, commitments, config, reviewed_fingerprint, staff_name, at,
                  plan_id=None, acknowledgements=None):
    """Recompute and finalize only if the result matches what staff reviewed and every
    pending-data warning has been acknowledged with a reason.

    Returns one of:
    - {"status": "needs_confirmation", "plan"}: data or warnings changed since review;
    - {"status": "acknowledgement_required", "plan", "warnings", "problems"}: pending
      data exists and is not (correctly) acknowledged;
    - {"status": "finalized", "snapshot", "commitments"}; the snapshot includes the
      acknowledgements with reasons, staff, and time.
    """
    plan = build_plan(shelter_log, inventory_log, commitments, config)
    if plan["fingerprint"] != reviewed_fingerprint:
        return {"status": "needs_confirmation", "plan": plan}

    accepted, problems = check_acknowledgements(plan, acknowledgements)
    if problems:
        return {"status": "acknowledgement_required", "plan": plan,
                "warnings": plan["pending_data_warnings"], "problems": problems}
    at_iso = pd.Timestamp(at).isoformat()
    acknowledged = [{**a, "acknowledged_by": staff_name, "acknowledged_at": at_iso} for a in accepted]

    plan_id = plan_id or uuid.uuid4().hex[:12]
    lines = [(l["shelter_id"], "general", l["allocated_meals"]) for l in plan["general"]["lines"]]
    for group in plan["special"]:
        lines += [(l["shelter_id"], group["diet_tag"], l["suggested_meals"])
                  for l in group["lines"] if l["suggested_meals"]]
    updated = add_commitments(commitments, plan_id, lines, at)
    snapshot = {**plan, "plan_id": plan_id, "finalized_by": staff_name, "finalized_at": at_iso,
                "acknowledgements": acknowledged}
    return {"status": "finalized", "snapshot": snapshot, "commitments": updated}
