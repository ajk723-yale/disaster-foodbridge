"""Schema, type, missing-value, duplicate, and consistency checks.

Each validator returns (clean_df, issues):
- clean_df keeps every input row, with parsed values and a `row_ok` flag
  (False when the row has at least one error).
- issues is a list of dicts: severity ("error" | "warning"), row, field, message.
  Rows are 0-based positions in the uploaded file; file-level issues use row=None.

Numbers are parsed to fractions.Fraction so later calculations are exact.
"""
from fractions import Fraction

import pandas as pd

from src.schemas import (
    GENERAL_TAG,
    INVENTORY_REQUIRED,
    SHELTER_REQUIRED,
    UNKNOWN_COUNT,
    normalize_tag,
    parse_tag_values,
)


def _issue(issues, severity, row, field, message):
    issues.append({"severity": severity, "row": row, "field": field, "message": message})


def _parse_number(value):
    try:
        number = Fraction(str(value))
    except (ValueError, ZeroDivisionError):
        return None
    return number


def _parse_timestamp(value):
    """Return (timestamp, error_message)."""
    try:
        ts = pd.Timestamp(value)
    except (ValueError, TypeError):
        return None, f"'{value}' is not a valid date/time"
    if ts is pd.NaT:
        return None, f"'{value}' is not a valid date/time"
    if ts.tzinfo is None:
        return None, f"'{value}' has no timezone offset (e.g. +09:00)"
    return ts, None


def _check_columns(df, required, issues):
    missing = [c for c in required if c not in df.columns]
    for col in missing:
        _issue(issues, "error", None, col, f"required column '{col}' is missing")
    return not missing


def _non_negative(issues, i, field, raw, integer=False):
    number = _parse_number(raw)
    if number is None:
        _issue(issues, "error", i, field, f"'{raw}' is not a number")
        return None
    if number < 0:
        _issue(issues, "error", i, field, f"{raw} is negative")
        return None
    if integer and number.denominator != 1:
        _issue(issues, "error", i, field, f"{raw} must be a whole number")
        return None
    return int(number) if integer else number


def validate_shelter_reports(df):
    issues = []
    df = df.copy()
    if not _check_columns(df, SHELTER_REQUIRED, issues):
        return df.iloc[0:0], issues

    parsed = {"reported_at": [], "evacuee_count": [], "general_on_hand_meals": [],
              "special_needs": [], "special_on_hand_meals": [], "row_ok": []}
    for i, row in enumerate(df.to_dict("records")):
        n_errors = len([x for x in issues if x["severity"] == "error"])

        for col in SHELTER_REQUIRED:
            if not row[col]:
                _issue(issues, "error", i, col, "required value is empty")

        reported_at = None
        if row["reported_at"]:
            reported_at, err = _parse_timestamp(row["reported_at"])
            if err:
                _issue(issues, "error", i, "reported_at", err)

        count = _non_negative(issues, i, "evacuee_count", row["evacuee_count"], integer=True) \
            if row["evacuee_count"] else None
        on_hand = _non_negative(issues, i, "general_on_hand_meals", row["general_on_hand_meals"]) \
            if row["general_on_hand_meals"] else None

        # special_needs: tag:people, where people may be UNKNOWN_COUNT pending confirmation
        needs, errs = parse_tag_values(row.get("special_needs", ""))
        for e in errs:
            _issue(issues, "error", i, "special_needs", e)
        special = {}
        for tag, value in needs.items():
            if tag == GENERAL_TAG:
                _issue(issues, "error", i, "special_needs", f"'{GENERAL_TAG}' is not a special diet tag")
            elif value == UNKNOWN_COUNT or value == "":
                special[tag] = None
                _issue(issues, "warning", i, "special_needs",
                       f"number of people needing '{tag}' is unknown; staff should confirm")
            else:
                people = _non_negative(issues, i, "special_needs", value, integer=True)
                if people is not None:
                    special[tag] = people
        known = sum(v for v in special.values() if v is not None)
        if count is not None and known > count:
            _issue(issues, "error", i, "special_needs",
                   f"special-needs people ({known}) exceed evacuee_count ({count})")

        stock, errs = parse_tag_values(row.get("special_on_hand_meals", ""))
        for e in errs:
            _issue(issues, "error", i, "special_on_hand_meals", e)
        special_stock = {}
        for tag, value in stock.items():
            meals = _non_negative(issues, i, "special_on_hand_meals", value)
            if meals is not None:
                special_stock[tag] = meals
            if tag not in special:
                _issue(issues, "warning", i, "special_on_hand_meals",
                       f"stock reported for '{tag}' but no people listed with that need")

        parsed["reported_at"].append(reported_at)
        parsed["evacuee_count"].append(count)
        parsed["general_on_hand_meals"].append(on_hand)
        parsed["special_needs"].append(special)
        parsed["special_on_hand_meals"].append(special_stock)
        parsed["row_ok"].append(len([x for x in issues if x["severity"] == "error"]) == n_errors)

    for col, values in parsed.items():
        df[col] = pd.Series(values, index=df.index, dtype=object)

    dup = df[df["reported_at"].notna()].duplicated(["shelter_id", "reported_at"], keep=False)
    for i in [df.index.get_loc(ix) for ix in dup[dup].index]:
        _issue(issues, "warning", i, "reported_at", "another row has the same shelter_id and reported_at")
    names = df.groupby("shelter_id")["shelter_name"].nunique()
    for sid in names[names > 1].index:
        _issue(issues, "warning", None, "shelter_name", f"shelter_id '{sid}' has more than one shelter_name")
    return df, issues


def validate_inventory(df):
    issues = []
    df = df.copy()
    if not _check_columns(df, INVENTORY_REQUIRED, issues):
        return df.iloc[0:0], issues

    parsed = {"diet_tag": [], "quantity": [], "meals_per_unit": [], "counted_at": [],
              "expiry_date": [], "row_ok": []}
    for i, row in enumerate(df.to_dict("records")):
        n_errors = len([x for x in issues if x["severity"] == "error"])

        for col in INVENTORY_REQUIRED:
            if not row[col]:
                _issue(issues, "error", i, col, "required value is empty")

        quantity = _non_negative(issues, i, "quantity", row["quantity"]) if row["quantity"] else None
        per_unit = _non_negative(issues, i, "meals_per_unit", row["meals_per_unit"]) \
            if row["meals_per_unit"] else None
        if per_unit == 0:
            _issue(issues, "warning", i, "meals_per_unit", "meals_per_unit is 0, so this item is not counted as food")

        counted_at = None
        if row["counted_at"]:
            counted_at, err = _parse_timestamp(row["counted_at"])
            if err:
                _issue(issues, "error", i, "counted_at", err)

        expiry = None
        if row.get("expiry_date"):
            try:
                expiry = pd.Timestamp(row["expiry_date"]).date()
            except (ValueError, TypeError):
                _issue(issues, "error", i, "expiry_date", f"'{row['expiry_date']}' is not a valid date")
            if expiry is not None and counted_at is not None and expiry < counted_at.date():
                _issue(issues, "warning", i, "expiry_date", "item had already expired when counted")

        parsed["diet_tag"].append(normalize_tag(row["diet_tag"]) if row["diet_tag"] else "")
        parsed["quantity"].append(quantity)
        parsed["meals_per_unit"].append(per_unit)
        parsed["counted_at"].append(counted_at)
        parsed["expiry_date"].append(expiry)
        parsed["row_ok"].append(len([x for x in issues if x["severity"] == "error"]) == n_errors)

    for col, values in parsed.items():
        df[col] = pd.Series(values, index=df.index, dtype=object)

    dup = df[df["counted_at"].notna()].duplicated(["warehouse_id", "item_id", "counted_at"], keep=False)
    for i in [df.index.get_loc(ix) for ix in dup[dup].index]:
        _issue(issues, "warning", i, "counted_at", "another row has the same warehouse_id, item_id and counted_at")
    tags = df.groupby("item_id")["diet_tag"].nunique()
    for item in tags[tags > 1].index:
        _issue(issues, "error", None, "diet_tag", f"item_id '{item}' has more than one diet_tag")
        df.loc[df["item_id"] == item, "row_ok"] = False
    return df, issues
