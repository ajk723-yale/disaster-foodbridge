# P50 Final fresh-clone test (2026-10-25)

Goal: reproduce the teaching staff's setup. Clone `main` from GitHub into a new temporary folder, put a `.env` with
only `PORTKEY_API_KEY` one level above the clone, follow the published README, and check that the app runs in under
10 minutes.

- **Tested commit:** `e07a942` (remote `main` at test time). The P49 report/slide corrections were not committed, so
  they are not in this clone; they do not touch the app.
- **Layout:** `<tmp>/ta_parent/.env` (mode 600, one line `PORTKEY_API_KEY=…`; the value was never printed) and
  `<tmp>/ta_parent/disaster-foodbridge/` (the clone). `<tmp>` was a new scratch folder outside the development
  folder. The temporary `.env` was deleted after the test.
- **Clean environment:** every command ran under `env -i HOME=… PATH=/opt/homebrew/bin:/usr/bin:/bin` (so no
  `PORTKEY_API_KEY` from the shell), with `PIP_NO_CACHE_DIR=1` (no pip cache) and a new venv. No development
  venv, data, or cache was used.
- **Model usage:** `fresh_clone_p50_usage.jsonl` is the clone's own `data/live/usage_log.jsonl`, copied after the
  test.

## 1. Setup time (README commands)

| Step | Command | Elapsed |
|---|---|---|
| Clone | `git clone https://github.com/ajk723-yale/disaster-foodbridge.git` (**not in the README**) | 1 s |
| Enter folder | `cd disaster-foodbridge` (**README says `cd final_project`**, which does not exist after a clone) | 0 s |
| venv | `python3.14 -m venv .venv` | 2 s |
| Install | `.venv/bin/pip install -r requirements.txt` (no cache) | 20 s |
| Key file | `cp .env.example .env` | 0 s |
| **Setup commands total** | | **23 s** |
| Launch | `.venv/bin/python app.py` → first HTTP 200 on `http://localhost:8050` | ≤ 8 s (an upper bound; it includes tool polling delay) |

**Total: about 31 s of command time, well within the 10-minute rule.** Not included: a person's time to read the
README and type the commands, and slower networks (the install downloads about 40 packages).

## 2. Defect found: the README's `cp .env.example .env` step breaks the parent-folder key

Following the README literally, `cp .env.example .env` creates a project `.env` that contains the placeholder
`PORTKEY_API_KEY=your-portkey-api-key-here`. The README then says "edit .env and set PORTKEY_API_KEY", but a grader
whose key lives in the parent `.env` has nothing to put there. Because the app reads the project `.env` first and
does not override values already set, **the placeholder wins over the real key in the parent `.env`.**

- Observed: `config.ENV_FILES_LOADED = [<clone>/.env, <tmp>/ta_parent/.env]`; the key in use was the placeholder.
- Effect: the dashboard works, but every AI action fails. Chat showed "Something went wrong: The AI service
  returned an error (HTTP 401)". The usage log records `http_status 401` (run `2250dcfce04c`).
- **Workaround used:** delete the copied project `.env` (`rm .env`). After a restart,
  `ENV_FILES_LOADED = [<tmp>/ta_parent/.env]` and the real key was used. The README's "Where the key can live"
  paragraph implies this, but the Quick start does not say to skip the copy.
- Not fixed in this test (the prompt asked to test and report).

## 3. Dashboard (synthetic sample data)

Directly after first start (working data seeded from `data/sample/`):
- Current situation: **596** available general meals, **1,003** unmet demand, **407** additional meals needed,
  "Current stock covers 59% of unmet demand".
- Actions required: **4** (SH-04 no validated report; SH-03 halal count unknown; SH-02 newer report pending;
  WH-A canned-bread recount not validated).
- Map: 2 warehouses and 4 shelters, labeled "FICTIONAL TRAINING LAYOUT — not real locations".
- Plan A: Minami 206 / Kita 39 / Higashi 351, labeled "Proposed only".

## 4. Chat Agent: one real, uncached request

- Question (new wording): "Fresh-clone check on Oct 25: under Plan A, how many general meals does each shelter
  get, and how many meals must still be procured overall?"
- Tool call (server log): `calculate_allocation args={}`, one tool call, 2 model requests.
- Tool result: available 596, unmet 1,003, Plan A 206 / 39 / 351, shortage 407, plan fingerprint
  `9ac32e325eae…`, matching the sample-data figures of P40 case A1.
- Reply: "DRAFT for staff review — not finalized. … Minami Elementary School: 206 meals; Kita Community Center: 39
  meals; Higashi Junior High Gym: 351 meals. General meals to procure: 407. …", plus the 5 data warnings.
- Usage records (run `563da346c58c`): two calls, both HTTP 200, `model_reported gpt-6-luna-global`,
  `x-portkey-cache-status` **MISS**:
  - call 0: 1,865 input / 15 output tokens;
  - call 1: 2,642 input / 295 output tokens, of which 1,862 were provider cached-read tokens (the prompt cache
    within the run, not a Portkey replay).

## 5. Other workflows (synthetic test inputs; clone data only)

All model calls were Portkey **MISS** (see the usage file).

**Report intake**
- New report text: "Fresh-clone test report (synthetic). Kita Community Center (SH-02), checked at 13:40 on Oct
  24. We now have 71 people … About 20 general meals … Two residents still need allergy-free meals; we hold 4…".
- Extraction found SH-02, Kita Community Center, 71 people, `allergy_free:2`, and `allergy_free:4` on hand. It left
  two fields blank, each with a warning: general meals ("About 20" is approximate) and report time (no year given).
- As staff, I set the time to `2026-10-24T13:40+09:00`, the meals to 20, and the name "Fresh-clone tester", ticked
  the confirmation, and approved.
- Result: saved as validated record `ext-97a0ebac23`, with the corrected fields listed.
- Model calls: extraction 967 / 601 tokens; safety screen 403 / 38 tokens.

**Warehouse photos**
- Input: a 1000×760 center crop of the synthetic `data/sample_photos/synthetic_wh_b_bay1.png`. The crop was made
  outside the clone, so the image bytes were new to Portkey. Warehouse WH-B.
- Analysis `photo-e393cad2cf` was saved with its image, and the inventory did not change.
  - It described a partial view.
  - It read "ALLERGEN-FREE CURRY RICE" (30 cartons) and "ALPHA RICE (RETORT) 50 packs per carton" (2 full + 1
    partial).
  - It counted 6 unreadable cartons.
  - It noted that the warehouse identity is not visible in the image.
  - Findings: 1 not comparable, 1 needs review, 2 inconclusive.
  - Tokens: 1,540 / 1,590.
- Follow-up question: "how many alpha rice cartons are fully inside the frame versus cut off at the edge?"
  - Answer: "Two … fully inside the frame, and one is cut off at the right edge."
  - Tokens: 1,721 / 54.
- Upload method: the file was supplied through Dash's `set_props` on the `dcc.Upload` component, because the
  preview browser cannot open a file dialog. The app callbacks are the same as for a manual upload.

**Review & finalize**
- The loaded plan reflects the new SH-02 report: unmet 1,094; Plan A 189 / 86 / 321; shortage 498. The earlier
  "SH-02 newer report pending" warning is gone.
- I acknowledged the 2 warnings (SH-04 no report; WH-A bread recount) with reasons, entered a name, ticked the
  confirmation, and finalized.
- Result: plan **`93c8305626fa`** was finalized with 5 approval lines and 2 acknowledged warnings. A draft supply
  request (498 general meals, "DRAFT - REQUIRES STAFF REVIEW - NOT SENT") was saved.
- "Show saved request" reloaded the saved request from `finalization.db`.

## 6. Independence from the development folder

| Check | Result |
|---|---|
| Clone process open files (`lsof`) referencing the development folder | 0 |
| Python packages loaded from | only `<clone>/.venv` (venv built from Homebrew `python3.14`) |
| Process environment | `HOME`, `PATH` (plus macOS's `__CF_USER_TEXT_ENCODING`, `__PYVENV_LAUNCHER__`); no `PORTKEY_*` |
| `.env` files loaded (after the workaround) | only `<tmp>/ta_parent/.env` |
| Data paths in `config` | all under `<clone>/data/…` |
| Absolute paths to the developer's home or `AI code/final_project` in the clone (excluding `.venv`, `.git`) | 0 files |
| Development `data/live/` | file times before the test (last change 2026-10-25 04:04 local); not touched |
| Development git working tree | unchanged by the test (only the uncommitted P49 edits) |
| Clone `git status` after all workflows | clean (`data/live/` is ignored); `data/sample/` identical to `HEAD` |

## 7. Python and dependency compatibility

- **Python 3.14.7 (macOS, Homebrew):** all pinned packages installed from PyPI without a cache, and `pip check`
  reported no broken requirements. Installed versions: dash 4.4.1, plotly 7.1.0, pandas 3.1.0, python-dotenv 1.2.4,
  openai 3.37.0, pydantic-ai-slim 2.61.0, portkey-ai 2.3.4, pytest 9.1.1, pydantic 2.14.1.
- **Tests in the clone:** `.venv/bin/python -m pytest -q` → **222 passed** in 6.0 s (run with
  `-p no:cacheprovider` so nothing was written into the clone).
- **Python 3.13.15:** a `pip install --dry-run -r requirements.txt` resolved without errors. **The app was not run on
  3.13**; the README states 3.14.
- **Not tested:** Linux and Windows (the README already says Windows is unsupported because of `fcntl`).

## 8. Verdict

The fresh clone installs and starts in well under 10 minutes, and the dashboard shows the synthetic sample data.
Chat, report intake, photo analysis with a follow-up, and Review & finalize all worked with real `gpt-6-luna` calls,
none of them cached. The clone does not depend on the development folder.

**One blocking README issue for the grading setup:** following the Quick start literally (`cp .env.example .env`)
hides the parent-folder key, and all AI features fail with HTTP 401. Two smaller documentation gaps:
- there is no clone command;
- the README says `cd final_project` instead of `cd disaster-foodbridge`.

Ready for grading once the Quick start is corrected, or if graders skip the copy step.

*Follow-up (P51):* the README defects above were fixed in commit `87fd5d8`. A new fresh clone using only the revised
instructions worked without the workaround; see `fresh_clone_test_p51.md`.
