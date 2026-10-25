# P47 slides.html: build and verification

- **File:** `slides.html` (project root), about 590 KB, built by `scripts/build_slides_p47.py`.
  - Numbers come from `evidence/report/report_figures_p44.json` (the same file `report.html` uses) or from the
    cited evidence files.
  - Screenshots are cropped in code and embedded as base64.
  - reveal.js **5.2.1** (MIT license, notice kept in the file) is inlined: `reveal.js`, `reset.css`, `reveal.css`.
    It was downloaded with `npm pack reveal.js@5` into a scratch folder; no reveal.js theme is used.
- **Self-contained:** no `<link>`, `@import`, or external `src`/`href`.
  - The only URLs in the file are documentation strings and template code inside reveal.js.
  - Opened directly from disk (`file://`) in headless Chrome, the deck rendered (title slide).
- **Slides: 9** (`Reveal.getTotalSlides()` = 9; limit 10):
  1. Title
  2. Problem
  3. Solution
  4. How it works (diagram: AI / code / staff)
  5. Demo (S41–S43)
  6. Intake & vision (S15, S18)
  7. Tokenomics
  8. Safety & impact (S20)
  9. Limits & next steps
- **Navigation:**
  - ArrowRight / ArrowLeft move between slides (tested: 0 → 1 → 0);
  - `F` calls `requestFullscreen` (tested by intercepting the call; real fullscreen needs a user key press);
  - Esc opens the overview (reveal.js default);
  - slide number and progress bar are shown.
- **Inspection** at 1280×720: every slide was screenshotted and checked by eye, plus an automated check per slide
  (no element overflowing, no footnote overlapping content, no clipped headline numbers). **All 9 pass.**
- **Fixed during inspection:**
  - bold text was not bold (the reveal reset stylesheet);
  - slide 2 and slide 9 had too much empty space (larger text);
  - footnotes ran into the navigation arrows;
  - the slide 5 right column overflowed (tighter crops);
  - the slide 7 layout was cramped and a headline number wrapped;
  - slide 8 was rebuilt into two labeled columns;
  - a split f-string would have printed raw placeholders instead of numbers (caught by lint, fixed, verified);
  - the headline "well under a tenth of a cent" was too strong (the maximum is $0.00096) and was changed to "about a
    tenth of a cent or less".
- **New screenshots** of the current app (synthetic working data identical to `data/sample/`):
  - S41: Dashboard situation and actions;
  - S42: allocation plan, with halal shown as "unknown";
  - S43: map with SH-03 selected.

  S25 (P38) was not used because it shows the pre-P41 special-diet display (halal "0").

## Claims on the slides and their sources

| Slide | Claim | Source |
|---|---|---|
| 4 | Traced run: 4,467 input / 577 output tokens; figures matched | `agent_app_run_p45.json` |
| 5 | 596 / 1,003 / 407 | S41; `report_figures_p44.json` |
| 7 | $0.0001–$0.0010 per action; 75% of chat input read from cache (1,652 of 2,212 tokens, mean); monthly ranges; −74% / −85%; 8/8 quality checks | `report_figures_p44.json`; `p35_followup_cache/comparison_p35.json` |
| 8 | 0 → 2 of 2 detected; 0 of 7 false flags; 313/313; 45/3 → 48/0; ≈20 ms (18.5–21.9); 3.4 s | `safety/injection_defense_eval_p31.md`; `impact_eval_results*.json` |

## Limitations

- Screenshot detail is small at 1280×720. Captions carry the key numbers.
- Fullscreen was verified at the code-call level only.
- Testing used Chrome; other browsers were not tested.
- No speaker notes.

## P49 corrections

- **Slide 7:** the Light profile now reads "10 questions · 5 reports · 1 photo + 1 follow-up". The estimates already
  included the follow-up (`report_figures_p44.py` light profile: followup 1), so no number changed.
- **Slide 7 clarity:**
  - the scenario assumptions are two labeled lines (Light / Heavy) plus a short note on the range;
  - small text went from 17 to 19 px;
  - the cache caption is shorter, with bold key numbers.
- **Re-check:** 9 slides; all pass the automated overflow / footnote-overlap / clipped-number check; slide 7 inspected
  by screenshot.
- **Report–slides consistency:** 20 key figures and phrases appear in both documents; the slides' rounded monthly
  totals match the report's exact values.
