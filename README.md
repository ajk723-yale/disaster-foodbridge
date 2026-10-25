# Disaster FoodBridge

An AI-assisted web app (Dash) that helps municipal emergency staff coordinate food distribution to evacuation
shelters. It reads validated shelter reports and warehouse counts and drafts allocation plans:
- Plan A shares the available stock;
- Plan B meets all needs and lists what must be procured.

It also helps staff review AI-extracted shelter reports and warehouse photos, and lets staff finalize a plan. The
AI never approves or finalizes anything: every record and plan needs a staff decision.

All data in this repository is **synthetic**: made-up shelters and warehouses, fictional map positions, and drawn
test images.

## Quick start (about 5–10 minutes)

**Requirements**
- **Python 3.14** (tested with 3.14.7);
- **macOS or Linux** (the logs use `fcntl` file locking, so Windows is not supported);
- a **Portkey API key** with access to `gpt-6-luna`.

The app starts without a key, but the AI features then show a "PORTKEY_API_KEY is not set" message.

```bash
cd final_project
python3.14 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env            # then edit .env and set PORTKEY_API_KEY
.venv/bin/python app.py
```

Open **http://localhost:8050**. Stop the app with `Ctrl+C` in that terminal. Debug mode and the auto-reloader are
off, so there is a single process.

**Where the key can live.** The app reads `.env` from the project folder first, then from its parent folder (for
example a course folder that holds several projects). A variable already set in your shell wins over both files. The
key is never printed or logged.

**First start.** The working data is created automatically: each missing file in `data/live/` is copied from
`data/sample/`. The sample files are never modified, and the app refuses to write into `data/sample/`.

## Run the tests

```bash
.venv/bin/python -m pytest -q
```

The tests make no model calls and use temporary data, so no key is needed. Expected: all tests pass (222 at the
time of writing).

## What to try

| Tab | What it does | Changes working data? |
|---|---|---|
| 📊 **Dashboard** (opens first) | Current situation (available meals, unmet demand, meals to procure); a prioritized "Actions required" list with buttons to the right tab; a map of shelters and warehouses on a **fictional training layout** with a details panel; Plan A vs Plan B | No (read-only) |
| **Chat** | Ask about shelters, inventory, needs, Plan A/B, or a draft supply request, e.g. "Which shelters have special dietary needs?" | No (model call only) |
| **Report intake** | Paste a free-text shelter report (examples in `data/sample/free_text_reports.json`), extract fields with AI, correct them, and approve | Yes, **after approval**: adds a validated row to `data/live/shelter_log.csv` |
| **Warehouse photos** | Upload a photo (examples in `data/sample_photos/`), choose the warehouse, analyze, and ask follow-up questions | Stores the image copy and analysis in `data/live/photos/`; inventory is not changed |
| **Review & finalize** | Load Plan A, acknowledge each data warning with a reason, enter your name, and finalize | Yes: saves the plan, approvals, and a draft supply request in `data/live/finalization.db` |

Every AI action also adds one line to `data/live/usage_log.jsonl`. It holds token counts only: no prompts, report
text, images, or keys.

**Reset the demo.** Stop the app, delete the working copies, and start again. The sample files are untouched.

```bash
rm -f data/live/*.csv data/live/finalization.db* && rm -rf data/live/photos
```

## Configuration

All settings are optional except the key; see [`.env.example`](.env.example). They include the planning defaults (3
meals per person per day, 24-hour window), the display timezone (Asia/Tokyo), agent limits, and data paths.

## Project layout

| Path | Contents |
|---|---|
| `app.py` | Dash app: layout and callbacks |
| `src/` | Calculations (`allocation.py`, `planning.py`, `drafts.py`), records and validation, finalization (SQLite), AI agent and tools, report extraction, injection screening, photo analysis, usage logging, dashboard and map |
| `tests/` | pytest suite (offline) |
| `data/sample/` | Synthetic seed data (read-only for the app); `data/sample_photos/` synthetic images; `data/training_locations/` fictional map positions |
| `data/live/` | Working data created on first start (**not in git**) |
| `scripts/` | Evaluation and evidence scripts (some make real model calls; for the image scripts install `requirements-dev.txt`) |
| `evidence/` | Saved results, screenshots, and logs from development and evaluation (synthetic data; no keys) |
| `AI_prompts.md`, `development_log.md`, `evidence_index.md` | The prompts used, a factual development log (tested vs implemented), and an index of claims to evidence |
| `project_spec.md` | The original specification (**out of date since P5**; see the development log) |

## Not in git

- `.env` (keys);
- `.venv/`, caches, and temporary files;
- `data/live/` (working records, finalization database, stored photos, runtime usage log);
- `data/uploads/`;
- local editor and tool folders.

The `evidence/` folder **is** committed on purpose. It contains synthetic results and per-call usage snapshots
(token counts, request IDs), with no keys or personal data.

## Known limitations

- Synthetic data only; the map positions are fictional and show no distances or routes.
- No staff accounts or authentication.
- Some actions are not available in the UI: validating existing pending records, entering inventory counts, and
  recording dispatches or deliveries.
- Human review time and real-world impact have not been measured. See `evidence/impact/`.
- `data/sample/README.md` shows an older command that points the app directly at `data/sample/`. It is kept
  unchanged because the sample folder is protected; use the Quick start above instead.

More detail: `development_log.md` → "Current limitations".
