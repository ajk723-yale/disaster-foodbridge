# Project Spec — Shelter Food Allocation Agent

## Purpose

A web app that helps municipal emergency staff coordinate food distribution to evacuation
shelters after a disaster (e.g., a major earthquake). It turns shelter reports and warehouse
inventory into a daily allocation plan. When supply falls short, it drafts a replenishment
request to the prefectural or national government.

## Users

Municipal emergency operations staff (disaster response headquarters).

## Build status

| Part | Status |
|---|---|
| CSV loading, validation | Done, tested |
| Allocation and rounding | Done, tested |
| Record log, commitments, finalize check | Done, tested |
| AI extraction, request drafting, vision | Not started (stubs only) |
| Dash UI | Not started |

## Core workflow

1. **Ingest data.**
   - Upload shelter reports and warehouse inventory as CSV files.
   - Paste unstructured shelter reports. The AI agent extracts the same fields as the
     shelter CSV.
2. **Validate.**
   - Automatic checks run first.
   - Staff then validate or reject each record. Only validated records are used.
   - AI-extracted records always need staff validation.
3. **Compute need.** Done separately for general meals and for each special diet tag.
4. **Allocate.**
   - General meals: proportional to unmet demand.
   - Special diets: kept separate, and flagged for staff review when stock is short or
     information is missing.
5. **Detect shortage.** Shortages are shown per shelter and per diet tag.
6. **Draft request.** The AI agent drafts a replenishment request to the prefecture or
   national government, based on the computed shortages.
7. **Finalize.**
   - The app recalculates from the latest validated data.
   - If the result changed, staff must confirm the updated plan.
   - Finalizing records approved commitments.
8. **Dispatch.**
   - Commitments are marked `dispatched` when food leaves the warehouse, or `cancelled`
     if it never ships.
9. **(Exploratory) Vision check.** Staff upload warehouse photos, and AI Vision estimates
   stock for comparison with the inventory CSV. Differences are shown to staff only; they
   never change the inventory on their own.

## Data formats

The number of rows is unlimited, and no quantities are in code. Header-only templates are in
`data/templates/`. Timestamps must include a timezone offset (e.g., `2026-10-23T08:00+09:00`).
Diet tags are normalized (`Allergy-Free` → `allergy_free`). `general` is the reserved tag for
compatible general meals.

### Shelter report CSV

| Field | Required | Meaning |
|---|---|---|
| `shelter_id`, `shelter_name` | yes | Stable ID and display name |
| `reported_at` | yes | When the shelter observed these numbers |
| `evacuee_count` | yes | Whole number ≥ 0 |
| `general_on_hand_meals` | yes | General meals at the shelter |
| `special_needs` | no | `tag:people; …` e.g. `infant_formula:4; halal:2`. Use `?` when the count is unknown |
| `special_on_hand_meals` | no | `tag:meals; …` |
| `reporter`, `notes` | no | Free text |

People listed under `special_needs` are excluded from the general headcount.

### Warehouse inventory CSV

| Field | Required | Meaning |
|---|---|---|
| `warehouse_id`, `item_id`, `item_name` | yes | IDs and display name |
| `category` | no | Descriptive (e.g., `ready_meal`, `rice`, `water`) |
| `diet_tag` | yes | `general` or a special tag. Only matching tags are allocated together |
| `unit`, `quantity` | yes | Counting unit and stock |
| `meals_per_unit` | yes | Conversion to meals (0 = not food, e.g., water) |
| `counted_at` | yes | When the stock was counted |
| `expiry_date`, `notes` | no | |

### Validation rules

**Errors** (the record cannot be validated):
- a required column or value is missing
- a value is not a number, or is negative
- `evacuee_count` is not a whole number
- a timestamp has no timezone
- a `tag:value` entry is malformed
- `general` is used as a special tag
- special-needs people exceed `evacuee_count`
- one `item_id` has two diet tags

**Warnings:**
- a special-needs count is unknown (`?`)
- the same report is duplicated
- one `shelter_id` has two names
- special stock is reported with no matching need
- an item has `meals_per_unit` of 0
- an item had expired when counted

### Configurable defaults

| Setting | Default |
|---|---|
| `MEALS_PER_PERSON_PER_DAY` | 3 |
| `PLANNING_WINDOW_HOURS` | 24 |
| `MODEL` | `gpt-6-luna` |

All are set by environment variable, and later in the UI.

## Calculation rules

All values are in meals. Internally the math uses exact fractions; results are whole meals.

- **Need:** `ceil(people × meals_per_person_per_day × planning_window_hours / 24)`. Rounded
  up so no shelter is under-planned.
- **Unmet:** `ceil(max(0, need − on_hand − incoming))`. `incoming` is food committed to that
  shelter after its latest report.
- **Available:** `floor(Σ quantity × meals_per_unit − committed)` per diet tag. Rounded down
  so the app never promises food that isn't there.
- **General meals:**
  - If supply covers everyone, each shelter gets its full unmet demand.
  - Otherwise the app uses the **largest-remainder method**: each shelter gets the floor of
    `available × unmet / Σ unmet`, and leftover meals go one at a time to the largest
    remainders.
  - Ties go to the larger unmet demand, then to the lower `shelter_id`.
  - The result is the same for the same input, regardless of row order, and never exceeds
    any shelter's demand.
- **Special diet tags:** each tag is assessed on its own and is never mixed with general
  stock.
  - `ok`: every need is known and fully covered. Each shelter's full unmet amount is
    suggested.
  - `shortage` or `no_stock`: not enough stock. Nothing is split automatically, and staff
    are flagged to decide.
  - `missing_info`: some counts are unknown (`?`). Flagged for staff review; general need
    for that shelter may be overstated.

## Update recording and latest validated data

**Append-only record log.**
- Each upload, extraction, or correction is a new record with:
  - `record_id`
  - `source` (`csv`, `ai_extraction`, `manual_edit`)
  - `received_at`
  - `status` (`pending` → `validated` or `rejected`)
  - `validated_by`, `validated_at`
  - `supersedes`
  - `source_text`
- Validated and rejected records are final.
- A correction is a new record that `supersedes` the old one. It takes effect once it is
  validated.

**Latest validated:**
- Shelters: per `shelter_id`, the validated, non-superseded record with the latest
  `reported_at`.
- Inventory: the same rule per (`warehouse_id`, `item_id`), using `counted_at`.
- Ties go to the latest `received_at`, then `record_id`.

**Commitments** (stops dispatched food from being counted twice):
- One line per finalized (plan, shelter, diet tag): `approved` → `dispatched`, or
  `cancelled` (only while still approved).
- Approved and dispatched lines are subtracted from a tag's stock if they were made after
  that tag's earliest count. A full recount after dispatch replaces the deduction.
- A warning appears if counts of a tag straddle a commitment (some items recounted, some
  not), recommending a recount.
- The same commitments count as `incoming` for a shelter until it sends a newer report.

**Finalization.**
1. Staff review a plan, which carries a fingerprint: a hash of the config, the input
   record IDs, the commitment IDs, and every allocation line.
2. On Finalize, the app recalculates from the latest validated data.
3. If the fingerprint differs, it returns the updated plan with `needs_confirmation`.
   Staff must review that plan and finalize again.
4. If the fingerprint matches, it saves a snapshot (plan ID, staff, time, input record IDs,
   config, allocation, shortages, flags, warnings) and records approved commitments.
5. Warnings are shown if a newer pending report or count exists.

## Decisions made so far

- **Data input:** CSV for shelters and inventory, plus AI extraction from unstructured
  reports.
- **Human validation:** AI-extracted values must be validated by staff before use.
- **Food compatibility:** food is not interchangeable. Only `general` meals are pooled and
  split proportionally. Special diets stay separate and are flagged when short or unclear.
- **Deterministic rounding:** need is rounded up, stock is rounded down, and splits use
  largest remainder with a fixed tie-break.
- **No double-counting:** approved and dispatched commitments are tracked and deducted
  from available stock.
- **Finalization:** recalculate from the latest validated data. Any change requires staff
  confirmation. A finalized plan is saved as an immutable snapshot.
- **No hardcoded data:** shelter counts and quantities always come from data. 3 meals per
  day and a 24-hour window are configurable defaults. Test datasets live only in `tests/`.
- **Humans decide:** the AI extracts, drafts, and explains. Staff validate, decide special
  shortages, and finalize.
- **AI provider:** OpenAI `gpt-6-luna` via Portkey, with the key from `PORTKEY_API_KEY` in
  `.env`, which is never committed.
- **UI:** Dash, black-and-pink theme.

## Open for discussion

1. **Per-tag meal rates:** special diets use the same meals-per-person rate. Should some
   tags (e.g., infant formula feedings) have their own configurable rate?
2. **Overlapping needs:** one person per tag is assumed. What about someone who is both
   halal and allergy-free?
3. **Whole units:** allocation is in whole meals, not packs or cases. Should it convert to
   physical units when dispatching, and which warehouse ships what?
4. **Special shortages:** should staff get a suggested split (e.g., by medical priority),
   or always decide manually?
5. **Staleness:** how old a validated report can be before Finalize warns.
6. **Multiple warehouses:** stock is pooled across warehouses for now. Should transport or
   location limit this?
7. **Commitment deduction:** it uses the earliest count of a tag (conservative). Should it
   be per item instead, once dispatch picks specific items?
8. **Request format:** fields and template for prefectural/national requests (Japanese,
   English, or both).
9. **Persistence:** keep logs and snapshots in CSV/JSON files or in SQLite.
10. **Vision scope:** counting vs. gap flagging, whether `gpt-6-luna` accepts images via
    Portkey, and what tolerance makes a gap worth flagging.
11. **Agent design:** a simple pipeline, or tool-calling that uses these functions as tools.
12. **Access control:** single user or several staff roles.
