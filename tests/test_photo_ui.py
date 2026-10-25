"""Warehouse photos tab: callbacks drive the existing vision code, stay read-only (offline, no model calls)."""
import base64
import hashlib
import os

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

import app
from src import config, vision
from src.finalization import review_plan
from src.agent_tools import planning_config
from src.vision import PhotoAnalysis
from tests.test_vision import analysis, item
from tests.test_workspace import live  # noqa: F401  (fixture: seeded working folder, sample hashes checked)
from src.workspace import ensure_working_data

PHOTO = os.path.join(config.PROJECT_ROOT, "data", "sample_photos", "synthetic_wh_b_bay1.png")


def contents(path):
    return "data:image/png;base64," + base64.b64encode(open(path, "rb").read()).decode()


def file_hashes(folder):
    return {f: hashlib.sha256(open(os.path.join(folder, f), "rb").read()).hexdigest()
            for f in sorted(os.listdir(folder)) if f.endswith((".csv", ".db"))}


def text_of(component):
    """All text in a Dash component tree."""
    if component is None:
        return ""
    if isinstance(component, (str, int, float)):
        return str(component)
    if isinstance(component, (list, tuple)):
        return " ".join(text_of(c) for c in component)
    return text_of(getattr(component, "children", None))


@pytest.fixture
def fake_models(monkeypatch):
    output = analysis(item("ALLERGEN-FREE CURRY RICE", 36, unit="carton"),
                      item("ALPHA RICE (RETORT) 50 packs per carton", 3, unit="carton", per=50)).model_dump()
    monkeypatch.setattr(vision, "_vision_agent",
                        lambda: Agent(TestModel(custom_output_args=output), output_type=PhotoAnalysis))
    monkeypatch.setattr(vision, "_followup_agent", lambda: Agent(TestModel(custom_output_text="36 packs visible.")))


def test_upload_analyze_review_and_follow_up_without_changing_data(live, fake_models, monkeypatch):  # noqa: F811
    ensure_working_data()
    monkeypatch.setattr(config, "PHOTO_DIR", str(live / "photos"))
    before = file_hashes(live)
    plan_before = review_plan(config.FINALIZATION_DB_PATH, config.SHELTER_LOG_PATH, config.INVENTORY_LOG_PATH,
                              config.COMMITMENTS_LOG_PATH, planning_config())

    assert [o["value"] for o in app.warehouse_options(1)] == ["WH-A", "WH-B"]
    analysis_id, message, result, box_style, _ = app.analyze_photo(1, contents(PHOTO), "synthetic_wh_b_bay1.png",
                                                                   "WH-B")
    shown = text_of(result)
    assert "read-only; inventory unchanged" in text_of(message)
    assert "Possible discrepancy" in shown and "Needs review" in shown and "units differ" in shown
    img = result.children[0].children[0]
    assert img.src == contents(PHOTO)                                    # the stored image, byte for byte
    assert box_style == {}

    followups, cleared = app.ask_photo(1, "How many curry packs?", analysis_id)
    assert "36 packs visible." in text_of(followups) and cleared == ""
    assert os.path.exists(os.path.join(live, "photos", analysis_id, "followups.jsonl"))

    # read-only: working CSVs, finalization database (if any), and the plan are unchanged
    assert file_hashes(live) == before
    plan_after = review_plan(config.FINALIZATION_DB_PATH, config.SHELTER_LOG_PATH, config.INVENTORY_LOG_PATH,
                             config.COMMITMENTS_LOG_PATH, planning_config())
    assert plan_after["fingerprint"] == plan_before["fingerprint"]


def test_missing_photo_or_warehouse_is_reported(fake_models):
    _, message, *_ = app.analyze_photo(1, None, None, "WH-A")
    assert "Choose a photo first" in text_of(message)
    _, message, *_ = app.analyze_photo(1, contents(PHOTO), "x.png", None)
    assert "Choose the warehouse" in text_of(message)


def test_unsupported_upload_shows_an_error(fake_models, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PHOTO_DIR", str(tmp_path / "photos"))
    analysis_id, message, *_ = app.analyze_photo(1, "data:image/gif;base64,R0lGODlh", "photo.gif", "WH-A")
    assert analysis_id is None and "Unsupported image type" in text_of(message)
