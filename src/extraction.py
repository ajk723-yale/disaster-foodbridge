"""AI extraction of structured fields from free-text shelter reports (PydanticAI + gpt-6-luna).

The model fills a Pydantic output model. Every value is optional (unknown stays None),
must be backed by a verbatim quote, and the model lists missing, ambiguous, or
conflicting information instead of guessing. Code-side checks then verify the quotes
and the consistency of the values, and add their own issues.

Results are pending suggestions for staff review: nothing here is saved or treated
as validated data.
"""
import re
from typing import Literal
from zoneinfo import ZoneInfo

import pandas as pd
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.usage import UsageLimits

from src import config
from src.injection_guard import as_issues, screen_report_text
from src.llm import AgentError, run_with_fresh_model
from src.schemas import GENERAL_TAG, UNKNOWN_COUNT, normalize_tag
from src.timeutil import to_utc


class Evidence(BaseModel):
    field: str = Field(description="Which extracted field this quote supports, e.g. 'evacuee_count'")
    quote: str = Field(description="Exact words copied from the report, unchanged")


class SpecialNeed(BaseModel):
    diet_category: str = Field(description="snake_case English, e.g. infant_formula, allergy_free, halal, soft_food")
    people: int | None = Field(default=None, ge=0, description="Number of people; null if the report gives no number")


class SpecialFood(BaseModel):
    diet_category: str
    meals: float | None = Field(default=None, ge=0, description="Meals or servings on hand; null if not stated as such")


class Issue(BaseModel):
    field: str = Field(description="Affected field, or 'report' for the whole report")
    kind: Literal["missing", "ambiguous", "conflicting"]
    message: str


class ShelterReportExtraction(BaseModel):
    """Structured content of one free-text shelter report. Unknown values stay null."""
    shelter_id: str | None = Field(default=None, description="Shelter ID exactly as written (e.g. SH-01), else null")
    shelter_name: str | None = Field(default=None, description="Shelter name as written, else null")
    evacuee_count: int | None = Field(default=None, ge=0, description="Current number of evacuees; null if not "
                                      "stated as a single clear number")
    general_food_on_hand_meals: float | None = Field(
        default=None, ge=0, description="General food on hand in meals/servings, only if the report states it in "
        "meals or servings; null otherwise (do not convert kg, boxes, or 'enough for' statements)")
    food_on_hand_text: str | None = Field(default=None, description="The report's own words about food on hand")
    special_needs: list[SpecialNeed] = Field(default_factory=list)
    special_food_on_hand: list[SpecialFood] = Field(default_factory=list)
    reported_at_local: str | None = Field(
        default=None, description="'YYYY-MM-DDTHH:MM' only if the report states both an explicit date and time; "
        "else null")
    reported_at_timezone: str | None = Field(
        default=None, description="Timezone only if the report states one (e.g. 'JST', '+09:00'), else null")
    reported_at_text: str | None = Field(default=None, description="The report's own words about when it was written")
    evidence: list[Evidence] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)


INSTRUCTIONS = """\
You extract structured data from one free-text evacuation-shelter report written by shelter staff
(English or Japanese). Staff will review your output; it is never used without review.

Rules:
- Use only what the report states. Never guess, infer, estimate, or fill gaps from typical values.
- If a value is not stated, or not stated clearly enough, leave it null and add an issue
  (kind "missing" or "ambiguous").
- If the report gives conflicting values (e.g. two different headcounts), leave the value null and add an issue
  of kind "conflicting" quoting both.
- evacuee_count: a single current headcount. Approximate wording ("about 80", "around") is ambiguous: leave null
  and report it.
- general_food_on_hand_meals: only if stated in meals or servings. Keep other descriptions (kg, boxes,
  "enough for tonight") in food_on_hand_text and add an "ambiguous" issue.
- special_needs: one entry per diet category with the number of people; people = null if no number is given.
- Report time: fill reported_at_local only when an explicit date and time are both stated. Relative wording
  ("this morning", "just now") or a time without a date: leave null and add an issue. Fill
  reported_at_timezone only if a timezone is written.
- evidence: for every non-null value, add the exact words from the report (copy them, do not translate or
  paraphrase). Use the field names shelter_id, shelter_name, evacuee_count, general_food_on_hand_meals,
  special_needs, special_food_on_hand, reported_at.
- Do not add advice or commentary.
"""

# Evidence field names the model may use, mapped to the checked fields
_FIELD_ALIASES = {"reported_at_local": "reported_at", "reported_at_text": "reported_at",
                  "reported_at_timezone": "reported_at", "food_on_hand_text": "general_food_on_hand_meals"}


def _agent():
    return Agent(None, output_type=ShelterReportExtraction, instructions=INSTRUCTIONS,
                 name="report_extractor", retries=2)  # model chosen per run


def _normalize(text):
    return re.sub(r"\s+", " ", text).strip().casefold()


def _issue(field, kind, message, source="check"):
    return {"field": field, "kind": kind, "message": message, "source": source}


def _report_time(extraction, received_at, issues):
    """Explicit date and time only; the stated timezone, else REPORT_TIMEZONE (always flagged)."""
    if not extraction.reported_at_local:
        if not any(i["field"].startswith("reported_at") for i in issues):
            issues.append(_issue("reported_at", "missing", "no explicit report date and time"))
        return None
    try:
        local = pd.Timestamp(extraction.reported_at_local)
        local = local.tz_localize(None) if local.tzinfo is not None else local
        tz_text = (extraction.reported_at_timezone or "").strip()
        if tz_text.upper() in ("JST", "JAPAN STANDARD TIME"):
            tz_text = "+09:00"
        if not tz_text:
            stamp = local.tz_localize(ZoneInfo(config.REPORT_TIMEZONE))
            issues.append(_issue("reported_at", "ambiguous", "the report states no timezone; interpreted as "
                                 f"{config.REPORT_TIMEZONE} (REPORT_TIMEZONE setting), please confirm"))
        elif tz_text.startswith(("+", "-")):
            stamp = pd.Timestamp(f"{local.isoformat()}{tz_text}")
        else:
            stamp = local.tz_localize(ZoneInfo(tz_text))
        reported_at = to_utc(stamp)
    except (ValueError, TypeError, KeyError) as exc:
        issues.append(_issue("reported_at", "ambiguous",
                             f"could not read report time {extraction.reported_at_local!r}: {exc}"))
        return None
    if received_at is not None and reported_at > to_utc(received_at):
        issues.append(_issue("reported_at", "conflicting", "report time is later than the time it was received"))
        return None
    return reported_at


def check_extraction(extraction, source_text, received_at):
    """Code-side checks of a model extraction. Returns (reported_at_utc_iso | None, issues)."""
    issues = [{**i.model_dump(), "source": "model"} for i in extraction.issues]
    haystack = _normalize(source_text)

    # Every quote must really be in the report; every value needs a quote
    quoted = set()
    for ev in extraction.evidence:
        field = _FIELD_ALIASES.get(ev.field, ev.field)
        if _normalize(ev.quote) in haystack:
            quoted.add(field)
        else:
            issues.append(_issue(field, "ambiguous", f"quoted evidence not found in the report text: {ev.quote!r}"))
    values = {
        "shelter_id": extraction.shelter_id,
        "shelter_name": extraction.shelter_name,
        "evacuee_count": extraction.evacuee_count,
        "general_food_on_hand_meals": extraction.general_food_on_hand_meals,
        "special_needs": [n for n in extraction.special_needs if n.people is not None],
        "special_food_on_hand": [f for f in extraction.special_food_on_hand if f.meals is not None],
        "reported_at": extraction.reported_at_local,
    }
    for field, value in values.items():
        if value not in (None, []) and field not in quoted:
            issues.append(_issue(field, "ambiguous", "value has no supporting quote from the report"))

    if not extraction.shelter_id and not extraction.shelter_name:
        issues.append(_issue("shelter_id", "missing", "no shelter ID or name identified"))
    if extraction.evacuee_count is None and not any(i["field"] == "evacuee_count" for i in issues):
        issues.append(_issue("evacuee_count", "missing", "evacuee count unknown"))

    # Special needs: categories, duplicates, unknown counts, and totals
    seen = {}
    for need in extraction.special_needs:
        tag = normalize_tag(need.diet_category)
        if tag == GENERAL_TAG:
            issues.append(_issue("special_needs", "ambiguous", "'general' is not a special diet category"))
        if tag in seen:
            issues.append(_issue("special_needs", "conflicting", f"'{tag}' listed more than once"))
        seen[tag] = need.people
        if need.people is None:
            issues.append(_issue("special_needs", "missing", f"number of people needing '{tag}' unknown"))
    for food in extraction.special_food_on_hand:
        if food.meals is None and not any(i["field"] == "special_food_on_hand" for i in issues):
            issues.append(_issue("special_food_on_hand", "ambiguous",
                                 f"amount of '{normalize_tag(food.diet_category)}' food on hand is not stated in "
                                 "meals; it is left out of the row"))
    known = sum(p for p in seen.values() if p is not None)
    if extraction.evacuee_count is not None and known > extraction.evacuee_count:
        issues.append(_issue("special_needs", "conflicting",
                             f"special-diet people ({known}) exceed the evacuee count ({extraction.evacuee_count})"))

    reported_at = _report_time(extraction, received_at, issues)
    return (reported_at.isoformat() if reported_at is not None else None), issues


def to_shelter_row(extraction, reported_at):
    """Map to the shelter-report CSV fields (strings). Unknown values stay empty, so the
    row cannot pass validation until staff fill them in."""
    needs = "; ".join(f"{normalize_tag(n.diet_category)}:{UNKNOWN_COUNT if n.people is None else n.people}"
                      for n in extraction.special_needs)
    stock = "; ".join(f"{normalize_tag(f.diet_category)}:{f.meals:g}" for f in extraction.special_food_on_hand
                      if f.meals is not None)
    return {
        "shelter_id": extraction.shelter_id or "",
        "shelter_name": extraction.shelter_name or "",
        "reported_at": reported_at or "",
        "evacuee_count": "" if extraction.evacuee_count is None else str(extraction.evacuee_count),
        "general_on_hand_meals": "" if extraction.general_food_on_hand_meals is None
        else f"{extraction.general_food_on_hand_meals:g}",
        "special_needs": needs,
        "special_on_hand_meals": stock,
        "reporter": "",
        "notes": "AI-extracted; pending staff review",
    }


def extract_shelter_report(text, received_at, screen=True):
    """Extract one report. Returns a dict with the original text, the model's structured
    output, the checked report time (UTC), all issues, a CSV-shaped row, and token usage.
    Status is always 'pending': nothing is saved or validated here.

    screen=True also screens the untrusted text for instructions aimed at the AI or software
    (src/injection_guard.py). Findings are added as staff warnings and in "safety_screen"; they
    do not change the extracted values, validation, or approval."""
    if not text or not text.strip():
        raise AgentError("The report text is empty")
    try:
        result = run_with_fresh_model(_agent(), f"Report text:\n<<<\n{text}\n>>>",
                                      usage_limits=UsageLimits(request_limit=config.AGENT_REQUEST_LIMIT))
    except UsageLimitExceeded as exc:
        raise AgentError(f"The request limit was reached ({exc})") from exc
    except ModelHTTPError as exc:
        raise AgentError(f"The AI service returned an error (HTTP {exc.status_code})") from exc
    except UnexpectedModelBehavior as exc:
        raise AgentError(f"The AI output could not be read as a report ({exc})") from exc

    extraction = result.output
    reported_at, issues = check_extraction(extraction, text, received_at)
    usage = result.usage
    extraction_usage = {"requests": usage.requests, "input_tokens": usage.input_tokens,
                        "output_tokens": usage.output_tokens}
    safety = screen_report_text(text) if screen else None
    if safety:
        issues = issues + as_issues(safety)
    total = {k: extraction_usage[k] + (safety["usage"][k] if safety else 0) for k in extraction_usage}
    return {
        "status": "pending: AI-extracted, not validated; staff review required",
        "source_text": text,
        "received_at": to_utc(received_at).isoformat(),
        "model": config.MODEL,
        "extracted": extraction.model_dump(),
        "reported_at_utc": reported_at,
        "issues": issues,
        "shelter_row": to_shelter_row(extraction, reported_at),
        "safety_screen": safety,
        "usage": total,
        "usage_breakdown": {"extraction": extraction_usage, "safety_screen": safety["usage"] if safety else None},
    }
