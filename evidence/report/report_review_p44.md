# P44 report.html: verification and open points for review

- **File:** `report.html` (project root), one self-contained file of about 480 KB. It embeds 9 cropped screenshots
  (base64 JPEG) and 4 inline SVG figures (architecture, trace, token chart, cache chart). There are no external
  images, stylesheets, scripts, or fonts (checked); links go only to the repository and the 7 sources.
- **Built by:** `scripts/report_figures_p44.py` (every number, from saved evidence →
  `report_figures_p44.json`) and `scripts/build_report_p44.py` (layout; screenshot crop boxes are in the code).
- **Print check:** Chrome headless "print to PDF" on US Letter (612 × 792 pt) gives **11 pages**
  (`report_print_check_p44.pdf`). After the P45 revisions the print is **13 pages** (same file, regenerated). Each page was rendered to an image and inspected:
  - no clipped text or figures;
  - no table header left without its rows; long tables split only between rows and repeat their header;
  - every figure stays with its caption;
  - screenshot text prints at about 7 pt or larger.

  Fixes made during inspection:
  - the architecture diagram was redrawn twice (overlapping labels);
  - trace text was clipped and was shortened;
  - screenshots were unreadable at half width; they are now cropped and enlarged;
  - crops that cut a row or label were adjusted;
  - a header row was left at the bottom of a page;
  - two near-empty last pages were removed.

## Section check (the 8 sections required by the prompt)

| # | Requirement | Where | Status |
|---|---|---|---|
| 1 | Name, author, repository URL, one-sentence description, not claimed as deployed | Title block (page 1) | ✅ "private repository", "not publicly deployed" |
| 2 | Problem: incomplete reports, changing stock, dietary needs; no invented statistics or interviews | §2 | ✅ (states that no field data exists) |
| 3 | Honest comparison with named products and ChatGPT, with cited sources; no unverified "lacks" claims | §3 table, sources [1]–[5] | ✅, with caveats below |
| 4 | Agent, tools, extraction + screening, deterministic calculations, photo analysis, human approval; architecture diagram; one real traced run; AI vs code vs staff | §4: Fig. 1, component table, Fig. 2–6 | ✅ (trace: `agent_trace_p44.json`) |
| 5 | Measured token categories; cost per workflow and per user per month; 100 / 10,000 users; pricing assumptions; Portkey unknowns; P35 optimization and quality | §5: Fig. 7–8, 3 tables | ✅ (scenarios labeled as assumptions) |
| 6 | Risks and defenses; attack before/after; screenshots; implemented vs unsolved; no hard spending cap | §6: risk table, attack table, Fig. 9–11 | ✅ |
| 7 | Accuracy, reliability, timings, defects and fixes; sample size and method; no invented impact | §7: Fig. 12–13, timing tables | ✅ |
| 8 | Limits (synthetic data, missing info, recount rule, no operational validation) and next steps | §8 | ✅ |

**The course's own rubric document was not available to me** (only the requirements in the prompt), so the check
above is against the prompt.

## Claims that rest on weaker evidence (please review)

1. **ChatGPT [5].** The OpenAI Help Center page returned HTTP 403 to automated fetching. Its content (uploads of
   CSV and spreadsheets; running Python) was read from search-result extracts only.
2. **Sahana Eden [2].** The module list comes from an OSGeo-Live archive page for Sahana Eden 0.5.4 (about 2011). The
   current homepage [1] confirms only the general description. Current features were not verified.
3. **FEMA NSS [3]** is a 2011 fact sheet; the system's current state was not checked. **WFP LESS [4]** is described
   from a 2021 audit page.
4. **Monthly scenarios** use hypothetical usage profiles (the same as P32) and a 30-day month. Chat cost uses the mean
   of 5 measured questions; the traced allocation question costs about 3× that. Prices are OpenAI's published rates;
   the course Portkey / Azure billing is unknown.
5. **Agent trace (revised in P45).** The trace, the screenshots (S39, S40), the server-log lines, the usage-log
   lines, and the reply text now all come from **one app execution**, run `ddf9fc62fb5a`, in which both model calls
   reached the model (`evidence/report/agent_app_run_p45.json`, all checks pass).
   - Earlier, the P44 screenshots S35/S36, and a first P45 attempt (S37/S38), repeated the scripted question
     verbatim; Portkey answered them from its response cache (HIT; same response IDs as the scripted run). Those
     screenshots are no longer used.
   - It is still one run, and tool choice varies: the scripted run called two tools, the traced app run one.
6. **Timings correction.** While drafting, the P40 report's planning-time table turned out not to match its saved
   results file: an earlier run had been overwritten. The P40 report and the development log were corrected to the
   saved values. The report states the Plan A + B median as ≈20 ms (18.5–21.9 ms across 3 saved runs).
7. **Small samples throughout:** 2 attacks and 7 benign reports; 5 extraction examples; 1 run per follow-up
   question; synthetic images only.
8. **Screenshot stages.** Several screenshots (S12, S13, S18, S20) predate the Dashboard tab. The crops exclude the
   old tab bar, and the behavior shown is unchanged; captions give the capture step (e.g. "[S12 · P21]").

## P45 revisions

- **Motivation.** It now starts from the author's stated background: supporting government coordination related to
  the Fukushima nuclear accident, with no food-distribution management. It gives three lessons (incomplete
  information, coordination across organizations, human accountability) without specific incidents, and presents
  shelter food allocation as a new application.
- **Agent evidence.** Rebuilt from a single execution (above).
- **Impact.** Two panels separate "What was measured: technical validation" from "What was not measured: real-world
  impact" (no external municipal staff testing, no human time measured, no exercise or real use). The subsection
  headings say "technical validation", and the title page notes it. All measured values are unchanged.

## P49 corrections

- **Motivation:** "That work was not food distribution, and I have never managed food distribution" was replaced with
  "That crisis-coordination work shaped three convictions…". The paragraph closes with "a new area in which to apply
  these lessons"; nothing implies the author managed shelter food allocation.
- **Figure 2 caption** now also gives the run total (4,467 input / 577 output tokens), which the slides quote, so the
  same figure can be found in both documents.
- **Print check:** still **13 pages** (`report_print_check_p44.pdf` regenerated).
