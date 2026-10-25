"""prepare_supply_request: request facts from the calculate_allocation draft. Small test data only."""
from src import agent_tools, config
from tests.test_allocation_tool import SHELTERS, V, draft, logs

RICE_60 = f"x,{V},W1,I1,Rice,meal,general,pack,60,1,2026-01-01T05:00+09:00\n"


def request(tmp_path, shelters, inventory, commitments=""):
    allocation, _ = draft(tmp_path, shelters, inventory, commitments)
    return agent_tools.supply_request_from_allocation(allocation), allocation


def test_request_uses_allocation_shortage_and_placeholders(tmp_path):
    req, allocation = request(tmp_path, SHELTERS, RICE_60)
    assert req["status"].startswith("DRAFT") and "Not sent" in req["status"]
    g = req["general_meals"]
    assert (g["total_unmet_meals"], g["available_meals"], g["additional_meals_to_request"]) == (120, 60, 60)
    assert g["additional_meals_to_request"] == allocation["general_meals"]["shortage_meals"]
    assert [s["shortfall_meals"] for s in g["shortfall_by_shelter_after_plan_a"]] == [15, 45]
    assert req["planning_period"] == {"window_hours": 24, "meals_per_person_per_day": 3,
                                      "start": "[PLANNING PERIOD START DATE/TIME]"}
    for key in ("municipality", "recipient", "delivery_location", "delivery_deadline", "contact"):
        assert req["placeholders"][key].startswith("[") and req["placeholders"][key].endswith("]")
    assert req["allocation_plan_fingerprint"] == allocation["plan_fingerprint"]
    assert "note" not in req


def test_special_diet_requirements_and_unknown_counts(tmp_path):
    shelters = (f"a,{V},S1,One,2026-01-01T06:00+09:00,10,0,\"infant_formula:2; halal:?\",\n"
                f"b,{V},S2,Two,2026-01-01T06:00+09:00,10,0,infant_formula:2; allergy_free:1,\n")
    inventory = (f"x,{V},W1,I1,Rice,meal,general,pack,1000,1,2026-01-01T05:00+09:00\n"
                 f"y,{V},W1,I2,Formula,f,infant_formula,pack,7,1,2026-01-01T05:00+09:00\n"
                 f"z,{V},W1,I3,AF meal,meal,allergy_free,pack,9,1,2026-01-01T05:00+09:00\n")
    req, _ = request(tmp_path, shelters, inventory)
    special = {s["diet_category"]: s for s in req["special_diet_requirements"]}
    assert special["infant_formula"]["additional_meals_to_request"] == 5
    assert special["allergy_free"]["additional_meals_to_request"] == 0
    assert str(special["halal"]["additional_meals_to_request"]).startswith("to be confirmed")
    assert special["halal"]["shelters"][0]["people"] == "unknown"
    assert req["general_meals"]["additional_meals_to_request"] == 0
    assert any("halal" in w for w in req["pending_or_uncertain_data"])
    assert "note" not in req      # halal still needs confirming, so a request may be needed


def test_nothing_needed(tmp_path):
    req, _ = request(tmp_path, SHELTERS, f"x,{V},W1,I1,Rice,meal,general,pack,500,1,2026-01-01T05:00+09:00\n")
    assert req["note"] == "No additional supplies are needed based on current validated data."


def test_no_validated_data(tmp_path):
    req, _ = request(tmp_path, "", RICE_60)
    assert "cannot be drafted" in req["note"]


def test_tool_is_read_only(tmp_path, monkeypatch):
    logs(tmp_path, SHELTERS, RICE_60, "c1,P,S1,general,5,approved,2026-01-01T06:30+09:00,,,\n")
    files = {name: (tmp_path / f"{name}.csv") for name in ("s", "i", "c")}
    before = {name: path.read_bytes() for name, path in files.items()}
    monkeypatch.setattr(config, "SHELTER_LOG_PATH", str(files["s"]))
    monkeypatch.setattr(config, "INVENTORY_LOG_PATH", str(files["i"]))
    monkeypatch.setattr(config, "COMMITMENTS_LOG_PATH", str(files["c"]))
    req = agent_tools.prepare_supply_request()
    assert req["general_meals"]["additional_meals_to_request"] == 60 + 5 - 5   # 5 approved: reserved and incoming
    assert {name: path.read_bytes() for name, path in files.items()} == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["c.csv", "i.csv", "s.csv"]
