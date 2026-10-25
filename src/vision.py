"""Warehouse photo analysis (PydanticAI vision + gpt-6-luna via Portkey).

analyze_warehouse_photo() sends one photo to the model with a structured output type
that separates what is observed (readable label text, individually counted units)
from what is uncertain (estimates, unreadable labels). The model is not shown the
inventory, so it cannot "see" what it expects.

The comparison with the latest validated inventory records happens in code. A photo
may show only part of a warehouse, so:
- more units visible than recorded, or an item that isn't in the records, is a
  possible discrepancy for staff review;
- fewer units visible, or a recorded item not visible, is inconclusive, never a
  shortage.

Each analysis is stored with an exact copy of its image (data/live/photos/<id>/) so
staff can inspect it and ask follow-up questions (ask_about_photo). Nothing here
changes inventory records or allocation.
"""
import difflib
import hashlib
import json
import os
import re
import shutil
import uuid
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent, BinaryContent, CachePoint
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.usage import UsageLimits

from src import config
from src.llm import AgentError, run_with_fresh_model
from src.records import latest_validated
from src.store import load_inventory_log
from src.timeutil import utc_iso, utc_now
from src.workspace import assert_writable

MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024


class ObservedItem(BaseModel):
    label_text: str | None = Field(default=None, description="Label text exactly as readable in the photo; null if "
                                   "not readable. Do not complete or correct partial words.")
    label_readability: Literal["clear", "partial", "unreadable"]
    description: str = Field(description="What is visible, e.g. 'brown cardboard cases on the top shelf'")
    location_in_photo: str = Field(description="Where in the photo, e.g. 'top shelf, left half'")
    unit_seen: str | None = Field(default=None, description="The visible unit: case, carton, box, pack, bottle…")
    count_basis: Literal["counted", "estimated", "not_countable"] = Field(
        description="'counted' only if every unit is individually visible and was counted")
    visible_count: int | None = Field(default=None, ge=0, description="Exact count of visible units if counted")
    estimate_low: int | None = Field(default=None, ge=0, description="Lower bound if estimated")
    estimate_high: int | None = Field(default=None, ge=0, description="Upper bound if estimated")
    units_per_container_on_label: int | None = Field(
        default=None, ge=0, description="Only if a label states it (e.g. '50 packs per carton'); else null")
    uncertainty: str | None = Field(default=None, description="Why the label or count is uncertain, if it is")


class PhotoAnalysis(BaseModel):
    observed_facts: list[str] = Field(description="Statements directly visible in the photo")
    uncertain_estimates: list[str] = Field(description="Estimates, guesses about hidden parts, unreadable labels")
    items: list[ObservedItem]
    view_coverage: str = Field(description="What part of the storage area is visible and whether anything is cut "
                               "off, hidden, or stacked out of view")
    image_quality_issues: list[str] = Field(default_factory=list)


INSTRUCTIONS = """\
You analyze one photo of a municipal disaster-relief food warehouse for staff review.

Rules:
- Report only what is visible. Do not assume the photo shows the whole warehouse or the total stock.
- label_text: copy readable label text exactly; if a label is blurred or too small, set label_readability to
  "unreadable" or "partial" and do not guess the words.
- Count units only when each one is individually visible (count_basis "counted"). If units are hidden, stacked
  behind others, or too many to count reliably, use "estimated" with a range, or "not_countable".
- units_per_container_on_label only when a label states it. Never multiply or infer contents yourself.
- Put direct observations in observed_facts and anything uncertain in uncertain_estimates.
- Describe in view_coverage what is cut off or not visible.
"""

FOLLOWUP_INSTRUCTIONS = """\
You answer staff questions about one warehouse photo that was analyzed before. Answer only from what is visible
in the photo and the earlier analysis. Say clearly what you can see versus what is uncertain, and say so if the
photo cannot answer the question. Never assume the photo shows the whole warehouse. Be concise.
"""


def _vision_agent():
    return Agent(None, output_type=PhotoAnalysis, instructions=INSTRUCTIONS, name="photo_analyzer",
                 retries=2)  # model chosen per run


def _followup_agent():
    return Agent(None, instructions=FOLLOWUP_INSTRUCTIONS, name="photo_followup")  # model chosen per run


def _read_image(image_path):
    ext = os.path.splitext(image_path)[1].lower()
    if ext not in MEDIA_TYPES:
        raise AgentError(f"Unsupported image type {ext!r}; use PNG, JPEG, or WebP")
    data = open(image_path, "rb").read()
    if len(data) > MAX_IMAGE_BYTES:
        raise AgentError("Image is larger than 10 MB")
    return data, MEDIA_TYPES[ext]


def _run(agent, content):
    try:
        return run_with_fresh_model(agent, content,
                                    usage_limits=UsageLimits(request_limit=config.AGENT_REQUEST_LIMIT))
    except UsageLimitExceeded as exc:
        raise AgentError(f"The request limit was reached ({exc})") from exc
    except ModelHTTPError as exc:
        raise AgentError(f"The AI service returned an error (HTTP {exc.status_code}): {exc.body}") from exc
    except UnexpectedModelBehavior as exc:
        raise AgentError(f"The AI output could not be read ({exc})") from exc


def _usage(result):
    u = result.usage
    return {"requests": u.requests, "input_tokens": u.input_tokens, "output_tokens": u.output_tokens}


# ---- comparison with validated inventory (code only) ---------------------------

def _tokens(text):
    return " ".join(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _similarity(label, name):
    a, b = _tokens(label), _tokens(name)
    if not a or not b:
        return 0.0
    if b in a or a in b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _unit(text):
    return re.sub(r"(es|s)$", "", _tokens(text).split(" ")[0]) if text else ""


MATCH_THRESHOLD = 0.6


def _match(label, records):
    best = max(records, key=lambda r: _similarity(label, r["item_name"]), default=None)
    return best if best is not None and _similarity(label, best["item_name"]) >= MATCH_THRESHOLD else None


def compare_with_inventory(analysis, inventory_log, warehouse_id):
    """Compare a PhotoAnalysis with the latest validated records for warehouse_id.

    Returns {"warehouse_id", "inventory_record_ids", "findings", "not_visible", "summary"}.
    Finding status: possible_discrepancy | needs_review | inconclusive_partial_view | not_comparable |
    consistent_with_record.
    """
    latest = latest_validated(inventory_log, ["warehouse_id", "item_id"], "counted_at")
    rows = [] if latest is None or latest.empty else latest.to_dict("records")
    here = [r for r in rows if r["warehouse_id"] == warehouse_id]
    elsewhere = [r for r in rows if r["warehouse_id"] != warehouse_id]
    findings, matched_ids = [], set()

    for item in analysis.items:
        f = {"label_text": item.label_text, "unit_seen": item.unit_seen, "count_basis": item.count_basis,
             "visible_count": item.visible_count, "estimate": [item.estimate_low, item.estimate_high]}
        if item.label_readability == "unreadable" or not item.label_text:
            findings.append({**f, "status": "needs_review",
                             "message": "label not readable in the photo; staff should identify this item"})
            continue
        record = _match(item.label_text, here)
        if record is None:
            other = _match(item.label_text, elsewhere)
            note = (f"; an item with a similar name is recorded in {other['warehouse_id']} ({other['item_name']})"
                    if other else "")
            findings.append({**f, "status": "possible_discrepancy",
                             "message": f"visible item is not in the validated inventory for {warehouse_id}{note}"})
            continue
        matched_ids.add(record["item_id"])
        recorded = float(record["quantity"])
        f.update(item_id=record["item_id"], item_name=record["item_name"], recorded_quantity=recorded,
                 recorded_unit=record["unit"], counted_at=record["counted_at"].isoformat())

        # Units seen in the photo, possibly converted with a per-container figure from the label
        seen = item.visible_count if item.count_basis == "counted" else item.estimate_low
        basis = "counted" if item.count_basis == "counted" else "lower end of estimate"
        if seen is not None and _unit(item.unit_seen) != _unit(record["unit"]) and item.units_per_container_on_label:
            seen, basis = seen * item.units_per_container_on_label, f"{basis} × {item.units_per_container_on_label} " \
                                                                       f"per container (from label, unverified)"
        elif seen is not None and _unit(item.unit_seen) != _unit(record["unit"]):
            # Units differ and no label says how they relate: don't compare, but don't hide a count that
            # already exceeds the recorded number either
            if seen > recorded:
                f.update(visible_in_record_units=None, visible_basis=None, status="needs_review",
                         message=f"{seen} {item.unit_seen} visible ({basis}) vs {recorded:g} {record['unit']} "
                                 f"recorded; units differ, but if each {item.unit_seen} is one {record['unit']} "
                                 "this exceeds the record; staff should check")
                findings.append(f)
                continue
            seen = None
        f["visible_in_record_units"] = seen
        f["visible_basis"] = basis if seen is not None else None

        if seen is None:
            f.update(status="not_comparable", message=f"photo units ({item.unit_seen}) can't be compared with the "
                     f"record's unit ({record['unit']}) or the count is not available")
        elif seen > recorded:
            f.update(status="possible_discrepancy", message=f"at least {seen:g} {record['unit']} visible ({basis}) "
                     f"but {recorded:g} recorded; check the count or the record")
        elif seen < recorded:
            f.update(status="inconclusive_partial_view", message=f"{seen:g} {record['unit']} visible, {recorded:g} "
                     "recorded; the rest may be outside the photo, so this is not evidence of a shortage")
        else:
            f.update(status="consistent_with_record", message=f"{seen:g} {record['unit']} visible, same as recorded "
                     "(the photo may still not show all stock)")
        findings.append(f)

    not_visible = [{"item_id": r["item_id"], "item_name": r["item_name"], "recorded_quantity": float(r["quantity"]),
                    "recorded_unit": r["unit"],
                    "message": "not identified in this photo; no conclusion (the photo may show only part of the "
                               "warehouse)"}
                   for r in here if r["item_id"] not in matched_ids]
    counts = {}
    for f in findings:
        counts[f["status"]] = counts.get(f["status"], 0) + 1
    return {"warehouse_id": warehouse_id,
            "inventory_record_ids": sorted(r["record_id"] for r in here),
            "findings": findings, "not_visible": not_visible, "summary": counts,
            "note": "Compared with the latest validated inventory records. A photo is not evidence of total stock; "
                    "inventory records were not changed."}


# ---- analysis, storage, and follow-up -------------------------------------------

def analyze_warehouse_photo(image_path, warehouse_id, taken_at=None, save=True):
    """Analyze one warehouse photo and compare it with the validated inventory for warehouse_id.

    Returns the analysis record (also stored with a copy of the image when save=True).
    """
    data, media_type = _read_image(image_path)
    result = _run(_vision_agent(), [
        f"Warehouse photo for staff review. Staff say it was taken in warehouse {warehouse_id}.",
        BinaryContent(data=data, media_type=media_type)])
    analysis = result.output
    inventory_log, _ = load_inventory_log(config.INVENTORY_LOG_PATH)
    record = {
        "analysis_id": f"photo-{uuid.uuid4().hex[:10]}",
        "status": "AI photo analysis for staff review; inventory records not changed",
        "warehouse_id": warehouse_id,
        "taken_at": utc_iso(taken_at) if taken_at else None,
        "analyzed_at": utc_iso(utc_now()),
        "model": config.MODEL,
        "image": {"original_name": os.path.basename(image_path), "media_type": media_type,
                  "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()},
        "analysis": analysis.model_dump(),
        "comparison": compare_with_inventory(analysis, inventory_log, warehouse_id),
        "usage": _usage(result),
    }
    if save:
        record["stored_in"] = save_photo_analysis(image_path, record)
    return record


def _photo_dir(analysis_id):
    return os.path.join(config.PHOTO_DIR, analysis_id)


def photo_folder(analysis_id):
    """Folder holding the stored image, analysis.json, and followups.jsonl for an analysis."""
    return _photo_dir(analysis_id)


def save_photo_analysis(image_path, record):
    """Store the exact image bytes next to the analysis JSON. Returns the folder path."""
    folder = _photo_dir(record["analysis_id"])
    assert_writable(folder)
    os.makedirs(folder, exist_ok=False)
    ext = os.path.splitext(image_path)[1].lower()
    shutil.copyfile(image_path, os.path.join(folder, f"image{ext}"))
    record["image"]["stored_file"] = f"image{ext}"
    with open(os.path.join(folder, "analysis.json"), "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return folder


def load_photo_analysis(analysis_id):
    folder = _photo_dir(analysis_id)
    with open(os.path.join(folder, "analysis.json"), encoding="utf-8") as f:
        record = json.load(f)
    data = open(os.path.join(folder, record["image"]["stored_file"]), "rb").read()
    if hashlib.sha256(data).hexdigest() != record["image"]["sha256"]:
        raise AgentError(f"stored image for {analysis_id} does not match its recorded SHA-256")
    return record, data


def ask_about_photo(analysis_id, question):
    """Answer a follow-up question using the stored image and its analysis; the Q&A is appended to
    followups.jsonl next to the image."""
    record, data = load_photo_analysis(analysis_id)
    result = _run(_followup_agent(), [
        "Earlier analysis (JSON):\n" + json.dumps(record["analysis"], ensure_ascii=False),
        BinaryContent(data=data, media_type=record["image"]["media_type"]),
        CachePoint(),  # cache breakpoint: later questions on the same photo reuse the prefix (P35)
        f"Staff question: {question}"])
    entry = {"asked_at": utc_iso(utc_now()), "question": question, "answer": result.output,
             "usage": _usage(result)}
    folder = _photo_dir(analysis_id)
    assert_writable(folder)
    with open(os.path.join(folder, "followups.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry
