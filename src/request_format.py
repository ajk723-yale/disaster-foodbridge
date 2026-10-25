"""Render a saved supply-request snapshot as a draft letter (deterministic, no AI).

Only the stored facts and placeholders are used, so what staff see is exactly what
was saved with the finalized plan.
"""
from src.timeutil import display_time


def _fmt(n):
    return f"{n:g}" if isinstance(n, float) else str(n)


def format_request_markdown(request, tz_name=None):
    ph = request["placeholders"]
    period = request["planning_period"]
    g = request["general_meals"]
    lines = [
        "**DRAFT - REQUIRES STAFF REVIEW - NOT SENT**",
        "",
        f"Plan ID: {request['plan_id']} · Plan fingerprint: `{request['plan_fingerprint'][:16]}…`",
        f"Finalized by {request['finalized_by']} at {display_time(request['finalized_at'], tz_name)} "
        f"({request['finalized_at']} UTC record)",
        "",
        f"Date: {ph['date']}  ",
        f"Reference number: {ph['reference_number']}  ",
        f"To: {ph['recipient']}  ",
        f"From: {ph['sender']}, {ph['municipality']}",
        "",
        "**Purpose.** Request for additional food supplies for evacuation shelters, based on validated "
        "unmet demand in the finalized allocation plan above.",
        "",
        f"**Planning period.** {_fmt(period['window_hours'])} hours from {period['start']}, at "
        f"{_fmt(period['meals_per_person_per_day'])} meals per person per day.",
        "",
        f"**General meals requested: {g['additional_meals_to_request']} meals** "
        f"(validated unmet demand {g['total_unmet_meals']}, available {g['available_meals']}).",
        "",
        "| Shelter | Shortfall after allocation (meals) |",
        "|---|---|",
        *[f"| {s['shelter_name']} ({s['shelter_id']}) | {s['shortfall_meals']} |"
          for s in g["shortfall_by_shelter_after_plan_a"]],
        "",
        "**Special-diet requirements**",
        "",
    ]
    special = request["special_diet_requirements"]
    def amount(s):
        a = s["additional_meals_to_request"]
        return f"{a} additional meals" if isinstance(a, int) else f"amount {a}"
    lines += [f"- {s['diet_category']}: {amount(s)} (known unmet {s['known_unmet_meals']}, available "
              f"{s['available_meals']}, status {s['status']})" for s in special] or ["- None"]
    lines += ["", "**Pending or uncertain data at finalization**", ""]
    lines += [f"- {w}" for w in request["pending_or_uncertain_data"]] or ["- None"]
    lines += [
        "",
        f"**Delivery.** Location: {ph['delivery_location']} · Requested by: {ph['delivery_deadline']}",
        "",
        f"**Contact.** {ph['contact']}",
        "",
        f"_{request['status']} {request['snapshot_note']}_",
    ]
    if request.get("note"):
        lines.insert(2, f"_{request['note']}_")
    return "\n".join(lines)
