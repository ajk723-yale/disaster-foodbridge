# P42 Repository audit: reproducibility and security (2026-10-24)

| # | Check | Finding before | Action | Result after (verified) |
|---|---|---|---|---|
| 1 | `requirements.txt` has every dependency | Unpinned; `plotly` is imported directly (`src/dashboard_map.py`) but was not listed (it only came in through Dash); `pillow` and `pyflakes` (scripts/lint only) were not listed | Pinned the 8 runtime and test packages to the tested versions and added `plotly`; new `requirements-dev.txt` with `pillow` and `pyflakes` for the evaluation scripts | A fresh venv from `requirements.txt` alone installed in 18 s (pip cache warm) and **222 tests passed** in it |
| 2 | `.env.example` documents config without secrets | Placeholder only, but several settings were undocumented (`PORT`, `REPORT_TIMEZONE`, per-file paths, `USAGE_LOG_PATH`, `TRAINING_LOCATIONS_PATH`) and the .env location was not explained | Documented every setting the code reads, the lookup order, and the behavior without a key | `tests/test_config_env.py::test_env_example_has_no_real_secret` |
| 3 | API key from the project folder or its parent | `load_dotenv()` searched upward from `src/` through **all** parent folders, so it could pick up an unrelated `.env`; precedence was undocumented | `config.load_env()` reads only `<project>/.env`, then `<parent>/.env`; values already set in the shell always win | Unit tests: parent only, project wins over parent, shell wins, no file is fine. Fresh copy with the shell variable removed: no key → unset; dummy parent `.env` → loaded; dummy project `.env` → wins (dummy files deleted afterwards) |
| 4 | A fresh install initializes working data safely | Not tested from a clean copy before | Exported exactly the git-staged files to a clean folder (no `.env` above it) and started the app on port 8052 with the shell's key removed | Log: "working data seeded" for the 3 CSVs; seeded files byte-identical to `data/sample/`; sample hashes match the P27 baseline; Dashboard 596 / 1,003 / 407, 4 actions, 6 map markers; Chat without a key showed "PORTKEY_API_KEY is not set. Add it to .env (see .env.example)" |
| 5 | README a TA can follow in under 10 minutes | **No README** in the project (only `data/README.md`) | New `README.md`: requirements (Python 3.14, macOS/Linux, Portkey key), 5-command quick start, key location, first start, tests, what each tab does and what it changes, demo reset, configuration, layout, what is not in git, known limitations | Steps followed in the fresh-install test. The "under 10 minutes" target was **not timed with a TA** |
| 6 | Keys, personal data, runtime logs, temp files excluded from git | No git repository yet; `.gitignore` lacked `*.log`, temporary files, and local tool folders. Scan of all project files: the real key value found in **0** files, key-like patterns in **0**, emails in **0**; **1** file had a home-folder path (`evidence/impact/dashboard_defects_before.json`, in saved tracebacks) | Redacted the path to `<project>/` (12 occurrences) and made the script do this itself; extended `.gitignore` | `git init`; 306 files staged at audit time. None is `.env`, `.venv`, a cache, `data/live/*` (except `.gitkeep`), `data/uploads/*`, `.DS_Store`, or a local tool folder. `evidence/` is committed on purpose (synthetic results and usage snapshots with token counts and request IDs, no keys or personal data) |
| 7 | Tests and main app still work | — | — | Project venv: **222 passed**. Main app on port 8050 restarted on the new config: Dashboard renders, all 5 tabs switch, no server errors; one real chat question answered "596 general meals are available…" |

## Notes

- **Shell environment.** `PORTKEY_API_KEY` is also exported in this machine's shell environment (outside the
  repository), and it wins over any `.env`. The no-key check therefore had to remove it explicitly (`env -u`).
- **Platform.** The app uses `fcntl`, so it runs on macOS and Linux only; the README says so. Only Python 3.14.7 was
  tested (the other interpreter on this machine is 3.9, which is too old).
- **Not changed.** `data/sample/README.md` still shows an older command, and `project_spec.md` is out of date. Both
  are flagged in the README; the sample folder is protected byte-for-byte.
- **Git.** The repository was initialized on branch `main`, files are **staged but not committed**, and the git
  identity is configured globally. There is **no remote**. GitHub (account ajk723-yale, 4 repositories) has no
  repository with "food", "disaster", or "final" in its name. Nothing was pushed or published.
