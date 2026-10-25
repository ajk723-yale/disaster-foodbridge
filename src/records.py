"""Append-only record log, latest-validated selection, and allocation commitments.

Record log: every upload, AI extraction, or correction is a new row; validated
rows are never edited. A correction is a new record whose `supersedes` points
at the record it replaces.

Commitments: one row per (plan, shelter, diet_tag). States:
- approved: committed, not yet shipped (still in the warehouse, reserved);
- dispatched: shipped from a recorded warehouse, delivery not confirmed;
- delivered: delivery confirmed by staff, with delivered_at;
- cancelled: only from approved; ignored everywhere.
Warehouse side (inventory_position): approved food is always deducted (every
count includes it); dispatched/delivered food is deducted only if it left its
warehouse after that warehouse's latest count, since a later recount already
reflects it.
Shelter side (incoming_breakdown): delivery is never assumed. Approved and
dispatched food count as on its way until a delivery is confirmed; confirmed
deliveries count only if they arrived after the shelter's latest report.
"""
import uuid
from fractions import Fraction

import pandas as pd

from src.schemas import RECORD_META_COLUMNS

STATUSES = ("pending", "validated", "rejected")
COMMITMENT_COLUMNS = ["commitment_id", "plan_id", "shelter_id", "diet_tag", "meals",
                      "status", "committed_at", "dispatched_at", "warehouse_id", "delivered_at"]
COMMITTED = ("approved", "dispatched", "delivered")


def _new_id():
    return uuid.uuid4().hex[:12]


def make_records(clean_df, source, received_at, supersedes="", source_text="", id_factory=_new_id):
    """Wrap validated-for-format rows as pending records."""
    df = clean_df.copy()
    df["record_id"] = [id_factory() for _ in range(len(df))]
    df["source"] = source
    df["received_at"] = pd.Timestamp(received_at)
    df["status"] = "pending"
    df["validated_by"] = ""
    df["validated_at"] = None
    df["supersedes"] = supersedes
    df["source_text"] = source_text
    return df


def empty_log(data_columns):
    return pd.DataFrame(columns=list(data_columns) + ["row_ok"] + RECORD_META_COLUMNS)


def append_records(log, new_records):
    if log is None or log.empty:
        return new_records.reset_index(drop=True)
    return pd.concat([log, new_records], ignore_index=True)


def set_status(log, record_id, status, staff_name, at):
    """Validate or reject a pending record. Validated/rejected records are final."""
    if status not in ("validated", "rejected"):
        raise ValueError(f"status must be 'validated' or 'rejected', not {status!r}")
    match = log.index[log["record_id"] == record_id]
    if len(match) != 1:
        raise KeyError(f"record {record_id!r} not found")
    ix = match[0]
    if log.at[ix, "status"] != "pending":
        raise ValueError(f"record {record_id!r} is already {log.at[ix, 'status']}")
    if status == "validated" and not log.at[ix, "row_ok"]:
        raise ValueError(f"record {record_id!r} has validation errors and cannot be validated")
    log = log.copy()
    log.at[ix, "status"] = status
    log.at[ix, "validated_by"] = staff_name
    log.at[ix, "validated_at"] = pd.Timestamp(at)
    return log


def latest_validated(log, key_columns, time_column):
    """Latest validated, non-superseded record per key.

    Ties on time_column are broken by received_at, then record_id.
    """
    if log is None or log.empty:
        return log
    validated = log[log["status"] == "validated"]
    superseded = set(validated["supersedes"].dropna()) - {""}
    current = validated[~validated["record_id"].isin(superseded)]
    current = current.sort_values(key_columns + [time_column, "received_at", "record_id"])
    return current.groupby(key_columns, as_index=False, sort=True).tail(1).reset_index(drop=True)


def newer_pending(log, latest, key_columns, time_column):
    """Pending records that are newer than the latest validated one for their key
    (or that exist for a key with no validated record yet)."""
    if log is None or log.empty:
        return log
    pending = log[(log["status"] == "pending") & log[time_column].notna()]
    if latest is None or latest.empty:
        return pending
    ref = latest.set_index(key_columns)[time_column]
    keep = []
    for _, row in pending.iterrows():
        key = tuple(row[k] for k in key_columns) if len(key_columns) > 1 else row[key_columns[0]]
        keep.append(key not in ref.index or row[time_column] > ref[key])
    return pending[keep]


# ---- commitments ---------------------------------------------------------

def empty_commitments():
    return pd.DataFrame(columns=COMMITMENT_COLUMNS)


def add_commitments(commitments, plan_id, lines, committed_at, id_factory=_new_id):
    """lines: iterable of (shelter_id, diet_tag, meals); zero-meal lines are skipped."""
    rows = [{"commitment_id": id_factory(), "plan_id": plan_id, "shelter_id": sid, "diet_tag": tag,
             "meals": int(meals), "status": "approved", "committed_at": pd.Timestamp(committed_at),
             "dispatched_at": None, "warehouse_id": "", "delivered_at": None}
            for sid, tag, meals in lines if meals > 0]
    if not rows:
        return commitments
    new = pd.DataFrame(rows, columns=COMMITMENT_COLUMNS)
    return new if commitments.empty else pd.concat([commitments, new], ignore_index=True)


def _update_commitments(commitments, ids, allowed_from, status, at_column=None, at=None, extra=None):
    commitments = commitments.copy()
    for cid in ids:
        match = commitments.index[commitments["commitment_id"] == cid]
        if len(match) != 1:
            raise KeyError(f"commitment {cid!r} not found")
        ix = match[0]
        if commitments.at[ix, "status"] not in allowed_from:
            raise ValueError(f"commitment {cid!r} is {commitments.at[ix, 'status']}, cannot become {status}")
        commitments.at[ix, "status"] = status
        if at_column:
            commitments.at[ix, at_column] = pd.Timestamp(at)
        for col, value in (extra or {}).items():
            commitments.at[ix, col] = value
    return commitments


def mark_dispatched(commitments, commitment_ids, at, warehouse_id=""):
    """Record that food left `warehouse_id` at `at`. The warehouse lets later recounts
    of that warehouse replace the deduction instead of subtracting it twice."""
    return _update_commitments(commitments, commitment_ids, ("approved",), "dispatched", "dispatched_at", at,
                               extra={"warehouse_id": warehouse_id})


def mark_delivered(commitments, commitment_ids, at):
    """Record staff-confirmed delivery at the shelter. Only dispatched food can be delivered."""
    return _update_commitments(commitments, commitment_ids, ("dispatched",), "delivered", "delivered_at", at)


def cancel_commitments(commitments, commitment_ids):
    """Cancel approved (not yet dispatched) commitments, returning the food to availability."""
    return _update_commitments(commitments, commitment_ids, ("approved",), "cancelled")


def inventory_position(inventory, commitments):
    """Counted vs available meals per diet tag, with how each commitment was treated.

    inventory: latest validated inventory rows (parsed).
    Returns (positions, deductions, flags):
    - positions: {tag: {"counted", "dispatched_since_count", "reserved_not_dispatched",
      "available"}} as Fractions;
    - deductions: one dict per approved/dispatched commitment with its treatment;
    - flags: warnings for staff.
    A dispatch at the same moment as a count is treated as already reflected.
    """
    positions, deductions, flags = {}, [], []
    if inventory is None or inventory.empty:
        inventory = pd.DataFrame(columns=["warehouse_id", "diet_tag", "quantity", "meals_per_unit", "counted_at"])
    for tag, items in inventory.groupby("diet_tag", sort=True):
        counted = sum((Fraction(q) * Fraction(m) for q, m in zip(items["quantity"], items["meals_per_unit"])),
                      Fraction(0))
        positions[tag] = {"counted": counted, "dispatched_since_count": Fraction(0),
                          "reserved_not_dispatched": Fraction(0)}

    committed = (commitments[commitments["status"].isin(COMMITTED)]
                 if commitments is not None and not commitments.empty else commitments)
    for c in ([] if committed is None or committed.empty else committed.to_dict("records")):
        tag, meals = c["diet_tag"], Fraction(int(c["meals"]))
        entry = {"commitment_id": c["commitment_id"], "diet_tag": tag, "meals": int(c["meals"]),
                 "status": c["status"], "warehouse_id": c.get("warehouse_id") or "",
                 "dispatched_at": c["dispatched_at"]}
        deductions.append(entry)
        if tag not in positions:
            entry["treatment"] = "not deducted: no validated count for this diet tag"
            flags.append({"severity": "warning", "shelter_id": None, "diet_tag": tag,
                          "message": f"commitment {c['commitment_id']} is for '{tag}' but no '{tag}' stock is counted"})
            continue
        if c["status"] == "approved":
            positions[tag]["reserved_not_dispatched"] += meals
            entry["treatment"] = "deducted: approved and still in the warehouse (reserved)"
            continue

        left_at = c["dispatched_at"] if pd.notna(c["dispatched_at"]) else c["committed_at"]
        tag_items = inventory[inventory["diet_tag"] == tag]
        warehouse = entry["warehouse_id"]
        if not warehouse:
            # Source unknown: conservative, deduct unless every count of the tag is newer
            if left_at > tag_items["counted_at"].min():
                positions[tag]["dispatched_since_count"] += meals
                entry["treatment"] = "deducted: no source warehouse recorded (conservative)"
            else:
                entry["treatment"] = "not deducted: every count of this tag is newer than the dispatch"
            flags.append({"severity": "warning", "shelter_id": None, "diet_tag": tag,
                          "message": f"dispatch {c['commitment_id']} has no source warehouse recorded"})
            continue
        counts = tag_items.loc[tag_items["warehouse_id"] == warehouse, "counted_at"]
        if counts.empty:
            entry["treatment"] = "not deducted: no validated count for this warehouse and tag"
            flags.append({"severity": "warning", "shelter_id": None, "diet_tag": tag,
                          "message": f"dispatch {c['commitment_id']} left {warehouse}, which has no '{tag}' count"})
        elif left_at > counts.max():
            positions[tag]["dispatched_since_count"] += meals
            entry["treatment"] = f"deducted: left {warehouse} after its latest count"
        elif left_at <= counts.min():
            entry["treatment"] = f"not deducted: {warehouse} was recounted after this dispatch"
        else:
            positions[tag]["dispatched_since_count"] += meals
            entry["treatment"] = f"deducted (conservative): only some {warehouse} items were recounted after it"
            flags.append({"severity": "warning", "shelter_id": None, "diet_tag": tag,
                          "message": f"'{tag}' items in {warehouse} were counted at different times around "
                                     f"dispatch {c['commitment_id']}; a recount is recommended"})

    for tag, pos in positions.items():
        remaining = pos["counted"] - pos["dispatched_since_count"] - pos["reserved_not_dispatched"]
        if remaining < 0:
            flags.append({"severity": "warning", "shelter_id": None, "diet_tag": tag,
                          "message": f"committed '{tag}' meals exceed counted stock; check inventory"})
        pos["available"] = max(Fraction(0), remaining)
    return positions, deductions, flags


def available_by_tag(inventory, commitments):
    """Meals available per diet tag after committed food. Returns ({tag: Fraction}, flags)."""
    positions, _, flags = inventory_position(inventory, commitments)
    return {tag: pos["available"] for tag, pos in positions.items()}, flags


INCOMING_STATES = ("committed_not_shipped", "shipped_not_confirmed", "delivered_after_report")


def incoming_breakdown(shelters, commitments):
    """Food on its way to each shelter, by state, never assuming delivery.

    Returns (incoming, flags) where incoming is
    {(shelter_id, diet_tag): {state: meals}} with states:
    - committed_not_shipped: approved, not yet dispatched;
    - shipped_not_confirmed: dispatched, delivery not confirmed (even if it left
      before the shelter's latest report: deliveries can be delayed);
    - delivered_after_report: delivery confirmed after the shelter's latest report,
      so that report's on-hand figure can't include it.
    Confirmed deliveries at or before the latest report are already in its on-hand
    figure and are not counted again. Unconfirmed food that left before the latest
    report is flagged: if it did arrive, the report may already count it.
    """
    incoming, flags = {}, []
    if commitments is None or commitments.empty or shelters is None or shelters.empty:
        return incoming, flags
    reported = dict(zip(shelters["shelter_id"], shelters["reported_at"]))
    for row in commitments[commitments["status"].isin(COMMITTED)].itertuples():
        if row.shelter_id not in reported:
            continue
        report_time = reported[row.shelter_id]
        if row.status == "approved":
            state = "committed_not_shipped"
        elif row.status == "dispatched":
            state = "shipped_not_confirmed"
            if pd.notna(row.dispatched_at) and row.dispatched_at <= report_time:
                flags.append({"severity": "review", "shelter_id": row.shelter_id, "diet_tag": row.diet_tag,
                              "message": f"{int(row.meals)} meals ({row.commitment_id}) left before the shelter's "
                                         "latest report but delivery is not confirmed; counted as on its way. "
                                         "If it has arrived, confirm delivery so it isn't counted twice"})
        elif pd.notna(row.delivered_at) and row.delivered_at > report_time:
            state = "delivered_after_report"
        else:
            continue  # delivered at or before the latest report: already in its on-hand figure
        states = incoming.setdefault((row.shelter_id, row.diet_tag), dict.fromkeys(INCOMING_STATES, 0))
        states[state] += int(row.meals)
    return incoming, flags


def incoming_by_shelter(shelters, commitments):
    """Total meals on its way per (shelter_id, diet_tag); see incoming_breakdown."""
    incoming, _ = incoming_breakdown(shelters, commitments)
    return {key: sum(states.values()) for key, states in incoming.items()}
