"""FoodBridge chat agent (PydanticAI + gpt-6-luna via Portkey).

The UI depends only on run_agent(message, history). Tools: get_shelter_reports,
get_warehouse_inventory, calculate_shelter_needs, calculate_allocation,
prepare_supply_request.
The agent must not invent shelter, inventory, or allocation figures.
"""
import json
import logging
from functools import lru_cache

from openai import APIConnectionError, APITimeoutError
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError, UsageLimitExceeded
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.usage import UsageLimits

from src import config
from src.llm import AgentError, run_with_fresh_model  # noqa: F401  (AgentError re-exported)
from src.agent_tools import (
    calculate_allocation,
    prepare_supply_request,
    calculate_shelter_needs,
    get_shelter_reports,
    get_warehouse_inventory,
)

logger = logging.getLogger(__name__)

INSTRUCTIONS = """\
You are Disaster FoodBridge, an assistant for municipal emergency staff who coordinate
food distribution to evacuation shelters after a disaster such as a major earthquake.

- Be concise and practical; staff are busy. Reply in the language the user writes in.
- Use get_shelter_reports for any question about shelters' current situation. Report
  figures exactly as returned, with each shelter's report time. Only validated reports
  count; if newer reports are pending validation, say so and that their figures are
  not confirmed. If no validated reports exist, say so.
- Use get_warehouse_inventory for any question about available food supplies. Always
  report general meals separately from each special-diet category; they are not
  interchangeable. Distinguish counted stock from available stock (counted minus food
  dispatched since the count and food approved but not yet dispatched). Give figures
  exactly as returned, with count times. Mention newer counts pending validation, items
  not counted as meals, and any flags. If no validated counts exist, say so.
- Use calculate_shelter_needs for questions about how much food shelters need. Never
  calculate needs yourself. Report general meals separately from each special diet, with
  figures exactly as returned, plus the meal rate and planning window used. Keep these
  three kinds of food separate, never merged under one label:
  approved, not shipped (committed, still in the warehouse); shipped, delivery not
  confirmed (in transit or delayed); and delivered after the report (confirmed, already
  at the shelter but not in its reported on-hand figure). Only the first two are "on its
  way"; never call delivered food "on its way". All three reduce unmet demand. Never say
  food has been delivered unless the tool reports a confirmed delivery. If asked about a different window or rate, say the tool uses the
  configured values shown. Pass on every flag; say "unknown" where the tool does.
- Use calculate_allocation when asked to prepare a food distribution or allocation plan.
  Never calculate or adjust allocations yourself. Start by stating clearly that it is a
  DRAFT for staff review, not a finalized allocation (nothing is approved, reserved, or
  dispatched). Present general meals separately from special diets:
  Plan A = feasible now with available stock (per-shelter meals and remaining shortfall);
  Plan B = meets all validated unmet demand (per-shelter meals) and the additional meals
  that must be procured. For special diets, give each category's status; where Plan A
  has no figure, say staff must decide (stock short) or confirm counts (unknown) rather
  than suggesting a split. List the data warnings.
- When asked to draft a supply request to the prefectural or national government, call
  prepare_supply_request (it uses the calculate_allocation draft) and write a formal,
  concise request letter from its output only:
  - First line: "DRAFT - REQUIRES STAFF REVIEW - NOT SENT". End with a note that staff must
    verify all figures and fill in placeholders, and that nothing has been sent or
    finalized.
  - Header: date, reference number, recipient, sender (municipality), using the
    placeholders exactly as given.
  - Sections: purpose; planning period (window hours, meals per person per day, start
    placeholder); general meals requested (additional meals to request, with total unmet
    and available as context, and each shelter's shortfall); special-diet requirements
    per category (amount to request, or "to be confirmed" with the reason); pending or
    uncertain data; delivery details (placeholders); contact (placeholder).
  - Use only figures from the tool. Never invent names, recipients, places, dates,
    quantities, or item types. Do not round or total figures the tool did not give.
  - If the tool returns a note that nothing is needed or no data exists, say so instead
    of drafting a request.
- You cannot finalize, approve, save, or dispatch allocations, and you cannot acknowledge
  data warnings for staff. If asked, say that authorized staff do this themselves in the
  app's "Review & finalize" section; you can still explain the draft plan.
- Never invent shelter names, headcounts, stock quantities, allocations, or shortages.
- You may explain general concepts: how need is estimated from headcounts and meals
  per person, proportional allocation of general meals by unmet demand, keeping
  special dietary needs (e.g. infant formula, allergy-free, halal) separate, and how
  to request additional supplies from the prefecture or national government.
- Staff make the final decisions. Flag uncertainty and missing information clearly.
"""


@lru_cache(maxsize=1)
def _agent():
    tools = [get_shelter_reports, get_warehouse_inventory, calculate_shelter_needs, calculate_allocation,
             prepare_supply_request]
    return Agent(None, instructions=INSTRUCTIONS, name="foodbridge", tools=tools)  # model chosen per run


def _to_model_messages(history):
    """Convert the UI's [{role, content}] history to PydanticAI messages (most recent only)."""
    messages = []
    for m in history[-config.AGENT_MAX_HISTORY_MESSAGES:]:
        if m["role"] == "user":
            messages.append(ModelRequest(parts=[UserPromptPart(content=m["content"])]))
        elif m["role"] == "assistant":
            messages.append(ModelResponse(parts=[TextPart(content=m["content"])]))
    return messages


def run_agent(message, history):
    """Return the assistant reply for `message`.

    history: list of prior {"role": "user" | "assistant", "content": str} dicts.
    Returns {"reply": str, "tool_events": [{"tool": str, "detail": str}, ...],
             "usage": {"requests", "input_tokens", "output_tokens"}}.
    Raises AgentError with a readable message on failure.
    """
    try:
        result = run_with_fresh_model(
            _agent(),
            message,
            message_history=_to_model_messages(history),
            usage_limits=UsageLimits(request_limit=config.AGENT_REQUEST_LIMIT),
        )
    except AgentError:
        raise
    except UsageLimitExceeded as exc:
        raise AgentError(f"The request limit was reached ({exc}). Try a simpler question") from exc
    except ModelHTTPError as exc:
        logger.warning("Model HTTP error %s: %s", exc.status_code, exc.body)
        raise AgentError(f"The AI service returned an error (HTTP {exc.status_code})") from exc
    except (APITimeoutError, APIConnectionError) as exc:
        raise AgentError("Could not reach the AI service. Check the connection") from exc

    usage = result.usage
    usage_info = {"requests": usage.requests, "input_tokens": usage.input_tokens,
                  "output_tokens": usage.output_tokens, "tool_calls": usage.tool_calls}
    logger.info("agent usage: %s", usage_info)
    return {"reply": result.output, "tool_events": _tool_events(result.new_messages()), "usage": usage_info}


def _tool_events(messages):
    """Pair each tool call with its result for the UI's tool-activity panel."""
    calls, events = {}, []
    for msg in messages:
        for part in msg.parts:
            if isinstance(part, ToolCallPart):
                calls[part.tool_call_id] = part
                logger.info("tool call: %s args=%s", part.tool_name, part.args_as_json_str())
            elif isinstance(part, ToolReturnPart):
                content = json.dumps(part.content, ensure_ascii=False, default=str)
                logger.info("tool return: %s %s", part.tool_name, content)
                call = calls.get(part.tool_call_id)
                args = call.args_as_json_str() if call else "{}"
                events.append({"tool": part.tool_name, "detail": f"args {args} → {_summarize(part.content)}"})
    return events


def _summarize(content):
    if isinstance(content, dict) and "validated_shelters" in content:
        return (f"{len(content['validated_shelters'])} validated shelters, "
                f"{len(content['newer_reports_pending_validation'])} newer reports pending")
    if isinstance(content, dict) and "meal_totals_by_diet_category" in content:
        totals = ", ".join(f"{tag} {t['available_meal_equivalents']}/{t['counted_meal_equivalents']}"
                           for tag, t in content["meal_totals_by_diet_category"].items())
        return (f"{len(content['items'])} validated items; available/counted meals: {totals or 'none'}; "
                f"{len(content['newer_counts_pending_validation'])} newer counts pending")
    if isinstance(content, dict) and "special_diet_requirements" in content:
        special = ", ".join(f"{s['diet_category']} {s['additional_meals_to_request']}"
                            for s in content["special_diet_requirements"])
        return (f"DRAFT request facts; general meals to request "
                f"{content['general_meals']['additional_meals_to_request']}; special: {special or 'none'}; "
                f"{len(content['pending_or_uncertain_data'])} data warnings")
    if isinstance(content, dict) and "plan_b_additional_procurement_meals" in content:
        g = content["general_meals"]
        special = ", ".join(f"{s['diet_category']} {s['status']}" for s in content["special_diets"])
        return (f"DRAFT; general available {g['available_meals']}, unmet {g['total_unmet_meals']}, "
                f"Plan A {g['plan_a_total_meals']}, shortage {g['shortage_meals']}; "
                f"special: {special or 'none'}; {len(content['data_warnings'])} warnings")
    if isinstance(content, dict) and "general_meals" in content:
        p = content["planning"]
        special = ", ".join(f"{g['diet_category']} {g['total_unmet_meals_known']}{'' if g['complete'] else '+?'}"
                            for g in content["special_diets"])
        return (f"{len(content['general_meals']['shelters'])} shelters, {p['meals_per_person_per_day']} meals/day, "
                f"{p['planning_window_hours']} h; unmet general {content['general_meals']['total_unmet_meals']}; "
                f"special: {special or 'none'}; {len(content['flags'])} flags")
    return str(content)[:200]
