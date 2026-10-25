# Evidence Index — Disaster FoodBridge

Links the project's main claims to evidence, for the final report. Companion to
[development_log.md](development_log.md) (stage numbers below refer to that log; P# = prompt in `AI_prompts.md`).

## Status legend

| Mark | Meaning |
|---|---|
| ✅ | **In the project and re-runnable now** (code or a passing pytest test) |
| 👁 | **Observed during development only**: seen in a browser, chat, or server log, but not saved as a file in the project |
| 📷 | **Screenshot in the project** under `evidence/screenshots/` (see [Screenshots](#screenshots) for exactly what each one shows) |
| ❌ | **Not yet collected**: needs to be gathered before the report |

How to re-run the automated evidence:

```bash
cd ~/Documents/"AI code"/final_project && .venv/bin/python -m pytest -q
```

Last full run at the time of writing: **222 passed** (26 test files, after P42).

---

## 1. Calculations (need, allocation, rounding)

| Claim | Evidence | Status |
|---|---|---|
| Need = people × meals/day × hours/24, rounded up; the defaults (3 meals, 24 h) are configurable | `src/allocation.py` `meals_needed`; `src/config.py`; `test_allocation.py::test_meals_needed_uses_configurable_defaults`, `test_agent_tools.py::test_needs_use_configured_rate_and_window` | ✅ |
| Proportional split by largest remainder is exact, never exceeds demand, and doesn't depend on row order | `allocate_proportionally`; `test_allocation.py::test_proportional_split_with_largest_remainder`, `::test_split_is_exact_bounded_and_order_independent`, `::test_zero_and_fractional_supply` | ✅ |
| Only `general` meals are pooled; special-diet stock never reaches general meals | `test_allocation.py::test_special_stock_is_never_pooled_into_general`, `test_allocation_tool.py::test_special_diets_stay_separate_with_staff_decisions` | ✅ |
| Special-diet shortages and unknown counts are flagged, not split | `test_allocation.py::test_special_shortage_is_flagged_not_split`, `::test_unknown_special_count_needs_review`, `::test_special_need_without_any_stock` | ✅ |
| Plan A on the sample data = 206 / 39 / 351, shortage 407 | Manual chat (P16) and hand calculation in development_log Stage 11; recomputable with `calculate_allocation` on `data/sample/` | 👁 (no saved output); ❌ a test pinning the sample-data figures |
| The LLM never computes allocations; figures come from code | Design: `src/agent.py` instructions, tools in `src/agent_tools.py` / `src/drafts.py` | ✅ (code); 👁 agent outputs matched the tool output in each chat test (P8–P17) |

## 2. Data loading, validation, record log

| Claim | Evidence | Status |
|---|---|---|
| A missing required column is a file-level error (bug found and fixed in P5) | `src/data_io.py`; `test_validation.py::test_missing_required_column_is_file_error` | ✅ |
| Bad values (negative, non-integer, missing timezone, non-numeric) block validation | `test_validation.py::test_bad_values_mark_row_not_ok`, `::test_special_people_cannot_exceed_evacuees`, `::test_general_is_not_a_special_tag` | ✅ |
| An unknown special-needs count (`?`) is a warning, not an error | `test_validation.py::test_unknown_special_count_is_warning_not_error` | ✅ |
| Latest validated record wins; pending and older records are ignored; corrections supersede | `src/records.py`; `test_records_planning.py::test_latest_validated_ignores_pending_and_older_reports`, `::test_validated_correction_supersedes_original`, `::test_status_rules` | ✅ |
| A row with errors is never used, even if the file marks it validated | `src/store.py`; `test_agent_tools.py::test_row_with_errors_is_not_used_even_if_marked_validated` | ✅ |
| Sample data is kept separate from application logic | `data/sample/` + README; paths only through `SHELTER_LOG_PATH` / `INVENTORY_LOG_PATH` / `COMMITMENTS_LOG_PATH` | ✅ |
| No shelter counts or quantities are hardcoded in `src/` | Manual scan in P5 (only the configurable defaults and "24 hours per day" found) | 👁; ❌ re-run and save the scan output |

## 3. Dispatch tracking and delivery states

| Claim | Evidence | Status |
|---|---|---|
| A dispatch is subtracted only if it left its warehouse after that warehouse's latest count | `records.inventory_position`; `test_dispatch_tracking.py::test_dispatch_after_latest_count_is_deducted`, `::test_newer_recount_replaces_earlier_count_without_double_deduction`, `::test_recount_in_one_warehouse_does_not_affect_dispatch_from_another` | ✅ |
| Approved food stays reserved across recounts | `test_dispatch_tracking.py::test_approved_food_stays_reserved_across_recounts` | ✅ |
| Before/after double-count figures (390 → 420; 300 → 250; sample 566 → 596) | Scenario script run in P10 (script deleted afterwards) | 👁; ❌ recreate the script and save its output |
| Delivery is never assumed; a delayed delivery stays "shipped, not confirmed" and is flagged | `records.incoming_breakdown`; `test_delivery_states.py::test_delayed_delivery_newer_report_does_not_assume_arrival`, `test_dispatch_tracking.py::test_food_dispatched_before_report_is_not_assumed_delivered` | ✅ |
| Confirmed delivery is not double-counted after a newer report | `test_delivery_states.py::test_newer_report_after_confirmed_delivery_is_not_double_counted`, `::test_delivery_at_report_time_is_in_that_report` | ✅ |
| Status changes are enforced (approved → dispatched → delivered; cancel only while approved) | `test_delivery_states.py::test_state_transitions_are_enforced`, `::test_loader_checks_delivery_fields` | ✅ |
| Confirmed deliveries are not labeled "on its way" | `test_delivery_states.py::test_needs_tool_reports_states_and_delayed_delivery` (`still_on_its_way_meals == 25`) | ✅; 👁 agent wording before/after (P14 / P15 chat); 📷 S07, S08 |
| Delayed-delivery warning shown to a user in the chat | Never shown: the sample data has no such case | ❌ |

## 4. AI agent and tools

| Claim | Evidence | Status |
|---|---|---|
| The agent uses `gpt-6-luna` through Portkey with `PORTKEY_API_KEY` | `src/agent.py`, `src/config.py`; probe in P7 reported model `gpt-6-luna-2026-09-22` | ✅ (code); 👁 (probe output not saved) |
| The Responses API is needed for tools on this deployment (HTTP 400 on Chat Completions) | Server log in P8; `OpenAIResponsesModel` in `src/agent.py` | ✅ (code); 👁 (error log not saved) |
| All five tools are registered and called offline | `test_agent_tools.py::test_agent_calls_tool_offline` (PydanticAI `TestModel`) | ✅ |
| Tool outputs: shelters, inventory, needs, allocation, request facts | `test_agent_tools.py`, `test_allocation_tool.py`, `test_supply_request.py` | ✅ |
| `prepare_supply_request` is read-only | `test_supply_request.py::test_tool_is_read_only` | ✅ |
| The agent does not invent figures when data is missing | Unit tests of tool "no data" notes (`::test_missing_file_means_no_validated_data`, `::test_needs_without_validated_reports`, `test_allocation_tool.py::test_no_validated_reports`, `test_supply_request.py::test_no_validated_data`) | ✅ (tools only); ❌ a real-model chat test with empty data |
| The agent cannot finalize, approve, or write | `test_agent_cannot_finalize.py` (3 tests: tool list, no write references in agent / tool / draft code, instructions) | ✅; 👁 chat refusal in P21 (0 tool calls); 📷 S13 |
| Errors are shown as a recoverable error bubble | Manual P6 (simulated failure) and P7 (real bug) | 👁 |

### Real model calls observed (token usage from server logs, not saved)

| P# | Question (abridged) | Tool calls | Requests | Input / output tokens |
|---|---|---|---|---|
| P7 | Probe through Portkey ("Reply with the word OK.") | 0 | 1 | 12 / 4 |
| P7 | "What can you help me with…special dietary needs?" | 0 | 1 | 212 / 293 |
| P8 | "What's the latest situation at our evacuation shelters?" | 1 | 2 | 1,095 / 318 |
| P9 | "How much food do we currently have available?" | 1 | 2 | 1,870 / 354 |
| P9 | "Please show that as a table." | 1 | 2 | 2,363 / 435 |
| P11 | "How much food do we currently have available?" | 1 | 2 | 2,338 / 408 |
| P12 | "How much food does each shelter still need…24 hours?" | 2 | 2 | 2,940 / 510 |
| P14 | Needs + status of committed / shipped food | 1 | 2 | 2,950 / 552 |
| P15 | Same question after relabeling | 1 | 2 | 3,124 / 526 |
| P16 | "Prepare a food allocation plan…" | 1 | 2 | 3,517 / 573 |
| P17 | "Draft a request for additional food supplies…" (2 runs) | 1 each | 2 each | 4,294 / 637 each |
| P21 | "Please finalize the current allocation plan…" | 0 | 1 | 1,845 / 118 |

Status: 👁 for all rows. ❌ To collect: re-run with server logging written to a file (or a Portkey dashboard
export) if the report needs verifiable token and cost figures. Not collected: the first P7 call and the failed
first P8 call (HTTP 400), which were also real calls. Portkey caching of the second P17 run is unverified.

## 5. Finalization, persistence, concurrency

| Claim | Evidence | Status |
|---|---|---|
| Finalization recalculates from the latest validated data; changed results need confirmation | `planning.finalize_plan`; `test_records_planning.py::test_changed_data_requires_confirmation_before_finalizing`, `::test_config_change_also_changes_fingerprint`, `test_finalization.py::test_stale_review_needs_confirmation_and_stores_nothing` | ✅ |
| The plan snapshot and approvals are saved atomically in SQLite | `src/finalization.py`; `test_finalization.py::test_successful_finalization_persists_plan_and_approvals`, `::test_failure_while_writing_rolls_back_everything` | ✅ |
| A repeated finalization fails safely, without duplicates | `test_finalization.py::test_repeated_finalization_fails_safely` | ✅ |
| Simultaneous finalizations: exactly one succeeds | `test_finalization.py::test_simultaneous_finalization_threads`, `::test_simultaneous_finalization_separate_processes`; repeated 10/10 (P19) and 5/5 (P20, P22) | ✅ (tests); 👁 (repeat counts not saved) |
| Before the fix, two finalizations both succeeded (120 meals committed vs 60 available) | P18 probe script (deleted) | 👁; ❌ recreate if the report should show the "before" case |
| Saved approvals are seen by later drafts (incremental planning) | `test_finalization.py::test_successful_finalization_persists_plan_and_approvals` (next draft: 0 available, 60 unmet); browser P21 (0 available, 407 unmet) | ✅; 👁 |

## 6. Pending-data acknowledgements

| Claim | Evidence | Status |
|---|---|---|
| Pending reports or counts and shelters with no validated report produce specific warnings | `planning.pending_data_warnings`; `test_acknowledgements.py::test_all_kinds_of_pending_data_are_warned` | ✅ |
| Finalization stops until every warning is acknowledged with a reason (≥ 10 characters) | `test_acknowledgements.py::test_missing_acknowledgements_stop_finalization` | ✅; 👁 browser P21 messages |
| Acknowledgements are stored for audit (snapshot and table) | `test_acknowledgements.py::test_acknowledged_warnings_finalize_and_are_stored_for_audit` | ✅ |
| Changed pending data requires a fresh review and acknowledgement | `::test_new_pending_data_after_review_requires_fresh_review_and_acknowledgement`, `::test_replaced_pending_report_changes_the_warning`, `::test_pending_data_validated_before_finalization_requires_fresh_review` | ✅ |

## 7. Saved supply request and timestamps

| Claim | Evidence | Status |
|---|---|---|
| The saved request matches its finalized plan (fingerprint, shortages, special diets, period, warnings) | `test_saved_request.py::test_saved_request_matches_its_finalized_plan` | ✅ |
| Later data changes don't alter the stored request (byte-for-byte) | `test_saved_request.py::test_later_data_changes_do_not_alter_the_saved_request`; browser P22 (identical text after the changes, compared in the page, not by image) | ✅; 👁; 📷 S14 shows the retrieved request only, not the comparison |
| No request is stored without a successful finalization; a repeat keeps the original; rollback with the plan | `test_saved_request.py::test_no_request_without_successful_finalization`, `::test_repeat_finalization_keeps_the_original_request`, `::test_request_rolls_back_with_the_plan` | ✅ |
| Stored timestamps are UTC; display uses `DISPLAY_TIMEZONE` (default Asia/Tokyo); naive times rejected | `src/timeutil.py`; `test_saved_request.py::test_stored_timestamps_are_utc_and_display_uses_configured_zone` | ✅ |
| The request is a DRAFT and nothing is sent externally | Status text tested in `::test_saved_request_matches_its_finalized_plan` and `::test_rendered_request_shows_only_saved_facts`; no sending code exists in `src/` | ✅ |
| Placeholders keep their brackets in the chat | `test_app_render.py` (2 tests); 📷 S10 | ✅ |

## 8. User interface

| Claim | Evidence | Status |
|---|---|---|
| Chat: Enter sends, thinking dots, Send disabled while waiting, error bubble | Manual browser checks in P6 | 👁 (not in any screenshot: S01 shows only the chat layout and tool panel); ❌ no automated UI test |
| Markdown tables render | Manual P9 | 👁; 📷 S03 (before), S04 (after) |
| Review & finalize flow works end to end, including a data change before confirmation | Manual browser run in P21 on scratch data (plans `ee065f993387`, `c6ea00cb1dbf`) | 👁; 📷 S11, S12; ❌ no automated end-to-end test (e.g. Dash testing or Playwright) |
| Saved request retrievable from the "Saved plans" dropdown | Manual browser run in P22 (plan `3e2717444892`) | 👁; 📷 S14 |

## 9. Security and configuration

| Claim | Evidence | Status |
|---|---|---|
| No real API key is stored in the project | `.gitignore` excludes `.env`; `.env.example` has a placeholder only; key scans in P2 and P7 found nothing | ✅ (files); 👁 (scans); ❌ re-run and save a scan before submission |
| Live data and the database are excluded from git | `.gitignore` (`data/live/*`, `data/uploads/*`); checked in a throwaway git repository in P27 (4 working files ignored; `.gitkeep` and sample files tracked) | ✅ (file); 👁 (check output not saved) |
| Runtime environment versions | Observed: Python 3.14.7, pandas 3.1.0, pytest 9.1.1, pydantic_ai 2.61.0, openai 3.37.0, SQLite 3.53.4. `requirements.txt` is unpinned. | 👁; ❌ save `pip freeze` output |

## 10. AI extraction of free-text reports (P25)

| Claim | Evidence | Status |
|---|---|---|
| Extraction uses PydanticAI with `gpt-6-luna` and a Pydantic output model | `src/extraction.py` (`ShelterReportExtraction`, `_agent`), `src/llm.py`; the run file records `"model": "gpt-6-luna"` | ✅ |
| The original report text is kept exactly | `test_extraction.py::test_extract_wiring_offline` (`source_text` equals the input, including odd spacing); `source_text` in the saved run | ✅ |
| Missing values stay unknown and are flagged | `test_extraction.py::test_missing_values_stay_unknown_and_are_flagged`; real run E2 (count, meals, time null) | ✅ |
| Conflicting values are flagged, not resolved by guessing | Real run E3 (count null; issue quotes "Evacuees: 210" and "…is 260"); `test_extraction.py::test_model_issues_are_kept_with_their_source` | ✅ |
| Quotes are checked against the text; values need quotes | `test_extraction.py::test_quote_not_in_the_text_is_flagged`, `::test_value_without_quote_is_flagged` | ✅ (no fabricated quote occurred in the real run) |
| Report time: explicit date and time only; the configured timezone is always flagged; a time after receipt is rejected; stored as UTC | `test_extraction.py::test_complete_report_has_only_the_timezone_note`, `::test_stated_timezone_is_used_without_a_note`, `::test_report_time_later_than_receipt_is_rejected`; real run E1 (JST stated), E3 (flagged), E4 (no year → null), E5 (rejected) | ✅ |
| Special-diet checks (people above headcount, unknown counts, food with no meal amount) | `test_extraction.py::test_special_needs_checks`, `::test_special_food_without_a_meal_amount_is_flagged_not_dropped_silently`; real run E5 (50 > 45 caught by the code check) | ✅ |
| Bug: special-diet food with no meal amount was dropped silently (E3), now flagged | Original run file vs `…_rechecked.json` (only E3 gained the new issue; model outputs identical) | ✅ |
| Extracted rows cannot pass validation while values are unknown | `test_extraction.py::test_rows_map_to_the_shelter_schema_and_incomplete_rows_cannot_validate` | ✅ |
| Nothing was saved as validated data | Extraction code has no write path; `data/live/` checked empty before and after the real run; the runner writes only to `evidence/extraction/` | ✅ (code); 👁 (folder listing not saved) |
| The extractor is not available to the chat agent | `test_agent_cannot_finalize.py::test_agent_tools_are_read_only` (tool list unchanged: 5 tools) | ✅ |
| Extraction accuracy in general | Only 5 hand-written examples, one run | ❌ no accuracy measurement; outputs can vary between runs |

**Saved real-model results** (✅ verifiable files):
- [`evidence/extraction/extraction_run_20261024T193012Z.json`](evidence/extraction/extraction_run_20261024T193012Z.json):
  original text, structured output, issues, CSV-shaped row, and **token usage per report** (from PydanticAI's
  usage object), for E1–E5.
- [`evidence/extraction/extraction_run_20261024T193012Z_rechecked.json`](evidence/extraction/extraction_run_20261024T193012Z_rechecked.json):
  the same model outputs with the code checks re-applied after the E3 fix (no model calls).
- Inputs: [`data/sample/free_text_reports.json`](data/sample/free_text_reports.json). Runner:
  [`scripts/run_extraction_examples.py`](scripts/run_extraction_examples.py).

| Report | Case | Requests | Input / output tokens |
|---|---|---|---|
| E1 | complete, timezone stated | 1 | 971 / 253 |
| E2 | incomplete, vague | 1 | 944 / 283 |
| E3 | contradictory headcount | 1 | 970 / 276 |
| E4 | Japanese, no year | 1 | 966 / 682 |
| E5 | time after receipt; special-diet count above headcount | 1 | 942 / 201 |
| **Total** | run 2026-10-24 19:30:12–19:30:35 UTC | **5** | **4,793 / 1,695** |

## 11. Staff review and approval of extracted reports (P26)

| Claim | Evidence | Status |
|---|---|---|
| Nothing is saved until staff approve | `src/intake.py` (only `approve_extracted_report` writes); browser P26: approval without corrections was refused and the log stayed at 8 lines | ✅ (code); 👁 |
| Approved records are validated with the same rules as CSV uploads; invalid input writes nothing | `test_intake.py::test_invalid_or_unapproved_input_writes_nothing` (byte-identical file after 6 rejected cases) | ✅ |
| Append-only: earlier reports are never overwritten | `store.append_record`; `test_intake.py::test_approval_appends_a_validated_record_without_touching_earlier_ones` (`after.startswith(before)`); browser P26: first 1,383 bytes identical | ✅; 👁 |
| Original text, approver, and approval time (UTC) are kept; corrected fields noted | `test_intake.py::test_approval_appends_a_validated_record_without_touching_earlier_ones`; browser P26 row for `ext-5e9a7b773d` | ✅; 👁 |
| Staff enter times in the display timezone; stored as UTC | `test_intake.py::test_times_are_entered_in_display_zone_and_stored_in_utc` | ✅ |
| Concurrent approvals don't corrupt the log | `test_intake.py::test_concurrent_approvals_all_land_intact` (8 threads) | ✅ |
| A log that can't store the original text is refused, not truncated | `test_intake.py::test_log_without_source_text_column_is_refused_not_truncated` | ✅ |
| Logs with mixed timestamp offsets and precisions parse correctly (bug fixed in P26) | `store._load_log` (`utc=True`, `format="ISO8601"`); assertion in `test_intake.py::test_approval_appends_a_validated_record_without_touching_earlier_ones` | ✅ |
| A newly approved report is used by the recalculated plan; a previously reviewed plan needs fresh confirmation | `test_intake.py::test_approved_report_changes_the_plan_and_old_review_needs_confirmation`; browser P26 (SH-03 590 → 692; shortage 407 → 509; "Not finalized") | ✅; 👁; 📷 S16 |
| Approving a newer report resolves an older pending-report warning | `test_intake.py::test_approval_resolves_an_older_pending_report_warning` | ✅ (not shown in the browser) |
| The incomplete report showed empty fields and 5 warnings in the UI | Browser P26 | 👁 (not captured as a screenshot: S15 shows the state after approval) |
| The real sample log was not modified by the browser test | MD5 `4bc50129…` before and after; the test used scratch copies | 👁 |

## 12. Working data and sample-data protection (P27)

| Claim | Evidence | Status |
|---|---|---|
| All data paths default to one working folder (`LIVE_DATA_DIR`, default `data/live/`) | `src/config.py` `_data_path`; `test_workspace.py::test_default_paths_live_in_the_working_folder` | ✅ |
| First setup copies the sample logs byte for byte | `src/workspace.py`; `test_workspace.py::test_first_setup_copies_the_sample_logs`; browser P27 (log "seeded" ×3, `cmp` identical) | ✅; 👁 |
| Restart never overwrites working data | `test_workspace.py::test_restart_keeps_existing_working_data`; browser P27 (log "kept" ×3; SHA-256 of working files identical before and after the restart) | ✅; 👁 |
| Only missing files are seeded; simultaneous starts seed each file once | `test_workspace.py::test_only_missing_files_are_seeded`, `::test_concurrent_first_setup_seeds_each_file_once` | ✅ |
| Writes into `data/sample/` are refused (report approval, log append, finalization database) | `src/workspace.py` `assert_writable`; `test_workspace.py::test_writes_into_the_sample_folder_are_refused` | ✅ |
| Approval, recalculation, finalization, and restart all use the same working dataset | `test_workspace.py::test_approval_recalculation_finalization_and_restart_use_the_working_copies`; browser P27 (record `ext-2a8224785a`, plan `b171e8435131`, next plan 0 available after the restart) | ✅; 👁 |
| `data/sample/` is byte-for-byte unchanged | Fixture in `test_workspace.py` checks the SHA-256 of every sample file after each test; browser P27: `shasum -a 256 data/sample/*` equal to the baseline taken at the start of P27 | ✅; ✅ baseline saved: [`evidence/data_integrity/sample_sha256_baseline_p27.txt`](evidence/data_integrity/sample_sha256_baseline_p27.txt) |
| Root cause was the launch configuration overriding paths to `data/sample/` | Launch configuration before and after P27 (outside the project, in the session folder) | 👁 |
| `data/sample/README.md` was briefly edited in P27 and restored exactly | Hash comparison after restoring (all sample files equal to the baseline) | 👁 |

## 13. Warehouse photo analysis (P28)

**Important:** the two test images are **synthetic drawings**, generated by `scripts/make_sample_warehouse_photos.py`
with a known `data/sample_photos/ground_truth.json`. They are not photographs. No claim about real-photo accuracy is
supported.

| Claim | Evidence | Status |
|---|---|---|
| Vision uses PydanticAI with `gpt-6-luna` and a structured output separating facts from estimates | `src/vision.py` (`PhotoAnalysis`, `ObservedItem`); run file (`"model": "gpt-6-luna"`, `observed_facts` / `uncertain_estimates`) | ✅ |
| On the two synthetic images, all visible units were counted correctly (6, 8, 12, 1; 36, 3) | Run file vs `ground_truth.json` | ✅ (synthetic only) |
| An unreadable label was reported as unreadable, not guessed | Run file (WH-A item with `label_text: null`, `unreadable`); follow-up answer | ✅ (synthetic only) |
| Label transcription can contain small errors | Run file: "24 can / case" vs the drawn "24 cans / case" | ✅ |
| Partial views are never treated as total stock (fewer → inconclusive; not seen → no conclusion) | `test_vision.py::test_fewer_visible_is_never_a_shortage`, `::test_recorded_items_not_seen_are_inconclusive`; run file (bread 6 vs 10 → `inconclusive_partial_view`) | ✅ |
| More visible than recorded, or unrecorded items, are flagged as possible discrepancies | `test_vision.py::test_more_visible_than_recorded_is_a_possible_discrepancy`, `::test_unrecorded_and_unreadable_items_need_review`, `::test_per_container_label_converts_units_and_says_so`; run file (miso; alpha rice 150 > 120) | ✅ |
| Bug: a unit mismatch hid a discrepancy (36 "cartons" vs 30 packs), now sent to review | Original run (`not_comparable`) vs `…_recompared.json` (`needs_review`; model outputs identical); `test_vision.py::test_different_units_with_a_count_above_the_record_go_to_review` | ✅ |
| Each analysis is stored with an exact copy of its image; tampering is detected | `test_vision.py::test_analysis_is_stored_with_an_exact_copy_of_the_image`, `::test_tampered_stored_image_is_detected`; `evidence/vision/analyses/*/image.png` + `analysis.json` (SHA-256 recorded) | ✅ |
| Follow-up questions use the stored image and are logged next to it | `test_vision.py::test_follow_up_questions_use_the_stored_image_and_are_logged`; `evidence/vision/analyses/photo-da87f1e87d/followups.jsonl` (real answer) | ✅ |
| Inventory records were not changed | Run file: `inventory_sha256_before` = `inventory_sha256_after`; `test_vision.py::test_analysis_is_stored_with_an_exact_copy_of_the_image` | ✅ |
| Vision is not available in the chat or the UI | `test_agent_cannot_finalize.py::test_agent_tools_are_read_only` (tool list unchanged); no UI code | ✅ |
| Accuracy on real warehouse photos | None tested | ❌ need real photos (with permission) and a labeled ground truth |

**Saved real-model results** (✅ verifiable files):
- [`evidence/vision/vision_run_20261024T195656Z.json`](evidence/vision/vision_run_20261024T195656Z.json): model outputs,
  comparisons as first run, follow-up, and token usage (3 requests, 5,765 / 1,497 tokens).
- [`evidence/vision/vision_run_20261024T195656Z_recompared.json`](evidence/vision/vision_run_20261024T195656Z_recompared.json):
  the same model outputs with the corrected comparison rules (no model calls).
- [`evidence/vision/analyses/`](evidence/vision/analyses/): per-analysis folders with the exact image copy and
  `analysis.json`.
- Inputs: [`data/sample_photos/`](data/sample_photos/) (synthetic images and `ground_truth.json`). Generator:
  [`scripts/make_sample_warehouse_photos.py`](scripts/make_sample_warehouse_photos.py). Runner:
  [`scripts/run_vision_examples.py`](scripts/run_vision_examples.py).

## 14. Warehouse photos tab and model-client lifecycle (P29)

| Claim | Evidence | Status |
|---|---|---|
| Staff can upload a photo, choose the warehouse, analyze, and review the results next to the image | `app.py` (Warehouse photos tab); `test_photo_ui.py::test_upload_analyze_review_and_follow_up_without_changing_data`; browser P29 with both synthetic images | ✅; 👁; 📷 S18, S19 |
| The image shown is the stored copy, byte for byte | `test_photo_ui.py::test_upload_analyze_review_and_follow_up_without_changing_data` (`img.src` equals the file's data URL) | ✅ |
| Follow-up questions use the same image and are kept with it | `evidence/vision/browser_p29/*/followups.jsonl` (7 real Q&As with token usage) | ✅ |
| Read-only: no inventory, allocation, or finalization change | `test_photo_ui.py::test_upload_analyze_review_and_follow_up_without_changing_data` (CSV and DB hashes and the plan fingerprint unchanged); browser P29: working CSVs byte-identical to their seeds, no finalization DB created | ✅; 👁 |
| Bad input is reported (no photo, no warehouse, unsupported type) | `test_photo_ui.py::test_missing_photo_or_warehouse_is_reported`, `::test_unsupported_upload_shows_an_error` | ✅ |
| Each model call gets its own HTTP client, closed in its own event loop | `src/llm.py` `run_with_fresh_model`; `test_extraction.py::test_each_run_gets_its_own_client_closed_in_the_same_event_loop` | ✅ |
| "Event loop is closed" (first) and "bound to a different event loop" (after a caching attempt) errors are gone | Server logs of the P29 browser sessions: errors before the fix; none across 6 calls in one process after it | 👁 (logs not saved) |
| Layout bug (analysis text cut off) and its fix | 📷 S17 (bug), S18 / S19 (after fix) | 📷 |
| Token usage of the browser calls | `evidence/vision/browser_p29/` (13 successful calls: 6 analyses, 7 follow-ups) | ✅; the chat call (1,841 / 127) and the failed follow-up are 👁 only |
| Identical repeat analyses came from a Portkey cache | Identical outputs and token counts, 0.6–1.8 s | ❌ not verified |

## 15. Safety evaluation 1: prompt injection against extraction (P30)

| Claim | Evidence | Status |
|---|---|---|
| Baseline and attack inputs are isolated and contain identical facts | `evidence/safety/injection_inputs_p30.json` (made-up data; facts checked to appear in all three texts) | ✅ |
| The real extraction agent was used with unchanged defenses | `scripts/run_injection_eval.py` calls `extract_shelter_report()`; run file states the model; `src/extraction.py` / `src/llm.py` hash prefixes identical before and after | ✅ |
| Neither attack changed extracted values, the CSV row, the report time, validation, or code-side warnings | `evidence/safety/injection_run_20261024T212735Z.json` (comparison in `injection_eval_p30.md`) | ✅ (one run per case) |
| No untrusted instruction was followed (no halal 0, count 30, meals 500, approval claims, or suppressed warnings) | Same run file, `checks` per case | ✅ (one run per case) |
| The injection attempts were **not detected or flagged** by the model or the app | Same run file: `model_flagged_injection` empty in both attacks | ✅ (finding) |
| In the baseline, the model raised no issues; warnings came from code checks | Same run file: `model_issue_count` 0, `code_issue_count` 2 | ✅ (finding) |
| Live data and finalized plans were not modified | Run file `isolation`: `data/live/` hashes identical; no finalization DB before or after | ✅ |
| Token usage | Run file: 976 / 260, 1,042 / 561, 1,023 / 260 (total 3,041 / 1,081) | ✅ |
| Robustness across repeated runs, other wordings or languages, other surfaces (vision, chat, request drafting) | Not tested | ❌ |

## 16. Prompt-injection detection (P31)

| Claim | Evidence | Status |
|---|---|---|
| Two-layer screen (pattern + model) flags attempts to override, suppress warnings, change values, or bypass approval | `src/injection_guard.py`; `test_injection_guard.py::test_p30_attack_a_is_flagged_for_all_four_goals`, `::test_p30_attack_b_is_flagged` | ✅ |
| Both P30 attacks are detected by both layers with real model calls; the baseline is not flagged | `evidence/safety/injection_defense_run_20261024T213837Z.json` (`p30_cases`) | ✅ (one run per case) |
| Before P31 the same attacks were undetected | `evidence/safety/injection_run_20261024T212735Z.json` (`model_flagged_injection` empty) | ✅ |
| Extracted values for the P30 cases are identical before and after (the attacks did not succeed in either run) | Defense run file: `before_after.extracted_fields_differing_from_p30` empty, `shelter_row_same_as_p30` true; `checks.injected_values_adopted` all false | ✅ |
| No false positives on 6 benign reports with staff instructions and words like system / warning / verified / ignore / skip | `evidence/safety/benign_reports_p31.json`; defense run file (`benign_cases`, `false_positives: []`); `test_injection_guard.py::test_operational_instructions_for_staff_are_not_flagged` | ✅ (small sample) |
| Detection does not rely only on exact keywords (paraphrase, spacing, invisible characters, full-width, Japanese, field names) | `test_injection_guard.py::test_paraphrased_and_obfuscated_attacks_are_flagged` (6 cases) | ✅ pattern layer, offline only; ❌ not tested with the real model screen |
| The model layer can catch paraphrases the patterns miss | `test_injection_guard.py::test_model_layer_finds_what_patterns_miss_in_a_paraphrase` | ✅ with a test model only |
| Staff see the warning; the original report is kept | `test_injection_guard.py::test_staff_see_a_prominent_alert`; browser P31 | ✅; 👁; 📷 S20 |
| Extraction, validation, and approval rules unchanged | Fingerprints of instructions, schema, `check_extraction`, and `to_shelter_row` identical before and after; `src/validation.py` / `src/intake.py` SHA-256 unchanged (5c3bb221…, 935ab98f…); `test_injection_guard.py::test_extraction_adds_warnings_without_changing_values_or_approval` | ✅ (fingerprint comparison 👁, not saved as a file) |
| The pattern layer still works if the model screen fails | `test_injection_guard.py::test_pattern_layer_still_works_if_the_model_screen_fails` | ✅ |
| Token cost of the screen | Defense run file `usage_breakdown` (screen about 380–480 in / 14–318 out per report; total 12,454 / 3,639 for 9 reports) | ✅ |
| Detection or false-positive *rates* | Not measured (sample too small) | ❌ |

## 17. Tokenomics (P32)

| Claim | Evidence | Status |
|---|---|---|
| Published gpt-6-luna rates (standard short context: $0.10 input, $0.01 cached input, $0.125 / $0.25 cache writes for 30 min / 12 h, $0.50 output per 1M), checked 2026-10-24 | `evidence/tokenomics/pricing_gpt-6-luna_2026-10-24.json` (source URL https://developers.openai.com/api/docs/pricing); `test_tokenomics.py::test_pricing_file_records_source_date_and_caveats` | ✅ (fetched page content not archived) |
| Caching conditions (1,024-token minimum for GPT-5.6 and later; read 0.1×, write 1.25× / 2.5×; prefix match) | Pricing file `caching_conditions_from_guide` (source: prompt-caching guide) | ✅; gpt-6-luna not named in the guide (uncertain) |
| Course Portkey/Azure billing at these rates | Not checked | ❌ |
| Saved usage records contain only requests, input_tokens, output_tokens; cache, reasoning, and cost fields missing | `tokenomics_2026-10-24.json` → `token_fields` | ✅ |
| 42 measured calls counted once (copies excluded); 14 chat records kept separate as observed | `test_tokenomics.py::test_inventory_counts_each_real_call_once` | ✅ |
| Estimated cost per call by workflow (point and caching bounds) | `tokenomics_report_2026-10-24.md` section 4; `test_tokenomics.py::test_summary_matches_a_direct_calculation` | ✅ (estimates) |
| Calculation correctness (per-million, long context, cached / write split, bounds, scaling) | `test_tokenomics.py` (`::test_call_cost_uses_published_rates_per_million`, `::test_long_context_rates_apply_above_the_threshold`, `::test_cached_reads_and_writes_are_priced_separately`, `::test_caching_bounds_only_for_prompts_of_at_least_1024_tokens`, `::test_scaling_is_plain_arithmetic_and_requires_unit_costs`) | ✅ |
| Per-user cost and 100 / 10,000-user cost | Only a formula and two hypothetical profiles in the report (section 7) | ❌ needs measured activity (report section 9) |

## 18. Per-call usage logger (P33)

| Claim | Evidence | Status |
|---|---|---|
| Every model API call is logged once (one line per HTTP response), for all five workflows | `src/usage_log.py`, `src/llm.py`; `test_usage_log.py::test_tool_calling_run_logs_each_api_call_once`; real run: 6 calls → 6 lines (`evidence/usage/usage_fields_p33.json`) | ✅ |
| Missing fields are null (unknown), not zero; PydanticAI would show 0 | `test_usage_log.py::test_unknown_fields_stay_null_and_zero_stays_zero`, `::test_response_without_details_keeps_cache_fields_unknown` | ✅ |
| The API returns cached-read, cache-write, and reasoning tokens for gpt-6-luna via Portkey; the cache-write TTL split is not returned | `evidence/usage/usage_log_p33.jsonl` (`usage_raw`); `usage_fields_p33.json` (`present` counts, `raw_keys`) | ✅ |
| Implicit cache writes and reads occur for prompts of at least 1,024 tokens (e.g. chat wrote 1,839, then read 1,839) | `usage_log_p33.jsonl` | ✅ (one run) |
| Portkey's cache serves repeated identical prompts (header HIT; replayed usage; no Azure headers) | `usage_log_p33.jsonl` `headers` (HIT for extraction, screen, photo analysis; MISS for chat, follow-up) | ✅ reported by Portkey; ❌ billing not verified |
| No API key, report text, model output, image data, cookies, or `x-ratelimit-key` in the log | `test_usage_log.py::test_one_line_per_call_with_usage_and_no_secrets`; real run `secrets_or_content_found` all false | ✅ |
| Failed calls are logged without usage or error messages | `test_usage_log.py::test_failed_call_is_logged_without_usage_or_error_message` | ✅ (mocked only) |
| Append-only; logging failures never change agent behavior | `test_usage_log.py::test_log_is_append_only`, `::test_logging_failure_never_changes_agent_behavior` | ✅ |
| No USD costs in the log | `src/usage_log.py` (no cost fields); test asserts no cost in `usage` | ✅ |
| Cost estimates using measured cache tokens | Done in P34 (section 19) | ✅ (estimates) |

---

## 19. Tokenomics from the usage log (P34)

| Claim | Evidence | Status |
|---|---|---|
| 24 real calls logged through the normal app code path (chat, extraction, screen, photo analysis, follow-ups, with repeats) | `scripts/run_usage_sample_p34.py`; `evidence/tokenomics/usage_log_snapshot_p34.jsonl` (copy of `data/live/usage_log.jsonl`) | ✅ (one run) |
| Costs priced per token category (uncached input, cached read, cache write, output) per call | `src/tokenomics.py` `token_categories`, `price_logged_call`; `test_tokenomics_log.py::test_price_logged_call_per_category_and_ttl_scenario` | ✅ (estimates) |
| Unknown token fields are not priced as 0 | `test_tokenomics_log.py::test_token_categories_split_input_and_keep_unknown_as_none` | ✅ |
| Portkey HITs kept apart from provider calls; priced only under HIT_FREE / HIT_AS_REPLAYED scenarios | `test_tokenomics_log.py::test_call_kind_separates_portkey_hits_from_provider_calls`, `::test_portkey_hit_is_free_or_replayed_only_by_named_scenario`; report "Calls by kind" and scenario totals | ✅ HIT reported by Portkey; ❌ billing not verified |
| Cache-write TTL unknown, so W30 and W12 scenarios are shown | Snapshot (TTL fields null in all calls); report tables | ✅ |
| Per-workflow estimates and comparison with P32, with reasons | `tokenomics_p34_2026-10-24.json` (`comparison_with_p32`, `why_changed`); `tokenomics_p34_report_2026-10-24.md`; `test_tokenomics_log.py::test_saved_p34_evidence_matches_recomputation_from_snapshot` | ✅ (small sample) |
| Photo follow-ups write ~1,670 tokens to the prompt cache and read 0 | Report "Prompt-cache writes vs reads"; `test_tokenomics_log.py::test_cache_write_reuse_reports_unread_write_premium` | ✅ (4 calls) |
| Optimization (follow-up prompt-cache reuse) saves ~83% per later follow-up | Estimate only (report "Optimization worth testing next") | ❌ not tested |
| No model behavior, prompt, caching setting, or UI changed | Only `src/tokenomics.py` (not imported by the app), a script, tests, and evidence were added | ✅ |

## 20. Photo follow-up prompt-cache reuse, before/after (P35)

| Claim | Evidence | Status |
|---|---|---|
| Change is one `CachePoint()` between the image and the question in `ask_about_photo`; no prompt text, instructions, or cache options changed | `src/vision.py`; `test_followup_cache.py::test_question_comes_after_a_cache_point_that_follows_the_image`, `::test_breakpoint_is_sent_on_the_image_not_on_the_question` | ✅ |
| Baseline (current code): every follow-up wrote ~1,963 tokens and read 0 | `p35_followup_cache/results_baseline2.json`, `usage_log_baseline2.jsonl` (also `results_run1_baseline.json`) | ✅ (real calls) |
| Optimized: later questions on the same photo read 1,951 cached tokens and wrote 11–26 | `results_optimized2.json`, `usage_log_optimized2.jsonl`, `..._extra.jsonl` | ✅ (real calls, one run) |
| Estimated cost of later questions −74% (30-min writes) / −85% (12-h writes); all calls −54% / −62% | `comparison_p35.json`; `followup_cache_test_p35_report.md` | ✅ estimates, not billed amounts |
| Portkey HITs excluded from savings (deliberate repeat = HIT in both phases) | `comparison_p35.json` `checks.hits_excluded`; `test_followup_cache.py::test_saved_p35_comparison_counts_only_provider_calls` | ✅ |
| Phases did not share cache entries (first question reads 0 in both) | `checks.contamination_check_q1_reads_zero` | ✅ run 2; ❌ run 1 (kept, labeled INVALID) |
| Another photo cannot reuse the wrong context | Photo B read 0 cached tokens in both phases; `test_followup_cache.py::test_same_photo_shares_the_prefix_and_another_photo_does_not` | ✅ |
| Answers accurate, uncertainty preserved, injected sign not followed | `comparison_p35.json` `quality` (8/8 rules in both phases) and report "Answers" | ✅ (one run each, synthetic images) |
| Inventory/allocation logic and UI unchanged | Only `ask_about_photo` content changed; full suite 198 passed | ✅ |

## 21. Dashboard UI (P37)

| Claim | Evidence | Status |
|---|---|---|
| Dashboard figures are the existing tool outputs (no new business logic, no hardcoded figures) | `src/dashboard.py`; `test_dashboard.py::test_figures_are_the_existing_tool_outputs`, `::test_dashboard_follows_the_data` | ✅ |
| Summary cards: available meals, unmet demand, additional supplies, reports to check (pending and missing counted separately) | `test_dashboard.py::test_pending_and_missing_reports_are_counted_separately`; screenshot S21 | ✅ |
| Shelter cards with evacuees, needs, on hand / on its way, unmet, Plan A, shortfall, special diets, warnings | S21, S23; `test_dashboard.py::test_special_diet_shortages_and_unknown_counts_are_visible` | ✅ |
| Plan A vs Plan B: explanation tiles, paired bars, special-diet chips, collapsible table and data notes | S22; `test_dashboard.py::test_rendered_page_shows_the_figures_and_draft_status` | ✅ |
| Chart colors validated for the dark surface (magenta/blue pair passes all palette checks) | Dataviz `validate_palette.js` run (development log Stage 30) | ✅ (output not saved as a file) |
| Read-only: no data written, no finalization DB created; approval and finalization workflows unchanged | `test_dashboard.py::test_dashboard_reads_without_writing`; `app.py` diff is additive (new tab, section, callback) | ✅ |
| Browser: default tab, tab switching, Refresh, tooltips, aria-label, details, no console/server errors, 375 px layout | Stage 30 (scripted checks in the preview browser); S21–S23 | ✅ |
| Usability for real staff, screen readers | Not tested | ❌ |

## 22. Dashboard redesign (P38)

The P37 dashboard (section 21) was replaced; its screenshots S21–S23 show the earlier design.

| Claim | Evidence | Status |
|---|---|---|
| Three sections in order: current situation, actions required, allocation plan | `test_dashboard.py::test_proposed_allocations_are_never_called_approved_or_dispatched` (order check); S24, S25 | ✅ |
| Situation: three figures and a coverage bar from the existing calculations | `test_dashboard.py::test_figures_are_the_existing_tool_outputs`, `::test_dashboard_follows_the_data`; S24 | ✅ |
| Actions derived from the data, prioritized, each with what / why / next step; no warning dropped | `test_dashboard.py::test_sample_data_actions_cover_every_warning`, `::test_actions_follow_the_data_in_priority_order`, `::test_unmapped_warnings_are_never_dropped`; S24 | ✅ |
| Action buttons open the relevant tab; re-render/Refresh do not switch tabs | Browser check (Stage 31) | ✅ (browser only; no automated callback test) |
| Plan A / Plan B side by side; proposed allocations never described as approved or dispatched; special diets separate; details expandable | `test_dashboard.py::test_proposed_allocations_are_never_called_approved_or_dispatched`; S25 | ✅ |
| Read-only: nothing written | `test_dashboard.py::test_dashboard_reads_without_writing`; `data/live` CSVs identical to the sample after browser testing | ✅ |
| Mobile layout (375 px) | S26; no overflow (browser check) | ✅ |
| Understandable within 10 seconds for staff | Not measured | ❌ |

## 23. Dashboard map, fictional training layout (P39)

| Claim | Evidence | Status |
|---|---|---|
| Existing records contain no usable coordinates | `test_dashboard_map.py::test_sample_records_have_no_coordinates`; column check in Stage 32 | ✅ |
| Fictional training coordinates are clearly labeled, schematic x/y (not lat/lon), outside `data/sample/`; unlabeled files refused | `data/training_locations/fictional_training_locations.json`; `test_dashboard_map.py::test_training_locations_are_labeled_fictional_and_cover_the_sample`, `::test_unlabeled_location_files_are_refused` | ✅ |
| Map shows shelters (circles) and warehouses (squares); colors/rings show shortage, missing report, pending info | `test_dashboard_map.py::test_marker_status_comes_from_the_calculations`, `::test_markers_are_distinct_and_selection_is_highlighted`, `::test_status_follows_the_data`; S28–S30 | ✅ |
| Selecting a shelter shows validated demand, proposed Plan A, remaining shortage, warnings beside the map | `test_dashboard_map.py::test_details_panel_shows_demand_plan_a_shortage_and_warnings`, `::test_selecting_a_marker_returns_that_panel`; browser clicks on 5 markers; S28, S29 | ✅ |
| No distances, routes, travel times; no "dispatched/approved" claims | `test_dashboard_map.py::test_no_distances_routes_or_dispatch_claims`; browser text check | ✅ |
| Summary numbers kept; compact action list | S27 | ✅ |
| Calculations, records, allocation rules, approval workflows unchanged | No change to calculation modules; `data/live` CSVs identical to the sample; full suite 214 passed | ✅ |
| Touch selection on real phones | Not tested (emulated 375 px with mouse clicks only) | ❌ |
| Real-world locations | Not available; fictional layout only | ❌ by design |

## 24. Impact evaluation: accuracy, reliability, efficiency (P40)

| Claim | Evidence | Status |
|---|---|---|
| Evaluations ran on isolated copies; existing records and finalized plans unchanged | `evidence/impact/impact_eval_results.json` → `isolation` (data/live and data/sample hashes equal; no live finalization DB) | ✅ |
| Calculated needs, available stock, Plan A, and procurement match independently calculated results | `scripts/impact_eval/expected.py` (no `src/` imports); `impact_eval_results.json` → `accuracy` (6 cases, 313 fields, 0 mismatches); report section 1 | ✅ (synthetic data) |
| The evaluation's own first-run errors are disclosed | `impact_eval_results_run1.json`; report section 1 | ✅ |
| Missing reports, pending updates, unknown special-diet counts, changed validated data, rejected/pending records, invalid entry, and no inventory handled correctly in the calculations and finalization | `impact_eval_results.json` → `reliability` (R1–R7); `cases/R*/` | ✅ (45 checks passed) |
| Dashboard crashes with ≥2 unmatched data warnings (F1) | R3 and R7 `dashboard builds from this state` checks: `KeyError: 'other_note'` | ❌ found in P40 → ✅ fixed in P41 (section 25) |
| `no_stock` special diet not flagged on the Dashboard (F2) | Code reading in P40; reproduced and fixed in P41 (section 25) | ✅ fixed in P41 |
| Partial-recount rule ambiguity; the app subtracts the dispatch | R8 (exploratory) | ⚠️ rule unsettled |
| Automated planning time (ms) and AI extraction time (s), MISS vs Portkey HIT separated | `impact_eval_results.json` → `planning_efficiency`, `extraction_efficiency`; `usage_log_impact.jsonl` | ✅ (one machine, sample scale) |
| Human review time / productivity gains / real-world impact | Not measured | ❌ not claimed |

## 25. Dashboard defects F1/F2 fixed (P41)

| Claim | Evidence | Status |
|---|---|---|
| F1 and F2 reproduced before the fix | `evidence/impact/dashboard_defects_before.json` (3 crashes; "Enough in stock" for a no-stock diet; unknown shown as 0); S31 | ✅ |
| Dashboard builds with several unmatched and unexpected warnings; every warning shown with its text | `dashboard_defects_after.json`; `test_dashboard.py::test_several_unexpected_warnings_never_crash_and_all_are_shown`; S32 | ✅ |
| Known demand with zero stock labeled as a shortage | `test_dashboard.py::test_no_stock_special_diet_is_labeled_a_shortage`; S33, S34 | ✅ |
| Unknown demand distinct from confirmed zero demand | `test_dashboard.py::test_unknown_demand_is_distinct_from_confirmed_zero`; `dashboard_defects_after.json` (D5, D6) | ✅ |
| Items without any validated count labeled accurately, one action per item | `test_dashboard.py::test_items_without_any_validated_count_are_labeled_accurately` | ✅ |
| New regression tests fail on the old code | `evidence/impact/regression_tests_against_old_code.txt` (4 failed) | ✅ |
| Affected reliability tests re-run: 48 passed / 0 failed / 4 exploratory; accuracy unchanged | `evidence/impact/impact_eval_results_p41_rerun_after_fix.json` | ✅ |
| Calculations, agent, approval logic, layout unchanged; data unchanged | Only `src/dashboard.py` and `src/dashboard_view.py` changed; `data/live` and `data/sample` hashes equal | ✅ |
| Summary of reproduction, fix, and re-test | `evidence/impact/dashboard_fix_p41.md` | ✅ |

## 26. Repository audit: reproducibility and security (P42)

| Claim | Evidence | Status |
|---|---|---|
| `requirements.txt` installs everything needed to run the app and tests | Fresh venv from the git-staged files: pinned versions installed, 222 tests passed (`evidence/audit/repo_audit_p42.md` #1) | ✅ (Python 3.14.7, macOS) |
| `.env.example` documents all settings and contains no secret | `.env.example`; `test_config_env.py::test_env_example_has_no_real_secret` | ✅ |
| The key loads from the project folder or its parent (project wins; shell wins) | `test_config_env.py` (4 tests); fresh-copy check with dummy keys (#3) | ✅ |
| A fresh install seeds working data from the samples without changing them | Fresh copy on port 8052: seeded files byte-identical to `data/sample/`; sample hashes match the P27 baseline (#4) | ✅ |
| README with setup and launch instructions | `README.md`; followed in the fresh-install test | ✅; ❌ not timed with a TA |
| No key, personal data, runtime logs, or temp files in git | Scan: real key in 0 files, emails in 0, 1 home path redacted; `.gitignore`; staged-file check (#6) | ✅ |
| Tests and main app still work | 222 passed; port 8050 Dashboard and tabs fine; one real chat answer (#7) | ✅ |
| Git initialized, no remote, nothing pushed | `git init -b main`; staged only; no remote; no matching GitHub repository (#6, notes) | ✅ |

## 27. Submission cleanup and GitHub publication (P43)

| Claim | Evidence | Status |
|---|---|---|
| Temporary artifacts and exact-duplicate evidence removed (16 files) | Development log Stage 36 (list and reasons); `.gitignore` entry for `E1_planning_timing/` | ✅ |
| No key, secret, local path, live data, or personal email in the committed files or commit metadata | Stage 36 scan of all staged files; repository-local no-reply commit email | ✅ |
| Private repository created, `main` pushed (remote = local HEAD), README rendered | Stage 36 "Publication": `https://github.com/ajk723-yale/disaster-foodbridge`, anonymous HTTP 404, README with 8 sections | ✅ |
| Collaborator zlisto invited | Pending invitation (write; personal repos have no read-only role) | ⏳ zlisto must accept |

## 28. Final report (P44)

| Claim | Evidence | Status |
|---|---|---|
| `report.html` is self-contained and prints to 11 US Letter pages without clipping | `report.html`; `evidence/report/report_print_check_p44.pdf`; `evidence/report/report_review_p44.md` | ✅ |
| Every number in the report is computed from saved evidence | `scripts/report_figures_p44.py` → `evidence/report/report_figures_p44.json` | ✅ |
| One real agent run traced step by step (tool choice, tool results, reply, tokens) | `evidence/report/agent_trace_p44.json`, `agent_trace_usage_p44.jsonl`; S35, S36 | ✅ (one run) |
| Comparison with Sahana Eden, FEMA NSS, WFP LESS, ChatGPT is source-cited | Report §3 and sources [1]–[5] | ✅; ⚠️ [5] via search extracts, [2]/[3] dated |
| P40 planning-time table corrected to its saved results file | `evidence/impact/impact_eval_report.md` (note "Corrected in P44") | ✅ |
| Rubric compliance | Checked against the prompt's 8 sections; the course rubric document was not available | ⚠️ |

## 29. Report revisions (P45)

| Claim | Evidence | Status |
|---|---|---|
| The agent trace, screenshots, tool call / result, tokens, and reply all come from one app execution | `evidence/report/agent_app_run_p45.json` (run `ddf9fc62fb5a`; checks all pass), `agent_app_run_p45_usage.jsonl`, `agent_app_run_p45_reply.txt`; S39, S40 | ✅ |
| Both model calls of the traced run reached the model (no cached replay) | Usage-log `x-portkey-cache-status` MISS for both calls | ✅ |
| The P44 screenshots S35/S36 and the P45 attempt S37/S38 were Portkey cache HITs (replays of the scripted P44 run) | `data/live/usage_log.jsonl` lines 33–36 (HIT; same response IDs as `agent_trace_p44.json`) | ✅ found; those screenshots are not used in the report |
| Impact section separates technical validation from real-world impact | `report.html` §7 panels; `evidence/report/report_review_p44.md` "P45 revisions" | ✅ |
| Report still prints within 10–15 US Letter pages | `evidence/report/report_print_check_p44.pdf`: 13 pages | ✅ |

## Screenshots

Location: [`evidence/screenshots/`](evidence/screenshots/). These are byte-for-byte copies of the screenshots captured
during development (S01–S14 copied in P24; S15–S16 added in P26; S17–S19 added in P29; S20 added in P31; S21–S23 added in P37; S24–S26 added in P38; S27–S30 added in P39; S31–S34 added in P41); checksums are in [`evidence/screenshots/SHA256SUMS.txt`](evidence/screenshots/SHA256SUMS.txt).
The originals were left unchanged in Claude's session storage (`…/tool-results/mcp-Claude_Browser-blob-<id>.jpg`).
All screenshots use the **sample data** (`data/sample/`) or scratch copies of it, not real operational data.

Filename pattern: `S##_p<prompt>_stage<dev-log stage>_<topic>.jpg`. `BUG` or `WORDING-ISSUE` in a filename marks
a screenshot of a problem.

**Type:**
- ✅ **Success**: shows the intended behavior at the time.
- ⚠️ **Bug**: shows a problem that was later fixed.
- ◐ **Intermediate**: correct for that stage, but superseded by later changes.

Several screenshots were taken with the chat scrolled, so only part of a reply is visible. The **"Does not show"**
column says what each image can't be used to prove.

| ID | File | P# / Stage | Type | Shows (visible in the image) | Does not show / caveats |
|---|---|---|---|---|---|
| S01 | [S01_p06_stage04_chat-placeholder-tool-activity.jpg](evidence/screenshots/S01_p06_stage04_chat-placeholder-tool-activity.jpg) | P6 / 4 | ✅ | Black-and-pink chat; two user messages with **placeholder** replies; tool-activity panel open, reporting "0 earlier messages" and "2 earlier messages" (history reached `run_agent`) | The thinking dots, Enter-to-send, disabled Send, and error bubble (tested manually, not captured); no real AI |
| S02 | [S02_p07_stage05_first-real-agent-reply.jpg](evidence/screenshots/S02_p07_stage05_first-real-agent-reply.jpg) | P7 / 5 | ✅ | First real `gpt-6-luna` reply as plain text; it says the data tools aren't connected and gives no shelter figures | The user's question (scrolled off), token usage, the model name, and the failed first attempt |
| S03 | [S03_p08_stage06_shelter-reports-raw-markdown-BUG.jpg](evidence/screenshots/S03_p08_stage06_shelter-reports-raw-markdown-BUG.jpg) | P8 / 6 | ⚠️ Bug (display) | `get_shelter_reports` reply: validated figures for SH-01/02/03 and the pending SH-02 and SH-04 reports, but the table shows as **raw Markdown** (`\|`, `**`); tool-activity line | The tool's returned data in full; the HTTP 400 error before the Responses API switch. The figures were correct; only the display was wrong (fixed in Stage 7) |
| S04 | [S04_p09_stage07_inventory-table-rendered-counted-only.jpg](evidence/screenshots/S04_p09_stage07_inventory-table-rendered-counted-only.jpg) | P9 / 7 | ◐ Intermediate | Markdown table **rendered correctly** (fix works); inventory by category with general separate from allergy-free and infant formula; water not counted as meals; pending bread count noted | These are **counted** totals from before dispatch tracking (Stage 8); not the current "available" logic |
| S05 | [S05_p11_stage08_counted-vs-available-stock.jpg](evidence/screenshots/S05_p11_stage08_counted-vs-available-stock.jpg) | P11 / 8 | ✅ | Table: counted / dispatched since count / approved not dispatched / available: general 660/40/24/596, infant formula 20/4/0/16, allergy-free 30/0/0/30 | *Which* dispatches were left out because of a recount (WH-B cmt-001); that is in the tool output and tests, not in the image |
| S06 | [S06_p12_stage09_shelter-needs-two-tool-calls.jpg](evidence/screenshots/S06_p12_stage09_shelter-needs-two-tool-calls.jpg) | P12 / 9 | ◐ Intermediate | Per-shelter need / on hand / on the way / still needed (396/25/24/347, 186/90/30/66, 630/0/40/590); special diets listed separately; halal "unknown"; flags; **2 tool calls** (`calculate_shelter_needs`, `get_shelter_reports`) | The table header is cut off. "On the way" here does **not** yet separate approved, shipped, and delivered food (added in Stage 10) |
| S07 | [S07_p14_stage10_delivery-states-on-its-way-WORDING-ISSUE.jpg](evidence/screenshots/S07_p14_stage10_delivery-states-on-its-way-WORDING-ISSUE.jpg) | P14 / 10 | ⚠️ Wording issue | **Correct:** the table separates "24 committed, not yet shipped" (Minami) from "30 / 40 shipped, delivery not confirmed" (Kita / Higashi). **Issue:** infant formula listed as "on its way 4" although "confirmed delivered after the report" | The fix (see S08). Numbers were correct; only the label was misleading |
| S08 | [S08_p15_stage10_delivery-states-relabeled.jpg](evidence/screenshots/S08_p15_stage10_delivery-states-relabeled.jpg) | P15 / 10 | ✅ | Infant formula now "4 **confirmed delivered after the report**", separate from "committed not shipped" and "shipped, unconfirmed"; halal unknown; flags | Only the last table row (Higashi 590/0/40/0) is visible; the column headers and the Minami/Kita rows are scrolled off |
| S09 | [S09_p16_stage11_allocation-special-diets-and-warnings.jpg](evidence/screenshots/S09_p16_stage11_allocation-special-diets-and-warnings.jpg) | P16 / 11 | ✅ (partial view) | Special diets kept separate with Plan A / Plan B per diet; halal "No Plan A or Plan B figure … staff must confirm"; 4 data warnings; tool line: "DRAFT; general available 596, unmet 1003, Plan A 596, shortage 407" | The **DRAFT header and the per-shelter Plan A table (206/39/351)** are scrolled off; those figures come from the chat text capture, not this image |
| S10 | [S10_p17_stage12_supply-request-placeholders-after-fix.jpg](evidence/screenshots/S10_p17_stage12_supply-request-placeholders-after-fix.jpg) | P17 / 12 | ✅ (partial view) | After the bracket fix: placeholders shown **with brackets** (`[DELIVERY LOCATION / RECEIVING WAREHOUSE]`, `[REQUESTED DELIVERY DATE/TIME]`, `[CONTACT PHONE / EMAIL]`); pending-data list; "Nothing has been sent or finalized"; tool line "general meals to request 407" | The DRAFT header, header placeholders, and 407-meal section are scrolled off. The **bug state** (empty links) was not captured |
| S11 | [S11_p21_stage16_finalized-plan-id.jpg](evidence/screenshots/S11_p21_stage16_finalized-plan-id.jpg) | P21 / 16 | ✅ with caveat | Review & finalize tab after success: "Finalized. Plan ID: ee065f993387", 5 approved allocation lines, 3 acknowledged warnings; Finalize disabled | The acknowledgements as entered and the database contents. The time is shown as **`-04:00` local time**, from before Stage 17 switched to UTC storage and JST display |
| S12 | [S12_p21_stage16_data-changed-fresh-review.jpg](evidence/screenshots/S12_p21_stage16_data-changed-fresh-review.jpg) | P21 / 16 | ✅ | After the data changed: notice "Updated plan loaded after a data change. Previous acknowledgements were cleared."; updated Plan A (SH-01 unmet 201); special diets; warning checkboxes unticked | The "Not finalized" message (below the visible area) and the earlier value (141) for comparison |
| S13 | [S13_p21_stage16_agent-refuses-to-finalize.jpg](evidence/screenshots/S13_p21_stage16_agent-refuses-to-finalize.jpg) | P21 / 16 | ✅ | Chat: the user asks the agent to finalize and acknowledge warnings; the agent refuses and points to "Review & finalize"; no tool activity listed under the reply | That no plan was stored (checked in the database, not in the image); token usage |
| S14 | [S14_p22_stage17_saved-request-retrieved-jst.jpg](evidence/screenshots/S14_p22_stage17_saved-request-retrieved-jst.jpg) | P22 / 17 | ✅ (partial view) | Saved request for plan `3e2717444892`: "DRAFT - REQUIRES STAFF REVIEW - NOT SENT", fingerprint, "2026-10-25 04:06 JST (…+00:00 UTC record)", bracketed placeholders, 407 general meals, shelter shortfalls 141/27/239, special-diet lines | That the data changed before retrieval, or that the text matched the finalize-time view; that was checked by comparing the page text and by automated tests. The status line at the bottom is scrolled off |
| S15 | [S15_p26_stage20_intake-approved-after-corrections.jpg](evidence/screenshots/S15_p26_stage20_intake-approved-after-corrections.jpg) | P26 / 20 | ✅ | Report intake after approval: the pasted incomplete Higashi report; "Extracted (not saved). 5 warning(s). Model gpt-6-luna, 944 input / 283 output tokens."; "Saved as validated. Record ID: ext-5e9a7b773d", SH-03, 250 evacuees, report time 16:00 JST, approved by Suzuki, 6 corrected fields listed | The extracted fields and warnings **before** correction, and the refused first approval; the form is hidden after saving |
| S16 | [S16_p26_stage20_plan-needs-confirmation-after-intake.jpg](evidence/screenshots/S16_p26_stage20_plan-needs-confirmation-after-intake.jpg) | P26 / 20 | ✅ | After the approved report: "Updated plan loaded after a data change…"; Plan A table with SH-03 unmet 692, Plan A 187 / 36 / 373, shortage 509; halal `no_stock`, 18 unmet, "staff decision (no stock)" | The "Not finalized" message (below the visible area) and the old plan (590) for comparison |
| S17 | [S17_p29_stage23_photo-analysis-text-overflow-BUG.jpg](evidence/screenshots/S17_p29_stage23_photo-analysis-text-overflow-BUG.jpg) | P29 / 23 | ⚠️ Bug (layout) | WH-A analysis beside its image; the right column's text is cut off at the edge ("…24 can / case" are…", "…"20 cups"…") | The fix (S18, S19). The content itself was correct |
| S18 | [S18_p29_stage23_photo-image-beside-analysis.jpg](evidence/screenshots/S18_p29_stage23_photo-image-beside-analysis.jpg) | P29 / 23 | ✅ | After the layout fix: the stored WH-B image beside view coverage, observed facts (36 cartons, 3 cartons, "50 packs per carton"), uncertain estimates, and the start of the items table; analysis ID, time (JST), and tokens (1,867 / 629) under the image | The comparison table and the follow-ups (see S19) |
| S19 | [S19_p29_stage23_photo-comparison-and-followup-box.jpg](evidence/screenshots/S19_p29_stage23_photo-comparison-and-followup-box.jpg) | P29 / 23 | ✅ | WH-B comparison: "Needs review" for curry (36 cartons vs 30 packs, units differ) and "Possible discrepancy" for alpha rice (150 vs 120, label unverified); "not identified … none"; read-only note; the follow-up question box | The follow-up answers (below the visible area) and the image |
| S20 | [S20_p31_stage25_injection-alert-in-report-intake.jpg](evidence/screenshots/S20_p31_stage25_injection-alert-in-report-intake.jpg) | P31 / 25 | ✅ | Report intake with P30 Attack A pasted: "9 warning(s)… 1520 input / 879 output tokens (extraction + safety screen)"; red alert "this report contains text that looks like instructions to the AI or software… They were not followed" with the 5 flagged sentences and their source (pattern / pattern+model) | The extracted field values (75, 40, `halal:?`) and the original text, which are below the visible area (checked in the page) |
| S21 | [S21_p37_stage30_dashboard-summary-and-shelter-cards.jpg](evidence/screenshots/S21_p37_stage30_dashboard-summary-and-shelter-cards.jpg) | P37 / 30 | ✅ | Dashboard tab (1280 px): summary cards 596 available, 1,003 unmet, 407 to request, 3 items to check; shelter cards SH-01–SH-03 with stacked meal bars, "Short after Plan A" badges, special-diet chips, warnings; SH-04 "No validated report" | Working data identical to the sample data; SH-04 card text cut off at the bottom |
| S22 | [S22_p37_stage30_plan-a-vs-plan-b-with-table-and-notes.jpg](evidence/screenshots/S22_p37_stage30_plan-a-vs-plan-b-with-table-and-notes.jpg) | P37 / 30 | ✅ | Plan A vs Plan B tiles (596 sent, ~59%, 407 short / 1,003 total), paired bars per shelter, special-diet chips (halal needs confirmation), expanded table with totals, data notes | Only the first data notes are visible |
| S23 | [S23_p37_stage30_dashboard-mobile-375px.jpg](evidence/screenshots/S23_p37_stage30_dashboard-mobile-375px.jpg) | P37 / 30 | ✅ | 375 px phone layout after the tab-wrap fix: tabs on two rows, single-column cards, meal bar and chips | The clipped-tab state before the fix was not saved |
| S24 | [S24_p38_stage31_situation-and-actions.jpg](evidence/screenshots/S24_p38_stage31_situation-and-actions.jpg) | P38 / 31 | ✅ | Redesigned dashboard (1280 px): Current situation 596 / 1,003 / 407 (red), coverage bar 59% with "407 meals not covered"; Actions required (4): SH-04 no validated report, SH-03 halal count unknown, SH-02 newer report waiting, each with why / next step / "Open Report intake →" | The 4th action (inventory count) is below the visible area |
| S25 | [S25_p38_stage31_allocation-plan-a-vs-b.jpg](evidence/screenshots/S25_p38_stage31_allocation-plan-a-vs-b.jpg) | P38 / 31 | ✅ | Allocation plan: "Proposed only" note, legend, Plan A (596 proposed · 407 still short) and Plan B (1,003 proposed · 407 must be procured) side by side with per-shelter bars; special-diets table (halal count unknown); collapsed Shelter details / Assumptions sections | Expanded sections not shown; "All data notes" is below the visible area |
| S26 | [S26_p38_stage31_dashboard-mobile-375px.jpg](evidence/screenshots/S26_p38_stage31_dashboard-mobile-375px.jpg) | P38 / 31 | ✅ | 375 px phone layout: stacked figures, coverage bar, start of the action list | The plan section on mobile is not in the image |
| S27 | [S27_p39_stage32_situation-and-compact-actions.jpg](evidence/screenshots/S27_p39_stage32_situation-and-compact-actions.jpg) | P39 / 32 | ✅ | Dashboard top: Current situation 596 / 1,003 / 407 with 59% coverage bar; compact Actions required (4): title + next step + "Open Report intake →"; start of the Map section | The map itself is below the visible area |
| S28 | [S28_p39_stage32_map-shelter-selected-SH-03.jpg](evidence/screenshots/S28_p39_stage32_map-shelter-selected-SH-03.jpg) | P39 / 32 | ✅ | Map with "FICTIONAL TRAINING LAYOUT — not real locations" label, red shelter markers with amber rings (SH-02, SH-03), amber SH-04, square warehouses (WH-A ringed); SH-03 selected (pink ring); panel: Short after Plan A, 590 unmet, 351 Plan A (proposed), 239 remaining shortage, halal count unknown; legend | Taken before the label was split onto two lines ("· no distances or routes" on one line); panel issues scrolled below |
| S29 | [S29_p39_stage32_map-missing-report-SH-04.jpg](evidence/screenshots/S29_p39_stage32_map-missing-report-SH-04.jpg) | P39 / 32 | ✅ | SH-04 selected: "No validated report" status and its issue with why / next step / "Open Report intake →"; hover tooltip visible | Map label still the one-line version |
| S30 | [S30_p39_stage32_map-mobile-375px-SH-01.jpg](evidence/screenshots/S30_p39_stage32_map-mobile-375px-SH-01.jpg) | P39 / 32 | ✅ | 375 px: map stacked above the panel; SH-01 selected (347 meals unmet); two-line fictional label (scrolled just out of view) | Hover tooltip overlaps the SH-01 label; selection made by mouse click in phone emulation, not real touch |
| S31 | [S31_p41_stage34_BEFORE-dashboard-crash-R3-state-BUG.jpg](evidence/screenshots/S31_p41_stage34_BEFORE-dashboard-crash-R3-state-BUG.jpg) | P41 / 34 | ⚠️ Bug | Old code on the isolated R3 state (port 8051): "Dashboard could not be built: KeyError: 'other_note'", empty map | Isolated evaluation copy, not the working data |
| S32 | [S32_p41_stage34_AFTER-dashboard-R3-state-actions.jpg](evidence/screenshots/S32_p41_stage34_AFTER-dashboard-R3-state-actions.jpg) | P41 / 34 | ✅ | Same state after the fix: 596 / 988 / 392; "⛔ Not enough halal meals: 15 short" first in red; "Data note: SH-03 (general): 40 meals (cmt-003) …" with its text | The rest of the data note is cut off at the bottom |
| S33 | [S33_p41_stage34_AFTER-special-diet-no-stock-labeled-shortage.jpg](evidence/screenshots/S33_p41_stage34_AFTER-special-diet-no-stock-labeled-shortage.jpg) | P41 / 34 | ✅ | Allocation plan and special-diet table: "Halal 15 0 ⛔ 15 short (none in stock)"; "All data notes (5)" | Expanded data notes not shown |
| S34 | [S34_p41_stage34_AFTER-map-panel-SH-03-halal-shortage.jpg](evidence/screenshots/S34_p41_stage34_AFTER-map-panel-SH-03-halal-shortage.jpg) | P41 / 34 | ✅ | Map with SH-03 selected: 575 unmet, 347 Plan A (proposed), 228 shortage; "Halal: 5 people · 15 meals unmet"; the start of the Issues list | The issue entries are below the panel's visible area (checked as text in the browser) |
| S35 | [S35_p44_stage37_chat-allocation-draft-reply.jpg](evidence/screenshots/S35_p44_stage37_chat-allocation-draft-reply.jpg) | P44 / 37 | ✅ | Chat: "Prepare a food allocation plan for the next 24 hours." → "DRAFT — for staff review only", planning basis, general-meals table (Plan A 206/39/351, shortfall 141/27/239, Plan B 347/66/590, totals 596/407/1,003), "Plan B requires 407 additional general meals" | **Portkey cache HIT** (replay of the scripted P44 run, found in P45); not an independent model decision; no longer used in the report |
| S36 | [S36_p44_stage37_chat-allocation-warnings-tool-activity.jpg](evidence/screenshots/S36_p44_stage37_chat-allocation-warnings-tool-activity.jpg) | P44 / 37 | ✅ | End of the same reply: special diets (halal unknown, staff must confirm), 4 data warnings, and "Tool activity (2)" with `calculate_allocation` and `calculate_shelter_needs` and their result summaries | Same **Portkey cache HIT** run as S35 (found in P45); no longer used in the report |
| S37 | [S37_p45_stage38_app-run-allocation-draft-reply.jpg](evidence/screenshots/S37_p45_stage38_app-run-allocation-draft-reply.jpg) | P45 / 38 | ⚠️ | App run of "Prepare a food allocation plan for the next 24 hours." (top of reply) | **Portkey cache HIT** (replay); kept as a record; not used in the report |
| S38 | [S38_p45_stage38_app-run-warnings-tool-activity.jpg](evidence/screenshots/S38_p45_stage38_app-run-warnings-tool-activity.jpg) | P45 / 38 | ⚠️ | Same HIT run: special diets, warnings, tool activity (2 calls) | **Portkey cache HIT**; not used in the report |
| S39 | [S39_p45_stage38_traced-run-ddf9fc62-reply-top.jpg](evidence/screenshots/S39_p45_stage38_traced-run-ddf9fc62-reply-top.jpg) | P45 / 38 | ✅ | **Traced run `ddf9fc62fb5a`** (both calls MISS): "Please draft a food allocation plan for the next 24 hours." → "DRAFT — for staff review; not finalized", Plan A 206/39/351 with shortfalls 141/27/239, Plan B 347/66/590, "Additional general meals to procure: 407" | Lower part of the reply is in S40 |
| S40 | [S40_p45_stage38_traced-run-ddf9fc62-warnings-tool-activity.jpg](evidence/screenshots/S40_p45_stage38_traced-run-ddf9fc62-warnings-tool-activity.jpg) | P45 / 38 | ✅ | Same run: special diets (halal unknown), 4 data warnings, "Tool activity (1)" with `calculate_allocation` and its result summary | — |

**Not captured** (no screenshot exists): the P26 extracted fields before correction and the refused approval; the P6 thinking dots and error bubble; the P8 HTTP 400 error bubble; P17's first
run with empty-link placeholders; the P21 "Not finalized" guard messages; the P22 saved request with the wrong status line.

---

## Evidence still to collect (checklist)

- [x] Copy screenshots S01–S14 into the project: done in P24 (`evidence/screenshots/`, with SHA256SUMS.txt).
- [ ] Optional: capture screenshots of the states listed under "Not captured" if the report needs them.
- [ ] Save a full pytest run (`pytest -v`) to a dated file.
- [ ] Save server logs from a scripted set of chat questions to get verifiable token usage (the chat figures in
      section 4 are from unsaved session logs). The P25 extraction run's usage **is** saved (section 10).
- [ ] Screenshots of extraction results: none (the P25 run was script-based, not in the UI).
- [ ] An extraction accuracy check on a larger, labeled set of reports, if the report needs accuracy claims.
- [ ] Recreate and save the before/after scenario outputs for dispatch double-counting (P10) and the finalization
      probes (P18). Both scripts were deleted.
- [ ] A real-model chat check with **no validated data** (does the agent say so?).
- [ ] A chat check that shows a **delayed-delivery** warning (needs sample data with such a case).
- [ ] An automated end-to-end UI test, or a recorded run, of Review & finalize.
- [ ] Re-run and save the secret scan and the hardcoded-quantity scan.
- [x] Save the sample-data hash baseline: done in P27 ([`evidence/data_integrity/sample_sha256_baseline_p27.txt`](evidence/data_integrity/sample_sha256_baseline_p27.txt)).
- [ ] `pip freeze` of the project venv; consider pinning `requirements.txt`.
- [ ] Verify whether Portkey cached the repeated P17 request.
- [ ] Vision on **real** warehouse photos with a labeled ground truth (P28 used only synthetic drawings).
- [ ] Prompt-injection tests beyond P31: repeated runs; paraphrased, Japanese, and obfuscated attacks against the **real** model screen; a larger benign set for a false-positive rate; injection via shelter names, photos (vision), chat, and supply-request drafting.
- [x] Record cached / cache-write / reasoning tokens per call and save chat usage: done in P33 (usage log).
- [x] Recompute tokenomics from the usage log: done in P34 (section 19).
- [ ] Obtain the Portkey account's billing (are HITs billed? actual rates?) and measure per-user activity.
- [x] Test the photo follow-up prompt-cache optimization: done in P35 (section 20).
- [ ] Repeat the P35 follow-up test on real warehouse photos and with more runs per question.
- [ ] Any user or staff feedback: **none collected so far**.
- [x] Automated timing measurements: done in P40 (section 24). Human review time still **not measured**.
- [x] Fix and re-test dashboard defects F1/F2 found in P40: done in P41 (section 25).
- [ ] Update `project_spec.md`, which is out of date since P5, before citing it.
