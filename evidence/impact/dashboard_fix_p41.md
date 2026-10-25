# P41: Dashboard defects F1 and F2: reproduction, fix, re-test (2026-10-24)

The defects were found by the P40 impact evaluation (`impact_eval_report.md`). Only the dashboard display code
changed: `src/dashboard.py` (action list) and `src/dashboard_view.py` (special-diet table). No change was made to
allocation calculations, agent behavior, approval or finalization logic, or the overall layout.

## Evidence files

| File | Content |
|---|---|
| `dashboard_defects_before.json` | 6 reproduction scenarios run on the **old** code (`scripts/impact_eval/reproduce_dashboard_defects.py before`) |
| `dashboard_defects_after.json` | The same 6 scenarios after the fix |
| `cases/D1`–`D6` | Isolated data for each scenario. `D7_browser_R3_state` is the isolated copy used for the browser check |
| `regression_tests_against_old_code.txt` | The 4 new regression tests run against the old code: **4 failed** (expected) |
| `impact_eval_results_p41_rerun_after_fix.json` | The P40 evaluation re-run after the fix. `impact_eval_results.json` is the unchanged P40 result |
| Screenshots S31–S34 (`evidence/screenshots/`) | Browser before/after on the isolated R3 state (port 8051) |

## Reproduction (old code) vs after the fix

| Scenario | Before | After |
|---|---|---|
| F1: P40 R3 state (halal 5 people, 0 halal stock) | **crash** `KeyError: 'other_note'` | builds. "⛔ Not enough halal meals: 15 short" (red, first); the data note is shown with its text |
| F1: P40 R7 state (no validated inventory) | **crash** | builds. Allergy-free 6 and infant formula 1 shown as shortages; one "No validated stock count for …" item per inventory item; 4 data notes; all 16 warnings listed |
| F1: 3 unexpected warning types injected (unknown warehouse WH-Z, unknown plan, no ID) | **crash** | builds. Each shown as "Data note: <warning text>"; the WH-Z note is tied to WH-Z on the map |
| F2: halal need 15, 0 in stock (one unmatched warning, so F1 did not hide it) | builds, but the table read "Halal 15 0 **Enough in stock**", and the shortage appeared only as a generic note | "Halal 15 0 **⛔ 15 short (none in stock)**" plus a red shortage action (why: "None in stock for 15 needed") |
| F2: unknown halal count | table read "Halal **0** 0 ⚠️ count unknown" (unknown shown as 0) | "Halal **unknown** 0 ⚠️ count unknown" |
| F2: confirmed zero demand (formula fully covered) | "Infant formula 0 16 Enough in stock" | "Infant formula 0 16 **No unmet need**" (distinct from unknown) |

## The fixes

- **F1.** When deciding whether a warning is already covered by a specific action, the code now uses
  `covered_markers.get(kind)`. Generic "Data note" items have no marker and can never cover a warning, so a second
  unmatched warning no longer raises `KeyError`. Warnings are converted to text before matching.
- **F1 label.** A data note's visible title is now "Data note: <the warning text>". Before, the compact list showed
  only "Data note", and the text was visible only in a tooltip.
- **F2.** `SHORTAGE_STATUSES = ("shortage", "no_stock")`:
  - both statuses create the red special-diet shortage action, and its explanation says "None in stock" when the
    stock is 0;
  - the special-diet table shows "N short (none in stock)";
  - unknown demand shows "unknown" (or "N + unknown");
  - confirmed zero demand shows "No unmet need";
  - a status the view does not recognize is shown as written in amber, never as "Enough in stock".
- **Accuracy of related labels** (found while re-testing R7):
  - an inventory item with no validated count at all was described as "Available meals use the earlier count from an
    earlier time". It is now titled "No validated stock count for <item> at <warehouse>", with "not included in
    available meals until a count is validated";
  - items with several waiting counts produced one action per count. There is now one action per item.

## Re-test

- **Affected reliability cases (P40 runner re-run):** R3 9/0/1 and R7 6/0/0 (pass/fail/exploratory), including
  "dashboard builds" and "lists a special-diet shortage". **Totals: 48 passed, 0 failed, 4 exploratory** (P40: 45 /
  3 / 4).
- **Accuracy:** unchanged, 6/6 cases and 313 fields; the calculations were not touched.
- **Isolation:** `data/live/` and `data/sample/` unchanged.
- **Tests:** 4 new regression tests in `tests/test_dashboard.py`, and 2 existing assertions updated for the new
  data-note title. Full suite: **218 passed**.
- **Browser (isolated R3 copy on port 8051):**
  - before (old code still loaded in the server): "Dashboard could not be built: KeyError: 'other_note'" and an empty
    map (S31);
  - after: figures 596 / 988 / 392; the halal shortage first in red; the data note with its text (S32); the
    special-diet table with "15 short (none in stock)" (S33); the SH-03 map panel listing the halal shortage and the
    data note (S34);
  - no console or server errors.
- **Main app (port 8050, working data = sample):** renders without error; halal now reads "unknown" instead of "0".
