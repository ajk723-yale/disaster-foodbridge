"""Free-text report extraction: code-side checks and agent wiring (offline, no model calls)."""
import io

import pandas as pd
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from src import config, extraction
from src.data_io import load_shelter_reports
from src.extraction import ShelterReportExtraction, check_extraction, extract_shelter_report, to_shelter_row
from src.validation import validate_shelter_reports

TEXT = ("Minami Elementary (SH-01) report 2026-10-24 08:00. 120 evacuees now. "
        "We have 40 meals left. 3 infants need formula.")
RECEIVED = "2026-10-24T08:10+09:00"


def make(**kwargs):
    base = dict(shelter_id="SH-01", shelter_name="Minami Elementary", evacuee_count=120,
                general_food_on_hand_meals=40, special_needs=[{"diet_category": "infant_formula", "people": 3}],
                reported_at_local="2026-10-24T08:00",
                evidence=[{"field": "shelter_id", "quote": "SH-01"},
                          {"field": "shelter_name", "quote": "Minami Elementary"},
                          {"field": "evacuee_count", "quote": "120 evacuees now"},
                          {"field": "general_food_on_hand_meals", "quote": "40 meals left"},
                          {"field": "special_needs", "quote": "3 infants need formula"},
                          {"field": "reported_at", "quote": "2026-10-24 08:00"}])
    base.update(kwargs)
    return ShelterReportExtraction(**base)


def kinds(issues):
    return {(i["field"], i["kind"]) for i in issues}


def test_complete_report_has_only_the_timezone_note():
    reported_at, issues = check_extraction(make(), TEXT, RECEIVED)
    assert reported_at == "2026-10-23T23:00:00+00:00"          # 08:00 Asia/Tokyo in UTC
    assert kinds(issues) == {("reported_at", "ambiguous")}
    assert "REPORT_TIMEZONE" in issues[0]["message"]


def test_stated_timezone_is_used_without_a_note():
    reported_at, issues = check_extraction(make(reported_at_timezone="JST"), TEXT, RECEIVED)
    assert reported_at == "2026-10-23T23:00:00+00:00" and issues == []


def test_quote_not_in_the_text_is_flagged():
    ext = make(evidence=make().evidence + [{"field": "evacuee_count", "quote": "about 200 people"}])
    _, issues = check_extraction(ext, TEXT, RECEIVED)
    assert any("not found in the report text" in i["message"] for i in issues)


def test_value_without_quote_is_flagged():
    ext = make(evidence=[e for e in make().evidence if e.field != "evacuee_count"])
    _, issues = check_extraction(ext, TEXT, RECEIVED)
    assert ("evacuee_count", "ambiguous") in kinds(issues)


def test_missing_values_stay_unknown_and_are_flagged():
    ext = ShelterReportExtraction(food_on_hand_text="rice for tonight")
    reported_at, issues = check_extraction(ext, "We still have rice for tonight.", RECEIVED)
    assert reported_at is None
    assert {("shelter_id", "missing"), ("evacuee_count", "missing"), ("reported_at", "missing")} <= kinds(issues)
    row = to_shelter_row(ext, reported_at)
    assert row["evacuee_count"] == "" and row["general_on_hand_meals"] == "" and row["reported_at"] == ""


def test_special_needs_checks():
    ext = make(evacuee_count=2, special_needs=[{"diet_category": "Infant Formula", "people": 3},
                                               {"diet_category": "halal", "people": None}])
    _, issues = check_extraction(ext, TEXT, RECEIVED)
    assert ("special_needs", "conflicting") in kinds(issues)            # 3 > 2 evacuees
    assert any("'halal' unknown" in i["message"] for i in issues)
    assert to_shelter_row(ext, None)["special_needs"] == "infant_formula:3; halal:?"


def test_report_time_later_than_receipt_is_rejected():
    reported_at, issues = check_extraction(make(reported_at_local="2026-10-25T08:00"), TEXT, RECEIVED)
    assert reported_at is None and ("reported_at", "conflicting") in kinds(issues)


def test_model_issues_are_kept_with_their_source():
    ext = make(evacuee_count=None, issues=[{"field": "evacuee_count", "kind": "conflicting",
                                            "message": "120 and 150 both stated"}])
    _, issues = check_extraction(ext, TEXT, RECEIVED)
    assert {"field": "evacuee_count", "kind": "conflicting", "message": "120 and 150 both stated",
            "source": "model"} in issues
    assert not any(i["field"] == "evacuee_count" and i["kind"] == "missing" for i in issues)


def _validate(row):
    csv = ",".join(row) + "\n" + ",".join(f'"{v}"' for v in row.values()) + "\n"
    df, _ = validate_shelter_reports(load_shelter_reports(io.StringIO(csv)))
    return bool(df.iloc[0]["row_ok"]) if not df.empty else False


def test_rows_map_to_the_shelter_schema_and_incomplete_rows_cannot_validate():
    reported_at, _ = check_extraction(make(), TEXT, RECEIVED)
    assert _validate(to_shelter_row(make(), reported_at))
    assert not _validate(to_shelter_row(make(evacuee_count=None), reported_at))
    assert not _validate(to_shelter_row(make(), None))


def test_extract_wiring_offline(monkeypatch):
    output = make(evidence=[], issues=[]).model_dump()
    monkeypatch.setattr(extraction, "_agent", lambda: Agent(TestModel(custom_output_args=output),
                                                            output_type=ShelterReportExtraction))
    text = "  Original   text\nwith odd   spacing  "
    result = extract_shelter_report(text, RECEIVED)
    assert result["source_text"] == text                                # preserved exactly
    assert result["status"].startswith("pending")
    assert result["received_at"] == pd.Timestamp(RECEIVED).tz_convert("UTC").isoformat()
    assert result["extracted"]["evacuee_count"] == 120
    assert any("no supporting quote" in i["message"] for i in result["issues"])
    # extraction + safety screen (P31): one request each, total reported in "usage"
    assert result["usage_breakdown"]["extraction"]["requests"] == 1
    assert result["usage_breakdown"]["safety_screen"]["requests"] == 1
    assert result["usage"]["requests"] == 2
    assert result["safety_screen"]["flagged"] is False
    assert config.MODEL == "gpt-6-luna"


def test_special_food_without_a_meal_amount_is_flagged_not_dropped_silently():
    ext = make(special_food_on_hand=[{"diet_category": "infant_formula", "meals": None}])
    _, issues = check_extraction(ext, TEXT, RECEIVED)
    assert any(i["field"] == "special_food_on_hand" and "not stated in meals" in i["message"] for i in issues)
    assert to_shelter_row(ext, None)["special_on_hand_meals"] == ""


def test_each_run_gets_its_own_client_closed_in_the_same_event_loop(monkeypatch):
    import asyncio
    from src import llm

    closed = []

    class FakeClient:
        async def close(self):
            closed.append(asyncio.get_running_loop())

    def fake_model(capture=None):
        model = TestModel(custom_output_text="ok")
        model.client = FakeClient()
        return model

    monkeypatch.setattr(llm, "new_model", fake_model)
    agent = Agent(None)
    loops = []
    for _ in range(2):
        result = llm.run_with_fresh_model(agent, "hi")
        assert result.output == "ok"
        loops.append(closed[-1])
    assert len(closed) == 2 and loops[0] is not loops[1]          # one client per run, closed in its own loop
    # an agent that already has a model keeps it (tests never get a real model)
    assert llm.run_with_fresh_model(Agent(TestModel(custom_output_text="own")), "hi").output == "own"
    assert len(closed) == 2


def test_missing_key_is_reported_before_any_call(monkeypatch):
    import pytest
    from src import llm
    monkeypatch.setattr(config, "PORTKEY_API_KEY", None)
    with pytest.raises(llm.AgentError, match="PORTKEY_API_KEY"):
        llm.run_with_fresh_model(Agent(None), "hi")
