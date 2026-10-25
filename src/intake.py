"""Staff approval of AI-extracted shelter reports.

The AI extraction only suggests values. A record is added to the shelter report
log only when staff approve it: the staff-corrected fields are validated with the
same rules as uploaded CSVs, then appended (never overwriting earlier records) with
status "validated", the original report text, who approved it, and when (UTC).
"""
import io
import uuid
from zoneinfo import ZoneInfo

import pandas as pd

from src import config
from src.data_io import load_shelter_reports
from src.schemas import RECORD_META_COLUMNS, SHELTER_COLUMNS
from src.store import append_record
from src.timeutil import to_utc, utc_iso, utc_now
from src.validation import validate_shelter_reports
from src.workspace import ProtectedPathError

EDITABLE_FIELDS = ("shelter_id", "shelter_name", "reported_at", "evacuee_count", "general_on_hand_meals",
                   "special_needs", "special_on_hand_meals")


def local_time_input(value):
    """Turn a stored UTC/offset time into 'YYYY-MM-DD HH:MM' in the display timezone (for the form)."""
    if not value:
        return ""
    return to_utc(value).tz_convert(ZoneInfo(config.DISPLAY_TIMEZONE)).strftime("%Y-%m-%d %H:%M")


def parse_local_time(text):
    """Staff enter times in the display timezone; a written offset is respected. Returns UTC ISO or ''."""
    text = (text or "").strip()
    if not text:
        return ""
    ts = pd.Timestamp(text)
    if ts.tzinfo is None:
        ts = ts.tz_localize(ZoneInfo(config.DISPLAY_TIMEZONE))
    return utc_iso(ts)


def approve_extracted_report(shelter_log_path, extraction, corrected, staff_name, at=None):
    """Validate staff-corrected fields and append them as a validated record.

    extraction: the dict returned by extract_shelter_report (keeps source_text, received_at,
    and the AI's suggested row). corrected: {field: string} from the review form, with
    reported_at in the display timezone. Returns {"status": "saved", "record_id", "row"} or
    {"status": "invalid", "errors": [...]}; nothing is written unless saved.
    """
    errors = []
    if not (staff_name or "").strip():
        errors.append("Enter the approving staff member's name.")
    source_text = extraction.get("source_text") or ""
    if not source_text.strip():
        errors.append("The original report text is missing.")
    try:
        reported_at = parse_local_time(corrected.get("reported_at"))
    except (ValueError, TypeError):
        reported_at = None
        errors.append(f"Report time {corrected.get('reported_at')!r} is not a valid date and time.")

    data = {f: (str(corrected.get(f) or "").strip()) for f in EDITABLE_FIELDS}
    if reported_at is not None:
        data["reported_at"] = reported_at
    approved_at = utc_iso(at or utc_now())
    if reported_at and pd.Timestamp(reported_at) > pd.Timestamp(approved_at):
        errors.append("Report time is later than now.")

    suggested = extraction.get("shelter_row", {})
    changed = [f for f in EDITABLE_FIELDS if f != "reported_at" and data[f] != (suggested.get(f) or "")]
    if (suggested.get("reported_at") or "") != data["reported_at"]:
        changed.append("reported_at")
    row = {**data, "reporter": "", "notes": "AI-extracted; staff-approved"
           + (f"; staff corrected: {', '.join(changed)}" if changed else "; no corrections")}

    # Same validation as uploaded CSVs; errors block saving, warnings are returned
    csv_text = ",".join(SHELTER_COLUMNS) + "\n" + ",".join(
        '"' + str(row.get(c, "")).replace('"', '""') + '"' for c in SHELTER_COLUMNS) + "\n"
    parsed, issues = validate_shelter_reports(load_shelter_reports(io.StringIO(csv_text)))
    errors += [f"{i['field']}: {i['message']}" for i in issues if i["severity"] == "error"]
    warnings = [f"{i['field']}: {i['message']}" for i in issues if i["severity"] == "warning"]
    if errors or parsed.empty or not bool(parsed.iloc[0]["row_ok"]):
        return {"status": "invalid", "errors": errors or ["The record did not pass validation."],
                "warnings": warnings}

    record = {
        **row,
        "record_id": f"ext-{uuid.uuid4().hex[:10]}",
        "source": "ai_extraction",
        "received_at": extraction.get("received_at") or approved_at,
        "status": "validated",
        "validated_by": staff_name.strip(),
        "validated_at": approved_at,
        "supersedes": "",
        "source_text": source_text,
    }
    try:
        append_record(shelter_log_path, record, RECORD_META_COLUMNS + list(SHELTER_COLUMNS))
    except (ValueError, ProtectedPathError) as exc:  # e.g. no source_text column, or the sample data
        return {"status": "invalid", "errors": [f"The shelter report log cannot store this record: {exc}"],
                "warnings": warnings}
    return {"status": "saved", "record_id": record["record_id"], "row": record, "warnings": warnings}
