"""Column definitions and parsers shared by loading, validation, and allocation."""

GENERAL_TAG = "general"  # the only diet tag pooled for proportional allocation
UNKNOWN_COUNT = "?"      # placeholder for a special-needs count staff still need to confirm

SHELTER_COLUMNS = [
    "shelter_id",
    "shelter_name",
    "reported_at",
    "evacuee_count",
    "general_on_hand_meals",
    "special_needs",
    "special_on_hand_meals",
    "reporter",
    "notes",
]
SHELTER_REQUIRED = ["shelter_id", "shelter_name", "reported_at", "evacuee_count", "general_on_hand_meals"]

INVENTORY_COLUMNS = [
    "warehouse_id",
    "item_id",
    "item_name",
    "category",
    "diet_tag",
    "unit",
    "quantity",
    "meals_per_unit",
    "counted_at",
    "expiry_date",
    "notes",
]
INVENTORY_REQUIRED = [
    "warehouse_id", "item_id", "item_name", "diet_tag", "unit", "quantity", "meals_per_unit", "counted_at",
]

# Metadata added to every row in the append-only record log
RECORD_META_COLUMNS = [
    "record_id", "source", "received_at", "status", "validated_by", "validated_at", "supersedes", "source_text",
]


def normalize_tag(tag):
    return tag.strip().lower().replace(" ", "_").replace("-", "_")


def parse_tag_values(text):
    """Parse 'tag:value; tag:value' into {tag: value_string}.

    Returns (values, errors). Values stay as strings so callers decide how to
    interpret them (e.g. UNKNOWN_COUNT). Repeated tags are reported as errors.
    """
    values, errors = {}, []
    if text is None or not str(text).strip():
        return values, errors
    for part in str(text).split(";"):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            errors.append(f"'{part}' is not in tag:value form")
            continue
        tag, value = part.split(":", 1)
        tag = normalize_tag(tag)
        if not tag:
            errors.append(f"'{part}' has an empty tag")
            continue
        if tag in values:
            errors.append(f"tag '{tag}' appears more than once")
            continue
        values[tag] = value.strip()
    return values, errors
