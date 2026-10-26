"""P47: build slides.html, a self-contained reveal.js deck (9 slides) from report.html's evidence.

    .venv/bin/python scripts/build_slides_p47.py --reveal <path to reveal.js package/dist>

All numbers come from evidence/report/report_figures_p44.json (the same file report.html uses) or from the
cited evidence files. reveal.js 5.2.1 (MIT) JS and CSS are inlined; screenshots are cropped and embedded as
base64; no external requests. Works by double-clicking the file (file://).
"""
import base64
import html
import io
import json
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV = os.path.join(ROOT, "evidence")
SHOTS = os.path.join(EV, "screenshots")
F = json.load(open(os.path.join(EV, "report", "report_figures_p44.json")))
REPO = "github.com/ajk723-yale/disaster-foodbridge"

PINK, BG, PANEL, LINE, TEXT, MUTED = "#ff4fa3", "#0b0b0d", "#16161a", "#2a2a31", "#f3eef2", "#a79aa3"
AI, CODE, STAFF = "#d95926", "#3987e5", PINK          # dark-surface palette (validated)
AMBER, RED, GREEN = "#fab219", "#e5484d", "#2fbf71"


def usd(x, d=None):
    if d is None:
        d = 2 if x >= 1 else (4 if x >= 0.001 else 6)
    return f"${x:,.{d}f}"


def n(x):
    return f"{x:,.0f}"


def shot(name, crop, alt, style=""):
    buf = io.BytesIO()
    Image.open(os.path.join(SHOTS, name)).convert("RGB").crop(crop).save(buf, "JPEG", quality=90)
    data = base64.b64encode(buf.getvalue()).decode()
    return f'<img class="shot" src="data:image/jpeg;base64,{data}" alt="{html.escape(alt)}" style="{style}">'


def flow_svg():
    """Plain-English 'how it works' flow: AI reads, staff check, code computes, staff decide."""
    def box(x, y, w, h, color, title, lines, fill="#16161a"):
        t = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{fill}" stroke="{color}" stroke-width="3"/>',
             f'<text x="{x + 18}" y="{y + 38}" class="t" fill="{color}">{html.escape(title)}</text>']
        t += [f'<text x="{x + 18}" y="{y + 72 + i * 28}" class="d">{html.escape(l)}</text>' for i, l in enumerate(lines)]
        return "".join(t)

    def arrow(x1, y1, x2, y2):
        return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#a79aa3" stroke-width="3" '
                f'marker-end="url(#a)"/>')

    p = ['<svg viewBox="0 0 1180 440" xmlns="http://www.w3.org/2000/svg" role="img" '
         'aria-label="How it works: AI reads messy inputs, staff confirm, code computes, staff decide">',
         '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">'
         '<path d="M0,0 L10,5 L0,10 z" fill="#a79aa3"/></marker></defs>',
         '<style>.t{font:700 25px sans-serif}.d{font:20px sans-serif;fill:#e6dfe4}.s{font:600 17px sans-serif;'
         'fill:#a79aa3;letter-spacing:.08em}</style>',
         '<text x="0" y="22" class="s">1 · READ</text><text x="300" y="22" class="s">2 · CONFIRM</text>',
         '<text x="600" y="22" class="s">3 · CALCULATE</text><text x="900" y="22" class="s">4 · DECIDE</text>',
         box(0, 40, 270, 170, AI, "AI reads", ["free-text reports", "and warehouse photos", "into fields + quotes"]),
         box(300, 40, 270, 170, STAFF, "Staff confirm", ["correct the fields,", "approve → record", "becomes “validated”"]),
         box(600, 40, 280, 170, CODE, "Code calculates", ["needs, stock, Plan A,", "Plan B, warnings —", "same answer every time"]),
         box(910, 40, 270, 170, STAFF, "Staff decide", ["acknowledge warnings,", "name + finalize;", "nothing else is binding"]),
         arrow(272, 125, 296, 125), arrow(572, 125, 596, 125), arrow(882, 125, 906, 125),
         box(600, 250, 280, 170, AI, "AI explains", ["the chat agent calls", "read-only tools and", "words the answer"]),
         arrow(740, 212, 740, 246),
         '<rect x="0" y="250" width="570" height="170" rx="14" fill="#101013" stroke="#2a2a31" stroke-width="2"/>',
         f'<rect x="24" y="282" width="22" height="22" rx="5" fill="{AI}"/><text x="58" y="301" class="d">AI model (gpt-6-luna): reads and writes language</text>',
         f'<rect x="24" y="326" width="22" height="22" rx="5" fill="{CODE}"/><text x="58" y="345" class="d">Deterministic code: every number, tested</text>',
         f'<rect x="24" y="370" width="22" height="22" rx="5" fill="{STAFF}"/><text x="58" y="389" class="d">Staff: approve records, finalize plans</text>',
         '<rect x="910" y="250" width="270" height="170" rx="14" fill="#101013" stroke="#2a2a31" stroke-width="2"/>',
         '<text x="928" y="290" class="d">The AI has no tool that</text><text x="928" y="318" class="d">writes, approves or</text>',
         '<text x="928" y="346" class="d">finalizes anything</text><text x="928" y="384" class="s">ENFORCED BY TESTS</text>',
         '</svg>']
    return "".join(p)


def cache_svg():
    later = F["p35"]["photo A, later questions"]
    per = lambda side, w: later[side][f"cost_{w}"] / later[side]["provider_calls"]  # noqa: E731
    rows = [("30-min writes", per("baseline", "W30"), per("optimized", "W30")),
            ("12-hour writes", per("baseline", "W12"), per("optimized", "W12"))]
    mx = max(b for _, b, _ in rows)
    left, width = 190, 300
    p = ['<svg viewBox="0 0 600 230" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Cache optimization">',
         '<style>.l{font:20px sans-serif;fill:#f3eef2}.v{font:19px sans-serif;fill:#e6dfe4}.g{font:17px sans-serif;fill:#a79aa3}</style>',
         f'<rect x="{left}" y="4" width="16" height="16" rx="3" fill="{CODE}"/><text x="{left + 24}" y="18" class="g">before</text>',
         f'<rect x="{left + 110}" y="4" width="16" height="16" rx="3" fill="{AI}"/><text x="{left + 134}" y="18" class="g">after</text>']
    for i, (label, b, a) in enumerate(rows):
        y = 44 + i * 92
        p.append(f'<text x="{left - 14}" y="{y + 32}" class="l" text-anchor="end">{label}</text>')
        for j, (v, c) in enumerate(((b, CODE), (a, AI))):
            w = v / mx * width
            p.append(f'<rect x="{left}" y="{y + j * 34}" width="{w:.1f}" height="26" rx="4" fill="{c}"/>'
                     f'<text x="{left + w + 10:.1f}" y="{y + j * 34 + 20}" class="v">{usd(v)}</text>')
    p.append("</svg>")
    return "".join(p)


def slides():
    u = F["unit_costs_usd"]
    tr = F["trace"]
    sc = F["monthly_scenarios_usd (30 days, hypothetical profiles)"]
    later = F["p35"]["photo A, later questions"]
    acc, r40, r41 = F["accuracy"], F["reliability_p40"], F["reliability_after_fix_p41"]
    miss = F["extraction_timing"]["summary_provider_calls_only (all calls MISS)"]
    plan_ms = F["plan_ab_median_ms_across_saved_runs"]
    t = F["tokens_mean_per_provider_call_p34"]
    lo = min(v["W30"] for v in u.values())
    hi = max(max(v["W12"] for v in u.values()), tr["cost_estimate_usd"]["W12"])

    def scen(p, w, k):
        return sc[f"{p} (hypothetical) | {w} | follow-up cache on"][k]

    s = []
    # 1. Title
    s.append(f"""
<section class="title">
  <div class="kicker">Final project · AI-assisted emergency logistics</div>
  <h1>Disaster <span class="pink">FoodBridge</span></h1>
  <p class="pitch">Turns incomplete shelter and warehouse reports into a reviewable plan for sharing scarce food
  between evacuation shelters: every number from tested code, every decision with staff.</p>
  <div class="byline"><b>Kohei Ajiki</b><span><a href="https://{REPO}" style="color:inherit;text-decoration:underline">{REPO}</a> (public) · runs locally, not publicly deployed · synthetic data</span></div>
  <div class="hint">← → to navigate · F for fullscreen · Esc for overview</div>
</section>""")
    # 2. Problem
    s.append("""
<section>
  <h2>The problem: the math is easy, <span class="pink">the inputs are not</span></h2>
  <div class="grid4">
    <div class="card"><div class="ico">🕒</div><b>Reports arrive at different times</b><p>A newer report may still be waiting to be checked</p></div>
    <div class="card"><div class="ico">❓</div><b>Some shelters have no confirmed report</b><p>A new shelter can be invisible to the plan</p></div>
    <div class="card"><div class="ico">📦</div><b>Stock moves while it is counted</b><p>Was the 08:45 truck already in the 10:00 count?</p></div>
    <div class="card"><div class="ico">🍼</div><b>Special diets can’t be swapped</b><p>Formula, allergy-free, halal — and “unknown” is not zero</p></div>
  </div>
  <p class="take">A spreadsheet can use an unchecked report; a chatbot may compute differently each time.
  Staff need <b>one consistent picture from checked data</b>, a list of what is missing, and a <b>named person</b> who decides.</p>
  <p class="src">Illustrations from the synthetic sample data (4 shelters, 2 warehouses). No field statistics are claimed.</p>
</section>""")
    # 3. Solution
    s.append("""
<section>
  <h2>What FoodBridge does differently</h2>
  <div class="grid2">
    <div class="card big"><div class="num">1</div><b>The AI never does the arithmetic</b><p>Needs, stock, Plan A and Plan B come from tested code. The AI only picks the calculation and explains it.</p></div>
    <div class="card big"><div class="num">2</div><b>Uncertainty stays visible</b><p>Records are validated, pending or rejected. Only validated data counts; everything else becomes a warning.</p></div>
    <div class="card big"><div class="num">3</div><b>AI reads, staff confirm</b><p>Reports and photos are read by AI with quoted evidence, checked by code, and saved only after staff approve.</p></div>
    <div class="card big"><div class="num">4</div><b>A person finalizes the plan</b><p>Finalizing re-checks the data, needs an acknowledgement per warning, and records who decided.</p></div>
  </div>
  <p class="src">Compared in the report with Sahana Eden, FEMA’s National Shelter System, WFP LESS and ChatGPT: a different focus, not a claim that they lack these features.</p>
</section>""")
    # 4. How it works
    s.append(f"""
<section>
  <h2>How it works: <span style="color:{AI}">AI</span>, <span style="color:{CODE}">code</span>, <span class="pink">staff</span></h2>
  <div class="diagram">{flow_svg()}</div>
  <p class="src">Traced run ddf9fc62fb5a: the AI chose <code>calculate_allocation</code> → code returned 596 available, 1,003 unmet,
  407 short → AI wrote a DRAFT with every figure matching ({n(tr['usage_total']['input_tokens'])} input / {n(tr['usage_total']['output_tokens'])} output tokens). [report §4]</p>
</section>""")
    # 5. Demo
    s.append(f"""
<section>
  <h2>Product demo: the Dashboard</h2>
  <div class="demo">
    <figure class="main">{shot("S41_p47_stage39_dashboard-situation-actions-current.jpg", (60, 105, 740, 500), "Current situation and actions")}
      <figcaption><b>Situation + actions:</b> 596 meals available, 1,003 needed, 407 to procure; each open issue comes with a next step</figcaption></figure>
    <div class="side">
      <figure>{shot("S42_p47_stage39_allocation-plan-current.jpg", (60, 75, 740, 310), "Allocation plan A vs B")}
        <figcaption><b>Plan A vs Plan B</b> per shelter (proposed only)</figcaption></figure>
      <figure>{shot("S43_p47_stage39_map-SH-03-current.jpg", (70, 110, 730, 372), "Map with shelter details")}
        <figcaption><b>Map</b> (fictional layout): a shelter’s demand and shortage</figcaption></figure>
    </div>
  </div>
  <p class="src">Real app, synthetic data. Screenshots S41–S43.</p>
</section>""")
    # 6. Intake + vision
    s.append("""
<section>
  <h2>Report intake & vision: <span class="pink">AI reads, staff stay in control</span></h2>
  <div class="grid2 shots">
    <figure>""" + shot("S15_p26_stage20_intake-approved-after-corrections.jpg", (100, 150, 700, 470), "Report intake approved") + """
      <figcaption><b>Free-text report →</b> AI extracts fields with quotes → code flags gaps and conflicts →
      <b>staff correct and approve</b>; only then is it a validated record</figcaption></figure>
    <figure>""" + shot("S18_p29_stage23_photo-image-beside-analysis.jpg", (100, 95, 700, 420), "Warehouse photo analysis") + """
      <figcaption><b>Warehouse photo →</b> AI lists what is visible and what is uncertain → code compares with
      inventory and marks “needs review”; <b>a photo never changes stock</b></figcaption></figure>
  </div>
  <p class="src">Synthetic images and reports only. Screenshots S15 (P26), S18 (P29).</p>
</section>""")
    # 7. Tokenomics
    chat_in = t['chat']['uncached_input'] + t['chat']['cached_read'] + t['chat']['cache_write']
    s.append(f"""
<section>
  <h2>Tokenomics: <span class="pink">about a tenth of a cent or less</span> per action</h2>
  <div class="grid3">
    <div class="stat"><b>{n(tr['usage_total']['input_tokens'])} / {n(tr['usage_total']['output_tokens'])}</b><span>tokens in / out for one allocation question (2 model calls, measured)</span></div>
    <div class="stat"><b>{usd(lo, 4)}–{usd(hi, 4)}</b><span>estimated cost per action: a question, a report or a photo</span></div>
    <div class="stat"><b>{t['chat']['cached_read'] / chat_in * 100:.0f}%</b><span>of chat input reused from the prompt cache, billed at 1/10 price (measured mean)</span></div>
  </div>
  <div class="grid2w">
    <div class="panel">
      <div class="ph">Estimated cost per month (assumed usage, 30 days)</div>
      <table>
        <tr><th></th><th>per user</th><th>100 users</th><th>10,000 users</th></tr>
        <tr><td>Light</td><td>{usd(scen('light','W30','per_user_month'),2)}–{usd(scen('light','W12','per_user_month'),2)}</td><td>{usd(scen('light','W30','100_users_month'),0)}–{usd(scen('light','W12','100_users_month'),0)}</td><td>{usd(scen('light','W30','10000_users_month'),0)}–{usd(scen('light','W12','10000_users_month'),0)}</td></tr>
        <tr><td>Heavy</td><td>{usd(scen('heavy','W30','per_user_month'),2)}–{usd(scen('heavy','W12','per_user_month'),2)}</td><td>{usd(scen('heavy','W30','100_users_month'),0)}–{usd(scen('heavy','W12','100_users_month'),0)}</td><td>{usd(scen('heavy','W30','10000_users_month'),0)}–{usd(scen('heavy','W12','10000_users_month'),0)}</td></tr>
      </table>
      <div class="assume">
        <div><b>Light</b> 10 questions · 5 reports · 1 photo + 1 follow-up</div>
        <div><b>Heavy</b> 60 questions · 30 reports · 10 photos + 20 follow-ups</div>
        <div class="muted">per user per day · range = cache writes billed at the 30-min vs 12-hour rate</div>
      </div>
    </div>
    <div class="panel">
      <div class="ph">Verified fix: reuse the photo prompt</div>
      {cache_svg()}
      <p class="tiny">Each later question on the same photo: <b>−{abs(later['change_W30_pct']):.0f}% / −{abs(later['change_W12_pct']):.0f}%</b> cost.
      Answer checks: <b>8 of 8</b> before and after.</p>
    </div>
  </div>
  <p class="src">Estimates at OpenAI’s published gpt-6-luna rates from logged token counts — <b>not bills</b>. Course Portkey/Azure billing unknown; cache replays not counted as savings. [report §5]</p>
</section>""")
    # 8. Safety + impact
    s.append("""
<section>
  <h2>Safety & impact: <span class="pink">what the tests show</span></h2>
  <div class="grid2s">
    <div>
      <div class="colh">Safety: hidden instructions in reports</div>
      <div class="pair">
        <div class="stat red"><b>0 → 2 of 2</b><span>attacks detected and shown to staff</span></div>
        <div class="stat red"><b>0 of 7</b><span>normal reports falsely flagged</span></div>
      </div>
      <figure class="alert">""" + shot("S20_p31_stage25_injection-alert-in-report-intake.jpg", (105, 345, 695, 552), "Injection alert") + f"""
        <figcaption>Report intake shows each suspicious sentence; injected values (e.g. “halal 0”) were never adopted. [S20]</figcaption></figure>
    </div>
    <div>
      <div class="colh">Technical validation (synthetic data)</div>
      <div class="quad">
        <div class="stat"><b>{acc['fields']}/{acc['fields']}</b><span>values matched an independent re-calculation ({acc['cases']} cases)</span></div>
        <div class="stat"><b>{r41['pass']} / {r41['fail']}</b><span>reliability checks passed / failed, after fixing 2 bugs the tests found (was {r40['pass']} / {r40['fail']})</span></div>
        <div class="stat"><b>≈{sum(plan_ms) / len(plan_ms):.0f} ms</b><span>to recompute Plan A + B ({plan_ms[0]:.1f}–{plan_ms[-1]:.1f} ms, 3 runs)</span></div>
        <div class="stat"><b>{miss['median_wall_ms'] / 1000:.1f} s</b><span>median AI time per free-text report (5 new reports)</span></div>
      </div>
    </div>
  </div>
  <div class="banner"><b>Technical validation, not real-world impact.</b> No municipal staff tested the app; no human time savings
  were measured. <b>No hard spending cap</b> exists yet.</div>
</section>""")
    # 9. Limits
    s.append("""
<section>
  <h2>Before real-world use</h2>
  <div class="grid2 lim">
    <div class="panel">
      <div class="ph">Not yet tested</div>
      <ul>
        <li><b>Real data:</b> only synthetic reports, drawn photos, a fictional map</li>
        <li><b>Real users:</b> no staff testing, no human review time measured</li>
        <li><b>Accuracy at scale:</b> 5 extraction examples, 2 attacks, 7 normal reports</li>
        <li><b>Open rule:</b> is a dispatch already in a partial recount? (app is cautious)</li>
        <li><b>Security:</b> no login or roles, no spending cap</li>
      </ul>
    </div>
    <div class="panel">
      <div class="ph">Next steps</div>
      <ol>
        <li>Pilot with emergency staff on anonymized past data, timing review</li>
        <li>Staff login + roles; a daily token budget enforced in code</li>
        <li>Screens to validate pending records, stock counts, deliveries</li>
        <li>Labeled real-style reports and photos to measure accuracy</li>
        <li>Decide the recount rule; verified shelter coordinates</li>
      </ol>
    </div>
  </div>
  <p class="src">Full evidence: report.html and evidence/ in the repository. Thank you.</p>
</section>""")
    return s


CSS = f"""
:root {{ --r-background-color: {BG}; --r-main-color: {TEXT}; --r-heading-color: {TEXT}; --r-link-color: {PINK}; }}
.reveal-viewport {{ background: {BG}; }}
.reveal {{ font-family: "Avenir Next", "Helvetica Neue", Arial, sans-serif; font-size: 28px; color: {TEXT}; }}
.reveal .slides {{ text-align: left; }}
.reveal .slides section {{ height: 100%; padding: 8px 6px; box-sizing: border-box; }}
.reveal h1 {{ font-size: 96px; font-weight: 800; line-height: 1.02; margin: 0 0 24px; letter-spacing: -0.01em; }}
.reveal h2 {{ font-size: 46px; font-weight: 700; line-height: 1.1; margin: 0 0 24px; }}
.reveal p, .reveal li {{ line-height: 1.35; }}
.pink {{ color: {PINK}; }}
.reveal b, .reveal strong {{ font-weight: 700; }}
.kicker {{ text-transform: uppercase; letter-spacing: .14em; color: {MUTED}; font-size: 20px; margin: 110px 0 16px; }}
.pitch {{ font-size: 34px; max-width: 1050px; margin: 0 0 40px; color: #e6dfe4; }}
.byline {{ display: flex; flex-direction: column; gap: 6px; border-top: 2px solid {PINK}; padding-top: 18px; font-size: 26px; }}
.byline span {{ color: {MUTED}; font-size: 21px; }}
.hint {{ position: absolute; bottom: 10px; left: 6px; color: {MUTED}; font-size: 18px; }}
.card {{ background: {PANEL}; border: 1px solid {LINE}; border-radius: 16px; padding: 22px 22px 18px; }}
.card b {{ font-size: 29px; display: block; line-height: 1.2; }}
.card p {{ color: {MUTED}; font-size: 24px; margin: 12px 0 0; }}
.card .ico {{ font-size: 54px; margin-bottom: 14px; }}
.grid4 .card {{ min-height: 300px; padding-top: 28px; }}
.grid2 .card.big {{ min-height: 210px; padding: 28px; }}
.card.big .num {{ color: {PINK}; font-size: 40px; font-weight: 800; float: left; margin: -4px 16px 0 0; }}
.grid4 {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }}
.grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }}
.grid3 {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }}
.grid3c {{ display: grid; grid-template-columns: 0.9fr 1.25fr 1fr; gap: 16px; align-items: start; }}
.grid2w {{ display: grid; grid-template-columns: 1.15fr 1fr; gap: 16px; margin-top: 16px; align-items: start; }}
.reveal td {{ white-space: nowrap; }}
.grid2s {{ display: grid; grid-template-columns: 1fr 1.05fr; gap: 26px; }}
.colh {{ font-weight: 700; font-size: 24px; color: {MUTED}; text-transform: uppercase; letter-spacing: .06em; margin-bottom: 12px; }}
.pair {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 14px; }}
.quad {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
.alert figcaption {{ font-size: 18px; }}
.take {{ font-size: 30px; margin: 40px 0 0; color: #e6dfe4; border-left: 6px solid {PINK}; padding-left: 20px; }}
.src {{ position: absolute; bottom: 4px; left: 6px; right: 120px; color: {MUTED}; font-size: 17px; margin: 0; }}
.src code, .reveal code {{ color: {PINK}; font-size: 0.95em; }}
.diagram svg {{ width: 100%; height: auto; display: block; }}
.shot {{ display: block; width: 100%; border: 1px solid {LINE}; border-radius: 10px; margin: 0; }}
.reveal figure {{ margin: 0; }}
.reveal figcaption {{ font-size: 19px; color: {MUTED}; margin-top: 8px; line-height: 1.3; }}
.reveal figcaption b {{ color: {TEXT}; }}
.demo {{ display: grid; grid-template-columns: 1.12fr 1fr; gap: 18px; align-items: start; }}
.demo .side {{ display: flex; flex-direction: column; gap: 10px; }}
.demo .side figcaption {{ font-size: 17px; margin-top: 4px; }}
.shots figcaption {{ font-size: 20px; }}
.stat {{ background: {PANEL}; border: 1px solid {LINE}; border-left: 6px solid {PINK}; border-radius: 14px; padding: 16px 18px; }}
.stat b {{ display: block; font-size: 41px; font-weight: 800; line-height: 1.05; white-space: nowrap; }}
.stat span {{ display: block; color: {MUTED}; font-size: 20px; margin-top: 8px; line-height: 1.3; }}
.stat.red {{ border-left-color: {GREEN}; }}
.stack {{ display: flex; flex-direction: column; gap: 16px; }}
.panel {{ background: {PANEL}; border: 1px solid {LINE}; border-radius: 14px; padding: 16px 18px; }}
.ph {{ font-weight: 700; font-size: 23px; margin-bottom: 10px; }}
.panel svg {{ width: 100%; height: auto; display: block; }}
.reveal table {{ border-collapse: collapse; font-size: 20px; width: 100%; }}
.reveal th {{ text-align: right; color: {MUTED}; font-weight: 600; padding: 4px 6px; border-bottom: 1px solid {LINE}; }}
.reveal td {{ text-align: right; padding: 8px 6px; border-bottom: 1px solid {LINE}; font-variant-numeric: tabular-nums; }}
.reveal td:first-child, .reveal th:first-child {{ text-align: left; font-weight: 700; color: {TEXT}; }}
.tiny {{ font-size: 19px; color: {MUTED}; margin: 10px 0 0; line-height: 1.35; }}
.tiny b {{ color: {TEXT}; }}
.assume {{ margin-top: 12px; font-size: 19px; line-height: 1.45; color: #e6dfe4; }}
.assume b {{ display: inline-block; width: 70px; color: {PINK}; }}
.assume .muted {{ color: {MUTED}; font-size: 17px; margin-top: 4px; }}
.banner {{ margin-top: 18px; background: #241a10; border: 1px solid #8a5a1a; border-radius: 12px; padding: 14px 18px; font-size: 22px; }}
.lim ul, .lim ol {{ margin: 0; padding-left: 30px; font-size: 27px; }}
.lim li {{ margin-bottom: 18px; }}
.lim .panel {{ padding: 22px 24px; min-height: 470px; }}
.lim .ph {{ font-size: 30px; margin-bottom: 16px; color: {PINK}; }}
.reveal .controls {{ color: {PINK}; }}
.reveal .progress {{ color: {PINK}; }}
.reveal .slide-number {{ background: transparent; color: {MUTED}; font-size: 16px; }}
"""


def build(reveal_dir):
    js = open(os.path.join(reveal_dir, "reveal.js"), encoding="utf-8").read()
    reset = open(os.path.join(reveal_dir, "reset.css"), encoding="utf-8").read()
    rcss = open(os.path.join(reveal_dir, "reveal.css"), encoding="utf-8").read()
    body = "\n".join(slides())
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Disaster FoodBridge: Final Presentation</title>
<!-- reveal.js 5.2.1, MIT License, Copyright (C) 2011-2024 Hakim El Hattab and reveal.js contributors -->
<style>{reset}</style><style>{rcss}</style><style>{CSS}</style>
</head><body>
<div class="reveal"><div class="slides">
{body}
</div></div>
<script>{js}</script>
<script>
Reveal.initialize({{ width: 1280, height: 720, margin: 0.04, center: false, hash: false, controls: true,
  progress: true, slideNumber: 'c/t', transition: 'fade', backgroundTransition: 'none', keyboard: true }});
</script>
</body></html>"""


if __name__ == "__main__":
    reveal_dir = sys.argv[sys.argv.index("--reveal") + 1]
    out = os.path.join(ROOT, "slides.html")
    open(out, "w", encoding="utf-8").write(build(reveal_dir))
    print(out, os.path.getsize(out))
