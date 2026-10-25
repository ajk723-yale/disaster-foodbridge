# P40 Impact evaluation: accuracy, reliability, efficiency (2026-10-24)

- **Runner:** `scripts/run_impact_eval.py` (`--extraction` adds the real model calls)
- **Independent expected results:** `scripts/impact_eval/expected.py`, written from the documented rules and
  importing nothing from `src/`
- **Raw results:** `impact_eval_results.json` (final run) and `impact_eval_results_run1.json` (first run, before the
  evaluation's own errors were corrected)
- **Per-case inputs and outputs:** `cases/<case>/`, which holds the CSV copies, any records appended by the case,
  and the case's own finalization database
- **Model usage for the extraction timings:** `usage_log_impact.jsonl`

**All data is synthetic** (the repository's sample data and small made-up variants). Nothing here measures
real-world impact or staff productivity.

## Isolation

Every case ran on its own copies under `evidence/impact/cases/`, with the app's paths pointed there.

| Check | Result |
|---|---|
| `data/live/` (4 files) hashes before = after | ✅ unchanged |
| `data/sample/` (5 files) hashes before = after | ✅ unchanged |
| Live finalization database (`data/live/finalization.db`) | did not exist before or after; finalized plans were stored only in the case databases |
| Application code | not modified |

## 1. Accuracy: app vs independently calculated expected results

The oracle and the app read the same isolated CSVs. Every field the oracle computes is compared:
- per shelter and diet: people, need, on hand, on its way, delivered after report, unmet;
- per diet: counted stock, dispatched since count, reserved, available;
- Plan A per shelter, shortfall, total, and procurement;
- special-diet status, Plan A, and procurement.

| Case | Situation tested | Fields compared | Result | Key figures (expected = actual) |
|---|---|---|---|---|
| A1 | Sample data as provided: two warehouses, a recount that already reflects a dispatch, a delivery after the report, a reserved approval, a cancelled approval, rejected and pending records | 73 | ✅ all match | available 596; unmet 1,003; Plan A 206 / 39 / 351; procurement 407; halal unknown |
| A2 | Sample + a newer WH-B count of 600 (stock exceeds demand) | 73 | ✅ | available 1,076; Plan A = unmet (347 / 66 / 590); procurement 0 |
| A3 | Three equal shelters, 10 meals: tie-break | 32 | ✅ | 4 / 3 / 3 (tie broken by shelter_id); procurement 80 |
| A4 | Infant formula needed 24, 10 in stock | 46 | ✅ | formula status shortage; procurement 14; no Plan A lines for formula |
| A5 | 0.5 meals per pack (stock 13.5); a delivery before vs after the report | 16 | ✅ | stock 13.5 shown, 13 planned; unmet 19 (the 2-meal late delivery counts, the earlier 5 do not); procurement 6 |
| A6 | Sample with a 12-hour planning window | 73 | ✅ | unmet 424; Plan A 149 / 0 / 275; procurement 0 |

**Accuracy result: 6 of 6 cases, 313 fields, 0 mismatches** (final run).

**The evaluation's own errors (run 1), corrected and disclosed.** The first run reported mismatches that came from the
evaluation, not the app:
- A5: the oracle subtracted deliveries from a warehouse ("W0") that has no validated count, so there is no counted
  stock to subtract from. It also rounded the inventory's meal equivalents down, although the documented rounding
  applies only to planning; the app's plan does use 13.
- R7: the oracle listed stock categories with zero counts, which the app's inventory summary omits. These are now
  skipped only when nothing is counted.
- Special-diet status vocabulary: the app reports `no_stock` when stock is 0; the oracle has a single "shortage"
  status. They are compared as equivalent, and the app's value is recorded.

## 2. Reliability

| Case | Situation | Checks passed / failed / exploratory | Outcome |
|---|---|---|---|
| R1 | SH-04 has only a pending report | 5 / 0 / 0 | Excluded from needs and Plan A; listed as without a validated report; warning and dashboard action "missing report" |
| R2 | SH-02 has a newer pending report (80 people); staff then approve an 80-person report through the normal intake function | 8 / 0 / 1 | Before: uses the validated 64-person report and warns. After: needs match the oracle (unmet 240 − 90 − 30 = 120), fingerprint changes, and the pending warning is gone. A new, correct warning appears: the 08:45 dispatch left before the new 11:00 report and is not confirmed delivered, so it may be counted twice |
| R3 | SH-03 halal count unknown; then a validated report states halal 5 | **7 / 2 / 1** | Before: halal "missing_info", procurement "unknown" (not 0), no halal Plan A, and general need from all 210 people flagged as possibly overstated. After: matches the oracle (halal 15 needed, 0 in stock, procurement 15; app status `no_stock`). **The dashboard fails to build** (see F1) |
| R4 | A validated SH-01 report arrives after staff reviewed the plan; then finalization in the case database | 9 / 0 / 0 | Stale review → `needs_confirmation`, nothing stored; fresh plan uses 147 general people; unacknowledged warnings → `acknowledgement_required`; with acknowledgements → `finalized`; repeat → `already_finalized`; afterwards the new approvals are counted as reserved and on their way (matches the oracle); the dashboard builds |
| R5 | Rejected typos (2,100 people; 3,000 rice) and a pending bread recount | 8 / 0 / 0 | Ignored; the pending recount is flagged; the dashboard builds with its 4 expected actions |
| R6 | Staff approve a report with evacuee count "abc" | 2 / 0 / 0 | Rejected as invalid; shelter log unchanged |
| R7 | No validated inventory at all | **5 / 1 / 0** | Available 0, Plan A 0, procurement = total unmet (1,003), matches the oracle, and a "no validated counts" note is shown. **The dashboard fails to build** (see F1) |
| R8 | Exploratory: bread recounted at 12:00, rice last counted at 06:30, a general dispatch left WH-A at 11:00 | 1 / 0 / 2 | The documented rule does not say whether a recount of one item reflects a dispatch whose item is unknown. **The app subtracts the dispatch (available 500, the conservative reading)**; the other reading gives 540. Not scored |

**Reliability result: 45 checks passed, 3 failed, 4 exploratory or observation-only.** All 3 failures are F1.

### Failures found

- **F1 (executed, reproducible): the dashboard crashes when two or more data warnings have no matching specific
  action.**
  - **Cause:** in `src/dashboard.py` `_actions`, after the first unmatched warning becomes a "Data note"
    (`other_note`), the next warning looks up `covered_markers["other_note"]`, which does not exist, and raises
    `KeyError: 'other_note'`.
  - **When it happens:** in R3 the unmatched warnings were "halal short by 15 meals" and an unconfirmed-delivery note
    for SH-03; in R7 there were six commitment and shortage warnings.
  - **Effect in the app:** the Dashboard tab shows "Dashboard could not be built: KeyError: 'other_note'" instead of
    the figures, and the map stays empty.
  - **Not affected:** the chat tools, Review & finalize, and the calculations; R4 finalized correctly.
  - **Why it was missed:** the P38 unit test added only one unmatched warning.
- **F2 (found by reading the code, NOT executed, because F1 stops the dashboard first):** the dashboard creates a
  special-diet shortage action only for status `shortage`, and its special-diet table shows "Enough in stock" for any
  status other than shortage or missing information. A special diet with status `no_stock` (need > 0, stock 0) would
  therefore not be flagged as a shortage and would read "Enough in stock".

Neither F1 nor F2 was fixed (the prompt asked for no behavior changes). Both affect the P38/P39 dashboard display
only, not the calculations.

## 3. Efficiency: automated processing time

Only automated processing was measured, on one machine (Python 3.14.7, macOS) with the sample data size (4 shelters,
9 inventory rows, 5 commitments). Planning times are wall-clock after one warm-up run.

| Operation (automated) | Runs | Median | p95 | Max |
|---|---|---|---|---|
| Shelter needs | 30 | 7.3 ms | 7.7 ms | 8.6 ms |
| Warehouse inventory | 30 | 9.4 ms | 10.1 ms | 10.7 ms |
| Allocation draft (Plan A + Plan B) | 30 | 18.7 ms | 21.9 ms | 23.1 ms |
| Supply-request draft | 30 | 18.8 ms | 21.8 ms | 29.3 ms |
| Finalization review (`review_plan`) | 30 | 15.8 ms | 16.1 ms | 17.0 ms |
| All dashboard figures (`load_dashboard`) | 30 | 41.4 ms | 44.4 ms | 47.5 ms |
| Finalize and store (SQLite, fresh DB) | 5 | 30.9 ms | — | 31.7 ms |

**Report extraction** (real `gpt-6-luna` calls through Portkey; one run each; per report = AI extraction + AI safety
screen + code checks; wall-clock):

| Set | Reports | Portkey cache status | Median per report | Range |
|---|---|---|---|---|
| 5 new reports written for this evaluation (N1–N5, English and Japanese) | 5 | all calls MISS (reached the provider) | **3.4 s** | 3.3–6.1 s |
| 5 sample reports (E1–E5), extracted before in P25 | 5 | extraction HIT (replayed by Portkey's response cache), screen MISS | 2.0 s | 1.5–2.5 s |

- Only the first row measures model processing. The second row is faster because the extraction was served from
  Portkey's cache, so it is **not** a model processing time.
- Model latency per call (from the usage log): extraction 1.9–4.3 s, safety screen 1.0–2.0 s on MISS. No call
  failed.
- The extracted fields are saved in the results. Their correctness was **not** scored here (this evaluation measured
  time only). Two new reports had general meals left blank ("About 40 meals"; "食料なし" = no food); staff review
  would need to fill these.

**Human review time: NOT MEASURED.** No staff were timed reading extractions, correcting fields, acknowledging
warnings, or finalizing. So no end-to-end time, no comparison with a manual process, and no productivity gain can be
stated. On this data, automated planning takes milliseconds and AI extraction takes seconds per report, but the time
staff need to review is unknown.

## Limits

- Synthetic data at sample scale (at most 4 shelters). Timings at larger scale are unknown.
- The oracle is independent code, but it was written by the same developer (Claude) from the same documentation as
  the app. A misunderstanding shared by both would not be detected. Two oracle errors were found and corrected (run 1
  is kept).
- R8 shows that the documented dispatch/recount rule is ambiguous for partial recounts. The app's behavior is the
  conservative one, but the rule itself is not settled.
- Extraction timing comes from one run per report; network and provider latency vary.
- No usability, real-world, or staff-productivity claim is made.
