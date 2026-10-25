# P51 Fresh-clone re-test with the revised README (2026-10-25)

This re-test checks the README fix made after the P50 test (`fresh_clone_test_p50.md` §2). The fixed README was
pushed first as commit `87fd5d8`, so the clone command in the README could be followed exactly against GitHub.

- **Layout:** a new temporary folder `<tmp>/ta_parent/`, unrelated to the P50 folder.
  - It held `.env` (mode 600, one line `PORTKEY_API_KEY=…`). The value was never printed, and the file was deleted
    after the test.
  - The repository was cloned inside it, as the README now says.
- **Clean environment:** every command ran under `env -i HOME=… PATH=/opt/homebrew/bin:/usr/bin:/bin`, with
  `PIP_NO_CACHE_DIR=1` and a new venv. No shell key, no development venv, data, or cache was used.
- **Usage records:** `fresh_clone_p51_usage.jsonl` is the clone's own `data/live/usage_log.jsonl`.

## 1. Commands (the revised Quick start, verbatim) and time

| Elapsed at start | Command |
|---|---|
| 0.0 s | `git clone https://github.com/ajk723-yale/disaster-foodbridge.git` (cloned `87fd5d8`) |
| 1.1 s | `cd disaster-foodbridge` |
| 1.1 s | `python3.14 -m venv .venv` |
| 2.8 s | `.venv/bin/pip install -r requirements.txt` (no cache) |
| 23.0 s | setup done |
| +10.4 s | `.venv/bin/python app.py`: first `GET /` answered 200 (the server log timestamp minus the launch timestamp; this was the first start, with byte-compilation of the new venv) |

**Total: 33.4 s, within the 10-minute rule.** No other step was needed:
- no `.env` was created in the repository;
- the `cp .env.example .env` step is no longer part of this setup;
- no workaround was used.

A person's reading and typing time and slower networks are not included.

## 2. Key loading

- `config.ENV_FILES_LOADED = ['<tmp>/ta_parent/.env']`: only the parent file.
- The placeholder key was not in use.
- No `.env` existed inside the clone, and the clone's `git status` was clean.

## 3. Dashboard

On first start (seeded from `data/sample/`): 596 available general meals, 1,003 total unmet demand, 407 additional
meals needed, and 4 actions required, matching P50 §3.

## 4. One real, uncached `gpt-6-luna` request

- Question (new wording): "Revised-README clone check: how many general meals are in validated stock right now, and
  what is the total unmet demand across shelters?"
- Tool calls (server log): `get_warehouse_inventory` and `calculate_shelter_needs` (2 tool calls in 2 model
  requests).
- Tool results:
  - general counted 660, dispatched since count 40, reserved 24, **available 596**;
  - **total unmet 1,003** (347 / 66 / 590).
- Reply: "Validated general stock: 660 counted meal equivalents; 596 available after subtracting 40 dispatched and 24
  approved but not yet dispatched. … General unmet demand: 1,003 meals across shelters …", plus special diets and
  data warnings.
- Usage records (run `e248b4f67067`): 2 calls, both HTTP 200, `model_reported gpt-6-luna-global`,
  `x-portkey-cache-status` **MISS**:
  - call 0: 1,860 input / 84 output tokens;
  - call 1: 3,988 input / 422 output tokens.
- Provider cached-read tokens were 1,825 and 1,857. These come from the provider's prompt cache for the shared
  system prompt and tool definitions. That is input-token caching on a real model call, not a Portkey response
  replay (which would show `HIT`).

## 5. Other checks

- Tests in the clone: `.venv/bin/python -m pytest -q` → **222 passed** (run with `-p no:cacheprovider`).
- Development `data/live/` was not touched: its file times are before the test.
- No app code changed between `e07a942` (P50) and `87fd5d8`; only documentation, the report, the slides, their
  build scripts, and evidence changed.
- Not repeated here: the intake, photo, and finalize workflows (P50 §5) and the independence checks (P50 §6). The
  app code is unchanged since then.

## 6. Result

The revised README works for the grading setup. A grader can clone into the folder that holds their `.env`, run four
commands, and use the AI features with no workaround. **Ready for grading.**
