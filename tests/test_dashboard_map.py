"""Dashboard map (P39): fictional training positions only, statuses from the existing calculations,
details panel with validated demand / proposed Plan A / remaining shortage / warnings, no distances or routes."""
import json
import os
import re

import pandas as pd
import pytest

from src import config
from src.dashboard import build_dashboard
from src.dashboard_map import (NotFictionalError, details_panel, find, load_training_locations, map_entities,
                               map_figure)
from tests import test_dashboard
from tests.test_dashboard import RICE, SHELTERS, text_of, tool_outputs

data = test_dashboard.data            # reuse the small-CSV fixture

SAMPLE = os.path.join(config.PROJECT_ROOT, "data", "sample")


def sample_dashboard(monkeypatch):
    return build_dashboard(*tool_outputs(monkeypatch))


def test_sample_records_have_no_coordinates():
    for name in ("shelter_log.csv", "inventory_log.csv"):
        cols = {c.lower() for c in pd.read_csv(os.path.join(SAMPLE, name), nrows=0).columns}
        assert not cols & {"lat", "latitude", "lon", "lng", "longitude", "x", "y", "address", "coordinates"}


def test_training_locations_are_labeled_fictional_and_cover_the_sample():
    locs = load_training_locations()
    assert locs["fictional"] is True and "NOT REAL" in locs["label"].upper()
    assert "not latitude/longitude" in locs["coordinate_system"].lower()
    assert all(set(loc) == {"id", "kind", "x", "y"} for loc in locs["locations"])     # no lat/lon fields
    ids = {loc["id"] for loc in locs["locations"]}
    shelters = set(pd.read_csv(os.path.join(SAMPLE, "shelter_log.csv"))["shelter_id"])
    warehouses = set(pd.read_csv(os.path.join(SAMPLE, "inventory_log.csv"))["warehouse_id"])
    assert shelters | warehouses <= ids
    assert not config.TRAINING_LOCATIONS_PATH.startswith(SAMPLE)                      # sample data untouched


def test_unlabeled_location_files_are_refused(tmp_path):
    bad = tmp_path / "real.json"
    bad.write_text(json.dumps({"label": "Shelter locations", "locations": []}))
    with pytest.raises(NotFictionalError):
        load_training_locations(str(bad))


def test_marker_status_comes_from_the_calculations(monkeypatch):
    d = sample_dashboard(monkeypatch)
    e = {x["id"]: x for x in map_entities(d, load_training_locations())}
    assert {k: (v["kind"], v["status"], v["pending"]) for k, v in e.items()} == {
        "SH-01": ("shelter", "shortage", False), "SH-02": ("shelter", "shortage", True),
        "SH-03": ("shelter", "shortage", True), "SH-04": ("shelter", "no_report", True),
        "WH-A": ("warehouse", "ok", True), "WH-B": ("warehouse", "ok", False)}
    row = next(r for r in d["plans"]["rows"] if r["shelter_id"] == "SH-01")
    assert (e["SH-01"]["facts"]["unmet_meals"], e["SH-01"]["facts"]["plan_a_meals"],
            e["SH-01"]["facts"]["shortfall_meals"]) == (row["unmet_meals"], row["plan_a_meals"],
                                                        row["plan_a_shortfall_meals"])


def test_status_follows_the_data(data):
    d = data(SHELTERS, RICE.format(500))                     # enough stock: no shortage anywhere
    e = map_entities(d, {"locations": [{"id": "S1", "kind": "shelter", "x": 1, "y": 1}]})
    assert {x["id"]: x["status"] for x in e} == {"S1": "ok", "S2": "ok", "W1": "ok"}
    assert [x["id"] for x in e if x["x"] is None] == ["S2", "W1"]                    # unplaced, not invented
    fig = map_figure(e)
    assert sum(len(t.x) for t in fig.data) == 1


def test_details_panel_shows_demand_plan_a_shortage_and_warnings(monkeypatch):
    d = sample_dashboard(monkeypatch)
    e = map_entities(d, load_training_locations())
    text = text_of(details_panel(find(e, "SH-03")))
    for expected in ("Higashi Junior High Gym", "Validated demand (unmet)", "590 meals", "Plan A (proposed)",
                     "351 meals", "Remaining shortage", "239 meals", "halal", "Next step",
                     "Map position is fictional"):
        assert expected in text, expected
    missing = text_of(details_panel(find(e, "SH-04")))
    assert "No validated report" in missing and "Report intake" in missing
    wh = text_of(details_panel(find(e, "WH-A")))
    assert "Canned bread" in wh and "not validated" in wh
    assert "Select a shelter" in text_of(details_panel(None))


def test_no_distances_routes_or_dispatch_claims(monkeypatch):
    d = sample_dashboard(monkeypatch)
    e = map_entities(d, load_training_locations())
    text = " ".join(text_of(details_panel(x)) for x in e)
    assert not re.search(r"\b(km|kilomet\w*|miles?|minutes?|hours? away|route|driving|travel time|eta)\b", text, re.I)
    assert not re.search(r"\b(dispatched|approved|sent|delivered)\b", text.replace("enter and approve it", ""), re.I)
    fig = map_figure(e)
    label = fig.layout.annotations[0].text
    assert "FICTIONAL TRAINING LAYOUT" in label and "not real locations" in label
    assert fig.layout.xaxis.showticklabels is False and fig.layout.yaxis.showticklabels is False


def test_markers_are_distinct_and_selection_is_highlighted(monkeypatch):
    e = map_entities(sample_dashboard(monkeypatch), load_training_locations())
    fig = map_figure(e)
    symbols = {t.name: t.marker.symbol for t in fig.data}
    assert symbols == {"warehouse": "square", "shelter": "circle"}
    shelters = next(t for t in fig.data if t.name == "shelter")
    assert list(shelters.customdata) == ["SH-01", "SH-02", "SH-03", "SH-04"]
    assert list(shelters.marker.color) == ["#e5484d", "#e5484d", "#e5484d", "#fab219"]
    selected = map_figure(e, "SH-02")
    ring = next(t for t in selected.data if t.name == "selected")
    assert (ring.x[0], ring.y[0]) == (find(e, "SH-02")["x"], find(e, "SH-02")["y"])


def test_selecting_a_marker_returns_that_panel(monkeypatch):
    import app
    e = map_entities(sample_dashboard(monkeypatch), load_training_locations())
    selected, panel, fig = app.select_on_map({"points": [{"customdata": "SH-02"}]}, e)
    assert selected == "SH-02" and "Kita Community Center" in text_of(panel)
    assert any(t.name == "selected" for t in fig.data)
