"""Warehouse photo analysis: comparison rules, storage, follow-ups, wiring (offline, no model calls)."""
import hashlib
import json
import os

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from src import config, vision
from src.llm import AgentError
from src.store import load_inventory_log
from src.vision import PhotoAnalysis, compare_with_inventory
from src.workspace import ProtectedPathError

SAMPLE_INVENTORY = os.path.join(config.PROJECT_ROOT, "data", "sample", "inventory_log.csv")
PHOTO = os.path.join(config.PROJECT_ROOT, "data", "sample_photos", "synthetic_wh_b_bay1.png")


def item(label, count=None, unit="pack", basis="counted", readability="clear", per=None, low=None, high=None):
    return {"label_text": label, "label_readability": readability, "description": "x", "location_in_photo": "x",
            "unit_seen": unit, "count_basis": basis, "visible_count": count, "estimate_low": low,
            "estimate_high": high, "units_per_container_on_label": per}


def analysis(*items):
    return PhotoAnalysis(observed_facts=[], uncertain_estimates=[], items=list(items), view_coverage="x")


def findings(result):
    return {(f["label_text"], f["status"]) for f in result["findings"]}


@pytest.fixture
def inventory():
    log, _ = load_inventory_log(SAMPLE_INVENTORY)       # read only
    return log


def test_more_visible_than_recorded_is_a_possible_discrepancy(inventory):
    result = compare_with_inventory(analysis(item("ALLERGEN-FREE CURRY RICE", 36)), inventory, "WH-B")
    [f] = result["findings"]
    assert (f["status"], f["item_id"], f["recorded_quantity"], f["visible_in_record_units"]) == \
        ("possible_discrepancy", "ITM-AF", 30, 36)


def test_fewer_visible_is_never_a_shortage(inventory):
    result = compare_with_inventory(analysis(item("CANNED BREAD 24 cans / case", 6, unit="case")), inventory, "WH-A")
    [f] = result["findings"]
    assert f["status"] == "inconclusive_partial_view" and "not evidence of a shortage" in f["message"]


def test_recorded_items_not_seen_are_inconclusive(inventory):
    result = compare_with_inventory(analysis(item("ALLERGEN-FREE CURRY RICE", 30)), inventory, "WH-B")
    assert findings(result) == {("ALLERGEN-FREE CURRY RICE", "consistent_with_record")}
    assert [n["item_id"] for n in result["not_visible"]] == ["ITM-RICE"]
    assert "no conclusion" in result["not_visible"][0]["message"]


def test_unrecorded_and_unreadable_items_need_review(inventory):
    result = compare_with_inventory(analysis(item("INSTANT MISO SOUP 20 cups", 8, unit="box"),
                                             item(None, 1, unit="carton", readability="unreadable")),
                                    inventory, "WH-A")
    assert findings(result) == {("INSTANT MISO SOUP 20 cups", "possible_discrepancy"), (None, "needs_review")}


def test_item_recorded_in_another_warehouse_is_mentioned(inventory):
    result = compare_with_inventory(analysis(item("ALLERGEN-FREE CURRY RICE", 5)), inventory, "WH-A")
    [f] = result["findings"]
    assert f["status"] == "possible_discrepancy" and "recorded in WH-B" in f["message"]


def test_per_container_label_converts_units_and_says_so(inventory):
    result = compare_with_inventory(analysis(item("ALPHA RICE (RETORT) 50 packs per carton", 3, unit="carton",
                                                  per=50)), inventory, "WH-B")
    [f] = result["findings"]
    assert (f["status"], f["visible_in_record_units"]) == ("possible_discrepancy", 150)
    assert "from label, unverified" in f["visible_basis"]


def test_different_units_without_label_are_not_compared(inventory):
    result = compare_with_inventory(analysis(item("ALPHA RICE (RETORT)", 3, unit="carton")), inventory, "WH-B")
    assert result["findings"][0]["status"] == "not_comparable"


def test_different_units_with_a_count_above_the_record_go_to_review(inventory):
    # found in the real P28 run: 36 curry packs were reported as "cartons" against 30 recorded packs
    result = compare_with_inventory(analysis(item("ALLERGEN-FREE CURRY RICE", 36, unit="carton")), inventory, "WH-B")
    [f] = result["findings"]
    assert f["status"] == "needs_review" and "units differ" in f["message"] and "30 pack" in f["message"]


def test_estimates_use_the_lower_bound(inventory):
    result = compare_with_inventory(analysis(item("ALLERGEN-FREE CURRY RICE", None, basis="estimated", low=25,
                                                  high=40)), inventory, "WH-B")
    [f] = result["findings"]
    assert f["status"] == "inconclusive_partial_view" and f["visible_basis"] == "lower end of estimate"


@pytest.fixture
def photo_store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PHOTO_DIR", str(tmp_path / "photos"))
    monkeypatch.setattr(config, "INVENTORY_LOG_PATH", SAMPLE_INVENTORY)    # read only
    output = analysis(item("ALLERGEN-FREE CURRY RICE", 36)).model_dump()
    monkeypatch.setattr(vision, "_vision_agent",
                        lambda: Agent(TestModel(custom_output_args=output), output_type=PhotoAnalysis))
    monkeypatch.setattr(vision, "_followup_agent",
                        lambda: Agent(TestModel(custom_output_text="I can see 36 packs.")))
    return tmp_path / "photos"


def test_analysis_is_stored_with_an_exact_copy_of_the_image(photo_store):
    inventory_before = hashlib.sha256(open(SAMPLE_INVENTORY, "rb").read()).hexdigest()
    record = vision.analyze_warehouse_photo(PHOTO, "WH-B", taken_at="2026-10-24T15:00+09:00")
    folder = record["stored_in"]
    stored = open(os.path.join(folder, "image.png"), "rb").read()
    assert stored == open(PHOTO, "rb").read()
    assert record["image"]["sha256"] == hashlib.sha256(stored).hexdigest()
    saved = json.load(open(os.path.join(folder, "analysis.json")))
    assert saved["comparison"]["summary"] == {"possible_discrepancy": 1}
    assert saved["taken_at"] == "2026-10-24T06:00:00+00:00"
    assert hashlib.sha256(open(SAMPLE_INVENTORY, "rb").read()).hexdigest() == inventory_before


def test_follow_up_questions_use_the_stored_image_and_are_logged(photo_store):
    record = vision.analyze_warehouse_photo(PHOTO, "WH-B")
    entry = vision.ask_about_photo(record["analysis_id"], "How many curry packs are visible?")
    assert entry["answer"] == "I can see 36 packs."
    lines = open(os.path.join(record["stored_in"], "followups.jsonl")).read().splitlines()
    assert json.loads(lines[0])["question"] == "How many curry packs are visible?"


def test_tampered_stored_image_is_detected(photo_store):
    record = vision.analyze_warehouse_photo(PHOTO, "WH-B")
    with open(os.path.join(record["stored_in"], "image.png"), "ab") as f:
        f.write(b"x")
    with pytest.raises(AgentError, match="does not match"):
        vision.ask_about_photo(record["analysis_id"], "anything?")


def test_photos_cannot_be_stored_in_the_sample_folder(photo_store, monkeypatch):
    monkeypatch.setattr(config, "PHOTO_DIR", os.path.join(config.PROJECT_ROOT, "data", "sample", "photos"))
    with pytest.raises(ProtectedPathError):
        vision.analyze_warehouse_photo(PHOTO, "WH-B")
    assert not os.path.exists(os.path.join(config.PROJECT_ROOT, "data", "sample", "photos"))


def test_unsupported_file_type_is_rejected(tmp_path):
    bad = tmp_path / "photo.gif"
    bad.write_bytes(b"GIF89a")
    with pytest.raises(AgentError, match="Unsupported"):
        vision.analyze_warehouse_photo(str(bad), "WH-A")
