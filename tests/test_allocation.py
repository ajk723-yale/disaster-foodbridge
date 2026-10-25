import itertools

from src.allocation import allocate_proportionally, build_allocation, meals_needed

CONFIG = {"meals_per_person_per_day": 3, "planning_window_hours": 24}


def shelter(sid, people, on_hand=0, special=None, special_stock=None):
    return {"shelter_id": sid, "shelter_name": sid, "evacuee_count": people, "general_on_hand_meals": on_hand,
            "special_needs": special or {}, "special_on_hand_meals": special_stock or {}}


def test_meals_needed_uses_configurable_defaults():
    assert meals_needed(10, 3, 24) == 30
    assert meals_needed(10, 3, 12) == 15
    assert meals_needed(7, 3, 8) == 7       # exactly 7
    assert meals_needed(5, 2.5, 24) == 13   # 12.5 rounds up
    assert meals_needed(0, 3, 24) == 0


def test_full_coverage_when_supply_is_enough():
    assert allocate_proportionally({"A": 10, "B": 5}, 100) == {"A": 10, "B": 5}


def test_proportional_split_with_largest_remainder():
    # quotas 10*{1,1,1}/3 = 3.33 each; one leftover goes to the smallest id on a full tie
    assert allocate_proportionally({"A": 1, "B": 1, "C": 1}, 2) == {"A": 1, "B": 1, "C": 0}
    result = allocate_proportionally({"A": 50, "B": 30, "C": 20}, 10)
    assert result == {"A": 5, "B": 3, "C": 2}
    result = allocate_proportionally({"A": 7, "B": 5, "C": 1}, 6)  # quotas 3.23, 2.31, 0.46
    assert result == {"A": 3, "B": 2, "C": 1}


def test_split_is_exact_bounded_and_order_independent():
    demands = {"S3": 13, "S1": 7, "S2": 29, "S4": 0}
    base = allocate_proportionally(demands, 31)
    assert sum(base.values()) == 31
    assert all(0 <= base[k] <= demands[k] for k in demands)
    for perm in itertools.permutations(demands):
        assert allocate_proportionally({k: demands[k] for k in perm}, 31) == base


def test_zero_and_fractional_supply():
    assert allocate_proportionally({"A": 4, "B": 4}, 0) == {"A": 0, "B": 0}
    assert sum(allocate_proportionally({"A": 4, "B": 4}, 5.9).values()) == 5   # floor available
    assert allocate_proportionally({}, 10) == {}


def test_general_need_excludes_special_diet_people_and_on_hand():
    result = build_allocation([shelter("S1", 10, on_hand=6, special={"halal": 2})], {"general": 100}, {}, CONFIG)
    line = result["general"]["lines"][0]
    assert (line["people"], line["need_meals"], line["unmet_meals"], line["allocated_meals"]) == (8, 24, 18, 18)


def test_general_shortage_is_proportional_and_reported():
    shelters = [shelter("S1", 10), shelter("S2", 30)]       # unmet 30 and 90
    result = build_allocation(shelters, {"general": 60}, {}, CONFIG)
    g = result["general"]
    assert [l["allocated_meals"] for l in g["lines"]] == [15, 45]
    assert [l["shortfall_meals"] for l in g["lines"]] == [15, 45]
    assert g["shortage_meals"] == 60


def test_special_stock_is_never_pooled_into_general():
    result = build_allocation([shelter("S1", 10)], {"general": 0, "halal": 500}, {}, CONFIG)
    assert result["general"]["allocated_meals"] == 0
    assert result["general"]["shortage_meals"] == 30


def test_special_tag_fully_covered_is_suggested():
    s = [shelter("S1", 10, special={"halal": 2}, special_stock={"halal": 1}), shelter("S2", 5, special={"halal": 1})]
    result = build_allocation(s, {"general": 100, "halal": 20}, {}, CONFIG)
    halal = result["special"][0]
    assert halal["status"] == "ok"
    assert [l["suggested_meals"] for l in halal["lines"]] == [5, 3]


def test_special_shortage_is_flagged_not_split():
    s = [shelter("S1", 10, special={"infant_formula": 2}), shelter("S2", 5, special={"infant_formula": 2})]
    result = build_allocation(s, {"infant_formula": 7}, {}, CONFIG)
    tag = result["special"][0]
    assert tag["status"] == "shortage" and tag["shortage_meals"] == 5
    assert all(l["suggested_meals"] is None for l in tag["lines"])
    assert any(f["severity"] == "review" and f["diet_tag"] == "infant_formula" for f in result["flags"])


def test_special_need_without_any_stock():
    result = build_allocation([shelter("S1", 4, special={"allergy_free": 1})], {}, {}, CONFIG)
    assert result["special"][0]["status"] == "no_stock"


def test_unknown_special_count_needs_review():
    s = [shelter("S1", 10, special={"halal": None}), shelter("S2", 5, special={"halal": 1})]
    result = build_allocation(s, {"halal": 100}, {}, CONFIG)
    tag = result["special"][0]
    assert tag["status"] == "missing_info"
    assert all(l["suggested_meals"] is None for l in tag["lines"])
    assert any(f["shelter_id"] == "S1" and f["diet_tag"] == "general" for f in result["flags"])


def test_incoming_food_reduces_unmet():
    result = build_allocation([shelter("S1", 10)], {"general": 100}, {("S1", "general"): 12}, CONFIG)
    assert result["general"]["lines"][0]["unmet_meals"] == 18
