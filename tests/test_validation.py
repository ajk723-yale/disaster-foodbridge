import io
from fractions import Fraction

from src.data_io import load_inventory, load_shelter_reports
from src.validation import validate_inventory, validate_shelter_reports

SHELTER_HEADER = "shelter_id,shelter_name,reported_at,evacuee_count,general_on_hand_meals,special_needs,special_on_hand_meals"
INVENTORY_HEADER = "warehouse_id,item_id,item_name,category,diet_tag,unit,quantity,meals_per_unit,counted_at"


def shelters(rows):
    return validate_shelter_reports(load_shelter_reports(io.StringIO(SHELTER_HEADER + "\n" + rows)))


def inventory(rows):
    return validate_inventory(load_inventory(io.StringIO(INVENTORY_HEADER + "\n" + rows)))


def errors(issues):
    return [i for i in issues if i["severity"] == "error"]


def test_valid_shelter_row_is_parsed():
    df, issues = shelters('S1,North School,2026-10-23T08:00+09:00,10,2.5,"Infant Formula:2; allergy-free:1",infant_formula:3')
    assert errors(issues) == []
    row = df.iloc[0]
    assert row["row_ok"]
    assert row["evacuee_count"] == 10
    assert row["general_on_hand_meals"] == Fraction(5, 2)
    assert row["special_needs"] == {"infant_formula": 2, "allergy_free": 1}
    assert row["special_on_hand_meals"] == {"infant_formula": 3}


def test_optional_columns_may_be_absent():
    csv = "shelter_id,shelter_name,reported_at,evacuee_count,general_on_hand_meals\nS1,A,2026-10-23T08:00+09:00,4,0"
    df, issues = validate_shelter_reports(load_shelter_reports(io.StringIO(csv)))
    assert errors(issues) == [] and df.iloc[0]["special_needs"] == {}


def test_missing_required_column_is_file_error():
    csv = "shelter_id,shelter_name,reported_at\nS1,A,2026-10-23T08:00+09:00"
    df, issues = validate_shelter_reports(load_shelter_reports(io.StringIO(csv)))
    assert df.empty
    assert {i["field"] for i in errors(issues)} == {"evacuee_count", "general_on_hand_meals"}


def test_bad_values_mark_row_not_ok():
    df, issues = shelters(
        "S1,A,2026-10-23T08:00+09:00,-3,0,,\n"
        "S2,B,2026-10-23T08:00+09:00,2.5,0,,\n"
        "S3,C,2026-10-23 08:00,5,0,,\n"          # no timezone
        "S4,D,2026-10-23T08:00+09:00,5,lots,,\n"
        "S5,E,2026-10-23T08:00+09:00,5,0,,"
    )
    assert list(df["row_ok"]) == [False, False, False, False, True]
    assert {i["row"] for i in errors(issues)} == {0, 1, 2, 3}


def test_unknown_special_count_is_warning_not_error():
    df, issues = shelters("S1,A,2026-10-23T08:00+09:00,10,0,halal:?,")
    assert df.iloc[0]["row_ok"]
    assert df.iloc[0]["special_needs"] == {"halal": None}
    assert any(i["severity"] == "warning" and "unknown" in i["message"] for i in issues)


def test_special_people_cannot_exceed_evacuees():
    df, issues = shelters("S1,A,2026-10-23T08:00+09:00,3,0,halal:2; infant_formula:2,")
    assert not df.iloc[0]["row_ok"]
    assert any("exceed" in i["message"] for i in errors(issues))


def test_general_is_not_a_special_tag():
    df, _ = shelters("S1,A,2026-10-23T08:00+09:00,3,0,general:1,")
    assert not df.iloc[0]["row_ok"]


def test_duplicate_report_is_flagged():
    _, issues = shelters("S1,A,2026-10-23T08:00+09:00,3,0,,\nS1,A,2026-10-23T08:00+09:00,4,0,,")
    assert sum("same shelter_id" in i["message"] for i in issues) == 2


def test_inventory_parsing_and_tag_normalization():
    df, issues = inventory("W1,I1,Rice ball,ready_meal,General,pack,40,1,2026-10-23T07:00+09:00\n"
                           "W1,I2,Water,water,general,bottle,100,0,2026-10-23T07:00+09:00")
    assert errors(issues) == []
    assert list(df["diet_tag"]) == ["general", "general"]
    assert df.iloc[0]["quantity"] == 40
    assert any("not counted as food" in i["message"] for i in issues)


def test_inventory_item_with_two_diet_tags_is_error():
    df, issues = inventory("W1,I1,X,meal,general,pack,1,1,2026-10-23T07:00+09:00\n"
                           "W2,I1,X,meal,halal,pack,1,1,2026-10-23T07:00+09:00")
    assert not df["row_ok"].any()
    assert any("more than one diet_tag" in i["message"] for i in errors(issues))
