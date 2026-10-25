# Data folders

| Folder | Purpose | In git |
|---|---|---|
| `sample/` | Made-up seed data and test inputs. **Read-only for the app**: any write into it is refused. | yes |
| `live/` | Working data the app reads and writes: `shelter_log.csv`, `inventory_log.csv`, `commitments_log.csv`, `finalization.db`. | no (`.gitignore`) |
| `templates/` | Header-only CSV templates. | yes |
| `uploads/` | Reserved for uploaded files. | no |

**First setup.** When the app starts, each missing working log in `live/` is copied from `sample/`. Existing
working files are never overwritten, so restarts keep approved reports, finalized plans, and dispatch records. To
start over from the sample data, stop the app and delete the files in `live/`.

Allocation, review, finalization, and the agent's tools all use the same working files. Settings: `LIVE_DATA_DIR`
(default `data/live`) and `SEED_DATA_DIR` (default `data/sample`); per-file overrides such as `SHELTER_LOG_PATH`
still exist.

Note: `sample/README.md` still shows an older command that points the app directly at `sample/`. With the write
guard, such a setup can read the sample files, but approving a report or finalizing is refused.
