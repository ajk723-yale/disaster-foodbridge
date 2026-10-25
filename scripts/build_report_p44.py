"""P44: build report.html (one self-contained file) from saved evidence.

    .venv/bin/python scripts/report_figures_p44.py     # numbers -> evidence/report/report_figures_p44.json
    .venv/bin/python scripts/build_report_p44.py       # -> report.html

All figures in the text come from report_figures_p44.json or from the cited evidence files.
Screenshots are embedded as base64 JPEG; charts and diagrams are inline SVG; no external assets.
"""
import base64
import html
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV = os.path.join(ROOT, "evidence")
SHOTS = os.path.join(EV, "screenshots")
F = json.load(open(os.path.join(EV, "report", "report_figures_p44.json")))
TRACE = json.load(open(os.path.join(EV, "report", "report_figures_p44.json")))["trace"]   # P45 single app run
REPO = "https://github.com/ajk723-yale/disaster-foodbridge"

BLUE, ORANGE, AQUA, VIOLET = "#2a78d6", "#eb6834", "#1baf7a", "#6250d6"   # validated (light surface)
INK, MUTED, RULE = "#1d1d1f", "#5b5b60", "#d9d7d2"


def usd(x, digits=None):
    if digits is None:
        digits = 2 if x >= 1 else (4 if x >= 0.001 else 6)
    return f"${x:,.{digits}f}"


def n(x):
    return f"{x:,.0f}"


def img(name, alt, width="100%", crop=None):
    """Embed a screenshot; crop=(left, top, right, bottom) in pixels of the saved screenshot (see captions)."""
    if crop:
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.open(os.path.join(SHOTS, name)).convert("RGB").crop(crop).save(buf, "JPEG", quality=88)
        raw = buf.getvalue()
    else:
        raw = open(os.path.join(SHOTS, name), "rb").read()
    data = base64.b64encode(raw).decode()
    return (f'<img src="data:image/jpeg;base64,{data}" alt="{html.escape(alt)}" '
            f'style="width:{width};margin:0 auto">')


def fig(content, caption, cls=""):
    return f'<figure class="{cls}">{content}<figcaption>{caption}</figcaption></figure>'


# ---- diagrams and charts (inline SVG) ------------------------------------------------------------

def architecture_svg():
    cols = {"staff": (6, 130), "ai": (162, 168), "code": (360, 178), "data": (566, 150)}
    rows = {"A": 30, "B": 84, "C": 138, "D": 192, "E": 246}
    H = 46
    fills = {"staff": ("#f4f2ee", "#8a857c"), "ai": ("#fdf0ea", ORANGE), "code": ("#eaf2fc", BLUE),
             "data": ("#f7f7f5", "#9a978f")}

    def box(col, row, title, lines, h=H, row_end=None):
        x, w = cols[col]
        y = rows[row]
        if row_end:
            h = rows[row_end] + H - y
        fill, stroke = fills[col]
        t = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>',
             f'<text x="{x + 8}" y="{y + 16}" class="bt">{html.escape(title)}</text>']
        t += [f'<text x="{x + 8}" y="{y + 30 + i * 12}" class="bl">{html.escape(l)}</text>' for i, l in enumerate(lines)]
        return "".join(t)

    def arrow(c1, c2, row, label="", dash=False):
        x1 = cols[c1][0] + cols[c1][1]
        x2 = cols[c2][0]
        y = rows[row] + H / 2
        d = ' stroke-dasharray="4 3"' if dash else ""
        lab = (f'<text x="{(x1 + x2) / 2}" y="{y - 5}" class="al" text-anchor="middle">{html.escape(label)}</text>'
               if label else "")
        return (f'<line x1="{x1}" y1="{y}" x2="{x2 - 2}" y2="{y}" stroke="#55534f" stroke-width="1.2"{d} '
                f'marker-end="url(#ah)"/>' + lab)

    p = ['<svg viewBox="0 0 720 312" xmlns="http://www.w3.org/2000/svg" role="img" '
         'aria-label="Architecture: each staff tab, the AI step if any, the deterministic code, and the data it uses">',
         '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
         'orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#55534f"/></marker></defs>',
         '<style>.bt{font:600 11.5px sans-serif;fill:#1d1d1f}.bl{font:10.2px sans-serif;fill:#3a3a3d}'
         '.al{font:italic 9.5px sans-serif;fill:#55534f}.lane{font:700 9.5px sans-serif;fill:#5b5b60;'
         'letter-spacing:.06em}</style>',
         '<text x="6" y="18" class="lane">STAFF (WEB APP)</text>',
         '<text x="162" y="18" class="lane">AI · gpt-6-luna via Portkey</text>',
         '<text x="360" y="18" class="lane">DETERMINISTIC CODE (tested)</text>',
         '<text x="566" y="18" class="lane">DATA</text>',
         box("staff", "A", "Dashboard", ["situation, actions, map"]),
         box("staff", "B", "Chat", ["questions, drafts"]),
         box("staff", "C", "Report intake", ["paste, correct, approve"]),
         box("staff", "D", "Warehouse photos", ["upload, analyze, ask"]),
         box("staff", "E", "Review & finalize", ["acknowledge, confirm"]),
         box("ai", "B", "Chat agent", ["picks 1 of 5 read-only tools,", "explains the result"]),
         box("ai", "C", "Extractor + screen model", ["fields with quotes; flags", "instructions to the AI"]),
         box("ai", "D", "Photo analyzer, follow-up", ["visible items, counts or", "ranges, unreadable labels"]),
         box("code", "A", "Needs and allocation", ["latest validated records,", "need, unmet demand,",
                                                  "Plan A (largest remainder),", "Plan B, data warnings"], row_end="B"),
         box("code", "C", "Checks + pattern screen", ["quotes, missing or conflicting", "values, time zone"]),
         box("code", "D", "Compare with inventory", ["labels “needs review”;", "never changes stock"]),
         box("code", "E", "Finalization", ["recompute, fingerprint check,", "acknowledgements, SQLite"]),
         box("data", "A", "Record logs (CSV)", ["shelters, inventory,", "commitments; append-only;",
                                               "validated / pending /", "rejected"], row_end="B"),
         box("data", "C", "Shelter log", ["new row only after", "staff approval"]),
         box("data", "D", "Stored photos", ["image + analysis"]),
         box("data", "E", "finalization.db", ["plans, approvals,", "draft requests"]),
         arrow("staff", "code", "A", "no model call", True),
         arrow("staff", "ai", "B"), arrow("ai", "code", "B"),
         arrow("staff", "ai", "C"), arrow("ai", "code", "C"), arrow("code", "data", "C"),
         arrow("staff", "ai", "D"), arrow("ai", "code", "D"), arrow("code", "data", "D"),
         arrow("staff", "code", "E", "no model call", True), arrow("code", "data", "E"),
         f'<line x1="{cols["data"][0]}" y1="70" x2="{cols["code"][0] + cols["code"][1] + 2}" y2="70" '
         'stroke="#55534f" stroke-width="1.2" stroke-dasharray="4 3" marker-end="url(#ah)"/>',
         '<text x="162" y="306" class="al">Every model call adds one line (token counts only) to the usage log.</text>',
         '</svg>']
    return "".join(p)


def trace_svg():
    calls = TRACE["calls"]
    steps = [
        ("STAFF", "#8a857c", "Asks a question", ["“Please draft a food", "allocation plan for the", "next 24 hours.”"]),
        ("AI · call 1", ORANGE, "Chooses 1 tool",
         [f"{n(calls[0]['input_tokens'])} in / {n(calls[0]['output_tokens'])} out", f"{calls[0]['latency_ms'] / 1000:.1f} s",
          "no data seen yet"]),
        ("CODE", BLUE, "Computes the figures", ["calculate_allocation on", "validated records", "(no model)"]),
        ("AI · call 2", ORANGE, "Writes the draft",
         [f"{n(calls[1]['input_tokens'])} in ({n(calls[1]['cached_read_tokens'])} cached)",
          f"{n(calls[1]['output_tokens'])} out ({n(calls[1]['reasoning_tokens'])} reasoning)",
          f"{calls[1]['latency_ms'] / 1000:.1f} s"]),
        ("STAFF", "#8a857c", "Reviews", ["DRAFT only: nothing", "saved, approved or", "dispatched"]),
    ]
    w, gap = 132, 13
    p = ['<svg viewBox="0 0 720 104" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Agent run trace">',
         '<style>.k{font:700 9.5px sans-serif;letter-spacing:.05em}.t{font:600 11.2px sans-serif;fill:#1d1d1f}'
         '.d{font:10px sans-serif;fill:#3a3a3d}</style>']
    for i, (actor, color, title, lines) in enumerate(steps):
        x = 4 + i * (w + gap)
        p.append(f'<rect x="{x}" y="4" width="{w}" height="96" rx="6" fill="#fff" stroke="{color}" stroke-width="1.6"/>')
        p.append(f'<rect x="{x}" y="4" width="{w}" height="18" rx="6" fill="{color}"/>'
                 f'<rect x="{x}" y="14" width="{w}" height="8" fill="{color}"/>')
        p.append(f'<text x="{x + 8}" y="17" class="k" fill="#fff">{i + 1} · {actor}</text>')
        p.append(f'<text x="{x + 8}" y="39" class="t">{html.escape(title)}</text>')
        p += [f'<text x="{x + 8}" y="{56 + j * 14}" class="d">{html.escape(l)}</text>' for j, l in enumerate(lines)]
        if i < len(steps) - 1:
            ax = x + w + 1
            p.append(f'<path d="M{ax} 52 l{gap - 3} 0" stroke="#55534f" stroke-width="1.4"/>'
                     f'<path d="M{ax + gap - 4} 48 l4 4 l-4 4" fill="none" stroke="#55534f" stroke-width="1.4"/>')
    p.append("</svg>")
    return "".join(p)


def tokens_chart_svg():
    t = F["tokens_mean_per_provider_call_p34"]
    rows = [("Chat (per model call)", "chat"), ("Report extraction", "extraction"), ("Safety screen", "safety_screen"),
            ("Photo analysis", "photo_analysis"), ("Photo follow-up (before P35)", "photo_followup")]
    cats = [("uncached_input", "Uncached input", BLUE), ("cached_read", "Cached read (0.1× price)", ORANGE),
            ("cache_write", "Cache write (1.25–2.5× price)", AQUA), ("output", "Output incl. reasoning", VIOLET)]
    left, width, top, rh = 200, 430, 34, 30
    mx = max(sum(t[k][c] for c, _, _ in cats) for _, k in rows)
    sc = width / mx
    parts = [f'<svg viewBox="0 0 720 {top + rh * len(rows) + 26}" xmlns="http://www.w3.org/2000/svg" role="img" '
             'aria-label="Mean tokens per provider call by workflow">',
             '<style>.l{font:11px sans-serif;fill:#1d1d1f}.v{font:10.5px sans-serif;fill:#3a3a3d}'
             '.g{font:10.5px sans-serif;fill:#5b5b60}</style>']
    lx = left
    for _, label, color in cats:                                  # legend
        parts.append(f'<rect x="{lx}" y="8" width="11" height="11" rx="2" fill="{color}"/>'
                     f'<text x="{lx + 15}" y="18" class="g">{label}</text>')
        lx += 16 + len(label) * 5.7 + 14
    for i, (label, k) in enumerate(rows):
        y = top + i * rh
        parts.append(f'<text x="{left - 8}" y="{y + 14}" class="l" text-anchor="end">{label}</text>')
        x = left
        for c, _, color in cats:
            v = t[k][c]
            if v <= 0:
                continue
            w = v * sc
            parts.append(f'<rect x="{x:.1f}" y="{y + 3}" width="{max(w - 2, 1):.1f}" height="16" rx="2" fill="{color}">'
                         f'<title>{c}: {v:,.0f}</title></rect>')
            x += w
        total = sum(t[k][c] for c, _, _ in cats)
        parts.append(f'<text x="{x + 6:.1f}" y="{y + 15}" class="v">{total:,.0f}</text>')
    parts.append("</svg>")
    return "".join(parts)


def p35_chart_svg():
    later = F["p35"]["photo A, later questions"]
    per = lambda side, w: later[side][f"cost_{w}"] / later[side]["provider_calls"]  # noqa: E731
    groups = [("30-minute cache writes (W30)", per("baseline", "W30"), per("optimized", "W30")),
              ("12-hour cache writes (W12)", per("baseline", "W12"), per("optimized", "W12"))]
    mx = max(max(b, a) for _, b, a in groups)
    left, width, top = 210, 400, 34
    parts = ['<svg viewBox="0 0 720 150" xmlns="http://www.w3.org/2000/svg" role="img" '
             'aria-label="Estimated cost per later follow-up question, before and after">',
             '<style>.l{font:11px sans-serif;fill:#1d1d1f}.v{font:10.5px sans-serif;fill:#3a3a3d}'
             '.g{font:10.5px sans-serif;fill:#5b5b60}</style>',
             f'<rect x="{left}" y="8" width="11" height="11" rx="2" fill="{BLUE}"/><text x="{left + 15}" y="18" class="g">'
             'Before (one prompt, no breakpoint)</text>',
             f'<rect x="{left + 220}" y="8" width="11" height="11" rx="2" fill="{ORANGE}"/><text x="{left + 235}" '
             'y="18" class="g">After (cache breakpoint before the question)</text>']
    for i, (label, before, after) in enumerate(groups):
        y = top + i * 56
        parts.append(f'<text x="{left - 8}" y="{y + 22}" class="l" text-anchor="end">{label}</text>')
        for j, (v, color) in enumerate(((before, BLUE), (after, ORANGE))):
            w = v / mx * width
            parts.append(f'<rect x="{left}" y="{y + j * 20}" width="{w:.1f}" height="16" rx="2" fill="{color}"/>'
                         f'<text x="{left + w + 6:.1f}" y="{y + j * 20 + 12}" class="v">{usd(v)}</text>')
    parts.append(f'<text x="{left}" y="146" class="g">Estimated cost per 2nd-or-later question on the same photo; '
                 'mean of 5 provider calls each. Not a bill.</text></svg>')
    return "".join(parts)


# ---- content ---------------------------------------------------------------------------------------

def build():
    t = F["tokens_mean_per_provider_call_p34"]
    u = F["unit_costs_usd"]
    sc = F["monthly_scenarios_usd (30 days, hypothetical profiles)"]
    tr = F["trace"]
    c1, c2 = tr["calls"]
    later = F["p35"]["photo A, later questions"]
    first = F["p35"]["photo A, question 1 (first on the photo)"]
    pt = F["planning_timings_ms"]
    ext = F["extraction_timing"]
    miss = ext["summary_provider_calls_only (all calls MISS)"]
    hit = ext["summary_with_portkey_cache_hits (not model processing time)"]
    rates = F["rates_per_million_usd"]

    def scen(profile, w):
        return sc[f"{profile} (hypothetical) | {w} | follow-up cache on"]

    css = f"""
    @page {{ size: Letter; margin: 0.6in 0.68in 0.62in 0.68in; }}
    * {{ box-sizing: border-box; }}
    html {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    body {{ margin: 0; color: {INK}; background: #fff; font: 10.4pt/1.45 "Iowan Old Style", "Charter", Georgia, serif; }}
    .page {{ max-width: 7.15in; margin: 0 auto; padding: 0.3in 0; }}
    h1, h2, h3, .kicker, figcaption, table, .meta, .callout, .stat, nav {{ font-family: "Avenir Next", "Helvetica Neue", Arial, sans-serif; }}
    h1 {{ font-size: 30pt; line-height: 1.05; margin: 0 0 6pt; letter-spacing: -0.01em; }}
    h2 {{ font-size: 15.5pt; margin: 20pt 0 6pt; padding-top: 6pt; border-top: 2px solid {INK}; break-after: avoid; }}
    h2 .num {{ color: {ORANGE}; margin-right: 6pt; }}
    h3 {{ font-size: 11.4pt; margin: 12pt 0 3pt; break-after: avoid; }}
    p {{ margin: 0 0 7pt; orphans: 3; widows: 3; }}
    a {{ color: {BLUE}; text-decoration: none; }}
    .kicker {{ text-transform: uppercase; letter-spacing: .12em; font-size: 8.5pt; color: {MUTED}; margin-bottom: 8pt; }}
    .lede {{ font-size: 12.4pt; line-height: 1.42; margin: 8pt 0 10pt; }}
    .meta {{ font-size: 9.6pt; color: {MUTED}; border-top: 1px solid {RULE}; border-bottom: 1px solid {RULE}; padding: 6pt 0; margin: 10pt 0; }}
    .meta b {{ color: {INK}; }}
    .stats {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8pt; margin: 10pt 0; }}
    .stat {{ border: 1px solid {RULE}; border-radius: 6px; padding: 7pt 9pt; break-inside: avoid; }}
    .stat b {{ display: block; font-size: 16pt; line-height: 1.1; }}
    .stat span {{ font-size: 8.8pt; color: {MUTED}; }}
    nav {{ font-size: 9.4pt; columns: 2; column-gap: 18pt; margin-top: 6pt; }}
    nav div {{ break-inside: avoid; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 8.9pt; margin: 6pt 0 9pt; break-inside: auto; }}
    tr {{ break-inside: avoid; }}
    thead {{ display: table-header-group; }}
    table.keep {{ break-inside: avoid; }}
    th {{ text-align: left; font-weight: 600; border-bottom: 1.4px solid {INK}; padding: 3.5pt 5pt; vertical-align: bottom; }}
    td {{ border-bottom: 1px solid {RULE}; padding: 3.5pt 5pt; vertical-align: top; }}
    td.r, th.r {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
    tr.sum td {{ font-weight: 600; border-top: 1.4px solid {INK}; }}
    figure {{ margin: 8pt 0 10pt; break-inside: avoid; }}
    figure img, figure svg {{ display: block; width: 100%; border: 1px solid {RULE}; border-radius: 4px; }}
    figure svg {{ border: none; }}
    figcaption {{ font-size: 8.6pt; color: {MUTED}; margin-top: 4pt; line-height: 1.35; }}
    figcaption b {{ color: {INK}; }}
    .two {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10pt; }}
    .two figure {{ margin-top: 4pt; }}
    .callout {{ font-size: 9.4pt; background: #f6f5f1; border-left: 3px solid {ORANGE}; padding: 6pt 9pt; margin: 8pt 0; break-inside: avoid; }}
    .callout.blue {{ border-left-color: {BLUE}; }}
    .tag {{ display: inline-block; font: 600 7.6pt "Avenir Next", Arial, sans-serif; padding: 0 5pt; border-radius: 8px; color: #fff; }}
    .tag.ai {{ background: {ORANGE}; }} .tag.code {{ background: {BLUE}; }} .tag.staff {{ background: #8a857c; }}
    .ok {{ color: #12783f; font-weight: 600; }} .no {{ color: #b3261e; font-weight: 600; }}
    ul {{ margin: 0 0 7pt; padding-left: 15pt; }} li {{ margin-bottom: 2.5pt; }}
    ol.small {{ break-inside: avoid; }}
    .refs {{ font-size: 8.6pt; margin-bottom: 4pt; }} .refs li {{ margin-bottom: 1.5pt; }}
    .src {{ font-size: 8.2pt; color: {MUTED}; }}
    .small {{ font-size: 9pt; }}
    .pb {{ break-before: page; }}
    @media screen {{ body {{ background: #ecebe7; }} .page {{ background: #fff; padding: 0.6in 0.7in; margin: 0.3in auto;
       box-shadow: 0 1px 6px rgba(0,0,0,.12); max-width: 8.5in; }} }}
    """

    # Tables ---------------------------------------------------------------------------------------
    comp = """
    <table>
      <tr><th style="width:17%">Product</th><th style="width:40%">What its publisher documents</th><th>How Disaster FoodBridge relates</th></tr>
      <tr><td><b>Sahana Eden</b><br><span class="src">[1][2]</span></td><td>Open-source toolkit for “database-driven web applications” in emergency and humanitarian management; an older module overview lists a Shelter Registry tracking “location, distribution, capacity and breakdown of victims”, Requests Management, and Mapping.</td><td>Far broader in scope. FoodBridge is a narrow prototype for one decision: how to split scarce food between shelters, with the rules encoded and tested. We did not check how Sahana deployments compute allocations.</td></tr>
      <tr><td><b>FEMA National Shelter System</b><br><span class="src">[3]</span></td><td>A “coordinated nationwide database of emergency shelter information”, built with the American Red Cross, with GIS mapping; also covers kitchens, points of distribution and warehouses.</td><td>A registry and situational-awareness system at national scale. FoodBridge works from a municipality’s own shelter and stock reports and turns them into a draft distribution plan.</td></tr>
      <tr><td><b>WFP LESS</b><br><span class="src">[4]</span></td><td>WFP’s system for “real time management” of commodities from intake to final destination (audit report, 2021).</td><td>Commodity tracking for a global agency. FoodBridge assumes far simpler stock records and focuses on the shelter-level allocation and its uncertainty.</td></tr>
      <tr><td><b>ChatGPT</b> (data analysis)<br><span class="src">[5]</span></td><td>Accepts uploaded spreadsheets and CSV files and can run Python to summarize, chart and calculate.</td><td>A general assistant; each analysis depends on the user’s prompt. FoodBridge fixes the rules in tested code, keeps the model away from the arithmetic, and adds record states, warnings and a staff sign-off.</td></tr>
    </table>"""

    def unit_row(label, key, note=""):
        v = u[key]
        return f'<tr><td>{label}{note}</td><td class="r">{usd(v["W30"], 6)}</td><td class="r">{usd(v["W12"], 6)}</td></tr>'

    unit_table = f"""
    <table>
      <tr><th>Action (one unit)</th><th class="r">Est. cost, 30-min writes</th><th class="r">Est. cost, 12-h writes</th></tr>
      {unit_row("Chat question (mean of 5 measured questions)", "chat question (P34 mean of 5)")}
      <tr><td>Chat: the traced allocation request (run ddf9fc62fb5a, 2 calls, §4)</td><td class="r">{usd(tr['cost_estimate_usd']['W30'], 6)}</td><td class="r">{usd(tr['cost_estimate_usd']['W12'], 6)}</td></tr>
      {unit_row("Report intake (extraction + safety screen)", "report intake (extraction + safety screen)")}
      {unit_row("Photo analysis", "photo analysis")}
      {unit_row("Photo follow-up, first question on a photo", "photo follow-up, before P35 change")}
      {unit_row("Photo follow-up, later questions (after P35 change)", "photo follow-up, 2nd+ on same photo, after P35 change")}
    </table>"""

    def scen_cells(profile):
        a, b = scen(profile, "W30"), scen(profile, "W12")
        return "".join(f'<td class="r">{usd(a[k], 2)}–{usd(b[k], 2)}</td>' for k in ("per_user_month", "100_users_month",
                                                                               "10000_users_month"))
    scen_table = f"""
    <table class="keep">
      <tr><th>Usage profile (assumed, per user per day)</th><th class="r">Per user / month</th><th class="r">100 users / month</th><th class="r">10,000 users / month</th></tr>
      <tr><td><b>Light:</b> 10 chat questions, 5 reports, 1 photo + 1 follow-up</td>{scen_cells("light")}</tr>
      <tr><td><b>Heavy:</b> 60 chat questions, 30 reports, 10 photos + 20 follow-ups</td>{scen_cells("heavy")}</tr>
    </table>"""

    token_table = "".join(
        f'<tr><td>{label}</td><td class="r">{t[k]["provider_calls"]}</td><td class="r">{n(t[k]["uncached_input"])}</td>'
        f'<td class="r">{n(t[k]["cached_read"])}</td><td class="r">{n(t[k]["cache_write"])}</td>'
        f'<td class="r">{n(t[k]["reasoning"])}</td><td class="r">{n(t[k]["output"])}</td></tr>'
        for label, k in (("Chat (per model call)", "chat"), ("Report extraction", "extraction"),
                         ("Safety screen", "safety_screen"), ("Photo analysis", "photo_analysis"),
                         ("Photo follow-up (before P35)", "photo_followup")))

    timings = "".join(f'<tr><td>{label}</td><td class="r">{pt[k]["median_ms"]:.1f} ms</td><td class="r">{pt[k]["max_ms"]:.1f} ms</td></tr>'
                      for label, k in (("Shelter needs", "calculate_shelter_needs"),
                                       ("Plan A + Plan B draft", "calculate_allocation (Plan A + B)"),
                                       ("Everything on the Dashboard", "load_dashboard (all dashboard figures)"),
                                       ("Finalize and save (SQLite)", "finalize_and_store (SQLite, fresh DB each run)")))

    acc, r40, r41 = F["accuracy"], F["reliability_p40"], F["reliability_after_fix_p41"]

    body = f"""
<div class="page">
<!-- 1. TITLE + LINKS -->
<div class="kicker">Final project report · AI-assisted emergency logistics</div>
<h1>Disaster FoodBridge</h1>
<p class="lede">An AI-assisted web app that helps municipal emergency staff turn incomplete shelter and warehouse
reports into a reviewable draft for sharing scarce food between evacuation shelters, while every number comes from
tested code and every decision stays with staff.</p>
<div class="meta"><b>Kohei Ajiki</b> · October 25, 2026 · Code: <a href="{REPO}">{REPO}</a> (private repository) ·
Runs locally (Dash, Python 3.14); <b>not publicly deployed</b> · All data in this report is synthetic.</div>

<p class="src" style="margin:6pt 0 0">Technical validation on synthetic data. No real-world impact or time savings were measured (§7).</p>
<div class="stats" style="margin-top:4pt">
  <div class="stat"><b>{acc['fields']} / {acc['fields']}</b><span>calculated values matched an independent re-calculation ({acc['cases']} test cases)</span></div>
  <div class="stat"><b>{r41['pass']} pass · {r41['fail']} fail</b><span>reliability checks after fixing the 2 dashboard defects our own tests found ({r40['fail']} failed before)</span></div>
  <div class="stat"><b>2 of 2</b><span>prompt-injection attacks detected and shown to staff; 0 of 7 normal reports falsely flagged</span></div>
  <div class="stat"><b>≈{sum(F['plan_ab_median_ms_across_saved_runs']) / 3:.0f} ms</b><span>median time to recompute Plan A + Plan B ({F['plan_ab_median_ms_across_saved_runs'][0]:.1f}–{F['plan_ab_median_ms_across_saved_runs'][-1]:.1f} ms across 3 saved runs; sample data, one laptop)</span></div>
  <div class="stat"><b>{miss['median_wall_ms'] / 1000:.1f} s</b><span>median AI time per free-text report (extraction + safety screen; 5 new reports)</span></div>
  <div class="stat"><b>{usd(min(v['W30'] for v in u.values()), 4)}–{usd(max(max(v['W12'] for v in u.values()), tr['cost_estimate_usd']['W12']), 4)}</b><span>estimated model cost per action (one question, report or photo) at published rates; not a bill</span></div>
</div>
<nav><div><b>1</b> Title + links</div><div><b>2</b> Motivation</div><div><b>3</b> What is new here</div><div><b>4</b> The agents</div>
<div><b>5</b> Tokenomics</div><div><b>6</b> Safety</div><div><b>7</b> Impact</div><div><b>8</b> Limits + next steps</div></nav>
<p class="src" style="margin-top:8pt">Evidence references such as <i>[E: impact_eval_report.md]</i> point to files in the repository’s
<code>evidence/</code> folder; <code>evidence_index.md</code> maps every claim to its file. Screenshot tags such as [S20 · P31] give the
screenshot ID and the development step (prompt number in <code>AI_prompts.md</code>) in which it was captured. Sources [1]–[7] are listed at the end.</p>

<!-- 2. MOTIVATION -->
<h2><span class="num">2</span>Motivation</h2>
<p>My interest in this problem grew out of professional experience supporting government coordination related to the
Fukushima nuclear accident. That crisis-coordination work shaped three convictions that guided this project. First, crisis decisions often have to be made before the
information is complete, so what is missing should be visible rather than quietly filled in. Second, information
passes between organizations that keep their own records on their own schedules, so it matters which version of a
figure has been checked, and by whom. Third, when a decision affects people, a named person must be accountable for
it, with the basis on record. Shelter food allocation is a new area in which to apply these lessons, chosen because it
is concrete, recurring, and easy to get wrong in exactly these ways.</p>
<p>After a large earthquake or flood, a city may run dozens of evacuation shelters and a few warehouses. Twice a day
someone has to decide how many meals go where. The arithmetic is simple; the inputs are not. Each shelter reports at
a different time, some reports are retyped from phone calls, a newer report may be waiting for someone to check it,
and a shelter that just opened may have no confirmed report at all. Warehouse stock moves while people count it: a
truck that left at 08:45 may or may not be reflected in a 10:00 recount. Food that was approved but not yet loaded
must not be promised twice.</p>
<p>Dietary needs make it harder. Infant formula, allergy-free meals and halal meals cannot be replaced by general
meals, and the number of people who need them is often unknown at first. “Unknown” is not zero: treating it as zero
quietly sends nothing to the families who need it most.</p>
<p>A spreadsheet can hold these numbers but does not stop someone from using an unconfirmed report, double-counting a
shipment, or merging special diets into general meals. A general chatbot can explain the numbers but may calculate
them differently each time, and it cannot tell which records a supervisor has actually checked. What staff need is
one consistent picture built only from <i>checked</i> data, an explicit list of what is missing or uncertain, a
defensible draft plan, and a clear point at which a named person takes responsibility for it. That is the gap this
project addresses. I have no field interviews or operational statistics for shelter food distribution; the value
argued here is about consistency, traceability and accountability, demonstrated on synthetic data.</p>

<!-- 3. WHAT IS NEW -->
<h2><span class="num">3</span>What is new here</h2>
<p>Disaster management software already exists, at much larger scale than this prototype. The table compares
FoodBridge with three named systems and with ChatGPT itself, using only what their publishers document.</p>
{comp}
<p><b>What FoodBridge does differently</b>, specifically:</p>
<ul>
<li><b>The model never does the arithmetic.</b> Needs, available stock, Plan A (a proportional split by the
largest-remainder method) and Plan B (what must be procured) are computed by tested Python. The language model only
chooses which calculation to call and explains the result.</li>
<li><b>Uncertainty is carried, not hidden.</b> Every record is <i>validated</i>, <i>pending</i> or <i>rejected</i>;
only validated records count, pending ones become warnings, and unknown special-diet counts stay “unknown” all the
way to the procurement draft.</li>
<li><b>AI reads messy inputs, staff confirm them.</b> Free-text reports and warehouse photos are read by the model
into structured fields with quoted evidence, checked by code, screened for embedded instructions, and saved only
after a staff member corrects and approves them.</li>
<li><b>A plan is final only when a person finalizes it.</b> Finalization recomputes the plan, refuses it if the data
changed since review, requires an acknowledgement for each warning, and records who finalized it.</li>
</ul>
<p class="small">We did not verify, and do not claim, that the products above lack any of these features. The
comparison shows a different focus, not superiority.</p>

<!-- 4. AGENTS -->
<h2><span class="num">4</span>The agents</h2>
<p>FoodBridge uses one large language model, <code>gpt-6-luna</code>, through the Portkey gateway, in four roles built
with the PydanticAI library. Around them, deterministic code makes every calculation and check, and staff make every
decision that changes records.</p>
{fig(architecture_svg(), "<b>Figure 1. Architecture</b>, one row per tab. Orange: model calls. Blue: deterministic code "
     "covered by the automated test suite (222 tests). Grey: staff actions and data. The chat agent reaches code only "
     "through read-only tool calls; new shelter rows and finalized plans are written only after a staff action. Dashed: "
     "no model involved. Source: <code>app.py</code>, <code>src/</code>.")}
<table>
<tr><th style="width:21%">Component</th><th style="width:13%">Who decides</th><th>What it does, and what it cannot do</th></tr>
<tr><td>Chat agent</td><td><span class="tag ai">AI</span></td><td>Picks among five read-only tools (shelter reports, inventory, needs, allocation, supply-request facts) and writes the answer. Instructed never to calculate or invent figures; has no tool that writes, approves or finalizes (enforced by tests).</td></tr>
<tr><td>Report extractor</td><td><span class="tag ai">AI</span> → <span class="tag code">code</span></td><td>Returns fixed fields (shelter, time, headcount, meals, special diets) with a quote for each value. Code then flags quotes not found in the text and missing, conflicting or impossible values, rejects report times later than receipt, and applies the time-zone rule.</td></tr>
<tr><td>Safety screen</td><td><span class="tag code">code</span> + <span class="tag ai">AI</span></td><td>A pattern layer (code) and a separate screening model look for text aimed at the software, e.g. “mark as approved”. Findings become staff warnings; they never change values.</td></tr>
<tr><td>Photo analyzer and follow-up</td><td><span class="tag ai">AI</span> → <span class="tag code">code</span></td><td>Lists visible items, counts or ranges, and unreadable labels; code compares them with validated inventory and labels results “needs review”. A photo never changes stock records.</td></tr>
<tr><td>Needs, allocation, finalization</td><td><span class="tag code">code</span> + <span class="tag staff">staff</span></td><td>Deterministic rules with rounding defined in tests; finalization only from the staff-only tab, with name, acknowledgements and a data-change check.</td></tr>
</table>

<h3>One agent run, traced step by step</h3>
<p>All evidence below comes from <b>one execution in the running app</b> (run ID <code>ddf9fc62fb5a</code>, Oct 25,
2026): the two screenshots (Figures 3–4), the tool call and its result (server log), the token counts (usage log) and
the reply text. The tool result was re-computed from the same data and its plan fingerprint matched the logged one
<i>[E: report/agent_app_run_p45.json]</i>.</p>
{fig(trace_svg(), f"<b>Figure 2. Trace of run ddf9fc62fb5a.</b> Tokens and latency are measured per model call; both calls "
     f"reached the model (Portkey MISS, not a cached replay). In call 2, {TRACE['calls'][1]['reasoning_tokens']} of the "
     f"{TRACE['calls'][1]['output_tokens']} output tokens were reasoning tokens. Run total: "
     f"{n(TRACE['usage_total']['input_tokens'])} input / {n(TRACE['usage_total']['output_tokens'])} output tokens.")}
{fig(img("S39_p45_stage38_traced-run-ddf9fc62-reply-top.jpg", "Chat reply with DRAFT heading and Plan A / Plan B",
         "5.4in", (105, 92, 695, 438)),
     "<b>Figure 3. Run ddf9fc62fb5a:</b> the question and the start of the reply: the DRAFT notice and Plan A "
     "(cropped; Plan B follows in the app). [S39 · P45]")}
<ol class="small">
<li><span class="tag staff">staff</span> types in Chat: “Please draft a food allocation plan for the next 24 hours.”</li>
<li><span class="tag ai">AI</span> decides, before seeing any data, to call <code>calculate_allocation</code> ({n(c1['input_tokens'])} input tokens: the agent’s instructions, the tool descriptions and the question).</li>
<li><span class="tag code">code</span> reads the latest validated records and returns: 596 general meals available, 1,003 unmet, Plan A 206 / 39 / 351 meals for the three shelters, 407 meals still short; allergy-free and formula covered; halal count unknown; 5 data warnings.</li>
<li><span class="tag ai">AI</span> writes the reply ({n(c2['output_tokens'])} output tokens): “DRAFT — for staff review; not finalized. Nothing has been approved, reserved, or dispatched.” It gives Plan A and Plan B per shelter, keeps special diets separate, says halal must be confirmed, and lists the warnings. Every figure in the reply matches the tool result (checked in the evidence file).</li>
<li><span class="tag staff">staff</span> reads the draft. Nothing is saved; a plan becomes binding only in <i>Review &amp; finalize</i>.</li>
</ol>

{fig(img("S40_p45_stage38_traced-run-ddf9fc62-warnings-tool-activity.jpg", "Special diets, warnings and tool activity",
         "4.4in", (108, 145, 578, 548)),
     "<b>Figure 4. Same run:</b> special diets, data warnings, and the tool-activity panel showing its single call to "
     "<code>calculate_allocation</code> (cropped). [S40 · P45]")}
<p class="small">Tool choice can vary between runs: an earlier scripted run of a similar question also called
<code>calculate_shelter_needs</code>. Two app runs that repeated that exact question were answered from Portkey’s
response cache (replays), so they are not used as trace evidence here.</p>
<h3>Photo analysis and the Dashboard</h3>
<p>Photo analysis is advisory: the model lists what it can see and what it cannot, and code compares the result with
the validated inventory without ever changing it. The Dashboard shows the same deterministic figures as the chat
tools, plus a prioritized action list and a map. The map uses <b>fictional training positions</b> because the sample
records contain no coordinates; it shows no distances or routes.</p>
{fig(img("S18_p29_stage23_photo-image-beside-analysis.jpg", "Warehouse photo with AI analysis", "4.7in",
         (100, 95, 700, 382)),
     "<b>Figure 5. Photo analysis</b> of a synthetic test image: what is visible, what is uncertain (cropped). [S18 · P29]")}
{fig(img("S28_p39_stage32_map-shelter-selected-SH-03.jpg", "Dashboard map with shelter details", "5.2in",
         (70, 112, 730, 380)),
     "<b>Figure 6. Dashboard map</b> on a fictional training layout; selecting SH-03 shows validated demand (590), "
     "proposed Plan A (351) and remaining shortage (239) (cropped). [S28 · P39]")}

<!-- 5. TOKENOMICS -->
<h2><span class="num">5</span>Tokenomics</h2>
<p>Every model call made through the app is logged with the token counts the API reports: input (split into
uncached, read from OpenAI’s prompt cache, and written to it), reasoning and output. No text, images or keys are
logged <i>[E: usage/usage_log_p33.jsonl, tokenomics/usage_log_snapshot_p34.jsonl]</i>. Costs below are
<b>estimates</b> at OpenAI’s published standard rates for <code>gpt-6-luna</code> (per million tokens: input
${rates['input']:.2f}, cached input ${rates['cached_input']:.2f}, cache write ${rates['cache_write_30m']:.3f} for 30
minutes or ${rates['cache_write_12h']:.2f} for 12 hours, output ${rates['output']:.2f}) [6][7]. Our calls go through
Portkey to an Azure deployment; the course account’s actual billing is unknown, and the API does not say which
cache-write duration applied, so costs are shown as a range (30-minute vs 12-hour writes).</p>
{fig(tokens_chart_svg(), "<b>Figure 7. Mean tokens per model call</b>, calls that reached the model (n = "
     f"{t['chat']['provider_calls']}, {t['extraction']['provider_calls']}, {t['safety_screen']['provider_calls']}, "
     f"{t['photo_analysis']['provider_calls']}, {t['photo_followup']['provider_calls']}). Chat reuses its cached "
     "instructions; photo calls write large prompts to the cache. Source: <i>[E: tokenomics/tokenomics_p34_2026-10-24.json]</i>.")}
<table>
<tr><th>Workflow</th><th class="r">Calls</th><th class="r">Uncached in</th><th class="r">Cached read</th><th class="r">Cache write</th><th class="r">Reasoning</th><th class="r">Output</th></tr>
{token_table}
</table>
{unit_table}
<div><p class="small"><b>Portkey cache hits are not counted as savings.</b> Portkey can replay
an identical earlier answer (a “HIT”); the replayed response repeats the original token counts, so we price HITs at
$0 or as new usage only as labeled scenarios. Across the 30 logged calls the total ranged from
{usd(F['p34_all_calls_scenarios_usd']['W30+HIT_FREE'], 4)} to {usd(F['p34_all_calls_scenarios_usd']['W12+HIT_AS_REPLAYED'], 4)}
depending on these assumptions.</p>
<p class="small">The traced allocation question costs about {tr['cost_estimate_usd']['W30'] / u['chat question (P34 mean of 5)']['W30']:.1f} times the average chat question because its tool
result is long; heavier chat use would raise the scenarios below.</p></div>
<h3>Monthly scenarios (assumed usage, not measured)</h3>
<p>We have no measured usage per user. The two profiles below are assumptions, applied over 30 days of active
response; each cell shows the 30-minute to 12-hour cache-write range, with the photo follow-up change of P35 in place.</p>
{scen_table}
<p class="small">Even the heavy profile stays near one to one and a half dollars per user per month in model cost
at these rates. These are not bills: real cost depends on the Portkey and Azure contract, actual usage, and longer
conversations.</p>

<h3>Measured optimization: reusing the photo prompt</h3>
<p>The logs showed that follow-up questions about the same photo each <i>wrote</i> about 1,670 tokens to the prompt
cache and <i>read</i> none: the photo, its earlier analysis and the question were sent as one message, so no later
question ever matched an earlier prompt. We added one cache breakpoint between the photo and the question, then ran
the same image and the same questions before and after. Each phase used its own copy of the image, differing by one
pixel, so that one phase could not reuse the other’s cache (a first attempt with byte-only copies did leak between
phases and was discarded) <i>[E: tokenomics/followup_cache_test_p35_report.md]</i>.</p>
{fig(p35_chart_svg(), f"<b>Figure 8.</b> Later questions read {n(later['optimized']['cached_read_tokens'])} cached tokens "
     f"instead of writing {n(later['baseline']['cache_write_tokens'])}: estimated cost −{abs(later['change_W30_pct']):.0f}% "
     f"(30-min) / −{abs(later['change_W12_pct']):.0f}% (12-h). The first question on a photo is unchanged "
     f"({usd(first['baseline']['cost_W30'])} vs {usd(first['optimized']['cost_W30'])}). Repeat questions answered from "
     "Portkey’s cache were excluded.")}
<p><b>Answer quality was unchanged in this test:</b> all 8 rule-based checks passed in both phases (correct counts,
unreadable label kept “unreadable”, “photo does not show all stock”, packs per carton “unknown”, and an instruction
painted on the image ignored). One answer described a different item as the “bottom-right carton”, which is
consistent with the image. This is one run per question on synthetic images, not a quality guarantee.</p>

<!-- 6. SAFETY -->
<h2><span class="num">6</span>Safety</h2>
<table class="keep">
<tr><th style="width:17%">Risk</th><th style="width:43%">Defense implemented</th><th>Evidence · what is <u>not</u> solved</th></tr>
<tr><td>Prompt injection in field reports</td><td>Report text is treated as data; two-layer screen (code patterns + a separate model) shows staff the suspicious sentences; values and approval rules are unaffected.</td><td>2/2 attacks detected, 0/7 false alarms (below). <i>Not screened:</i> chat messages, photos, supply drafts.</td></tr>
<tr><td>Inaccurate extraction</td><td>Each value needs a quote found in the text (otherwise flagged); missing or conflicting values stay empty and are flagged; impossible values are flagged or rejected; nothing saved until staff correct and approve.</td><td>Tests + 5 hand-written reports <i>[E: extraction/…_rechecked.json]</i>. <i>No accuracy rate measured.</i></td></tr>
<tr><td>Stale or unconfirmed data</td><td>Only the latest validated record counts; pending records become warnings; finalization recomputes the plan and refuses it if the data changed since review (Figure 10).</td><td>Reliability tests R2, R4 (§7). <i>No staleness threshold for old reports.</i></td></tr>
<tr><td>Unauthorized finalization</td><td>The agent has no write tools and refuses (Figure 11); finalization needs a name, an acknowledgement per warning and confirmation in a staff tab.</td><td>3 tests; R4. <i>No login or roles: the name is free text.</i></td></tr>
<tr><td>Excessive model usage</td><td>At most 3 model requests per chat message, 60-second timeout, 1 retry, last 20 messages of history; per-call token log.</td><td><b class="no">No hard spending cap</b>, no per-user or daily token budget, no rate limit.</td></tr>
</table>
<h3>Attack and defense experiment</h3>
<p>We embedded two attacks in an otherwise normal shelter report: a “note to the AI” asking it to mark the report
approved, hide all warnings and set halal to 0, and a fake “system override” demanding a headcount of 30 and 500
meals. <i>[E: safety/injection_eval_p30.md, safety/injection_defense_eval_p31.md]</i></p>
<table class="keep">
<tr><th>Measure (one run per case)</th><th class="r">Before (P30)</th><th class="r">After (P31)</th></tr>
<tr><td>Injected values adopted (halal 0, headcount 30, 500 meals)</td><td class="r">0 of 2 attacks</td><td class="r">0 of 2 attacks</td></tr>
<tr><td>Attack detected and shown to staff</td><td class="r"><span class="no">0 of 2</span></td><td class="r"><span class="ok">2 of 2</span></td></tr>
<tr><td>Normal reports wrongly flagged (baseline + 6 tricky benign reports)</td><td class="r">—</td><td class="r"><span class="ok">0 of 7</span></td></tr>
<tr><td>Extra tokens per report for the screen</td><td class="r">—</td><td class="r">≈380–480 in, 14–318 out</td></tr>
</table>
<p>The model was already robust here (it never adopted the injected values), but staff had no way to know an attack
had happened. The screen makes it visible. The benign set included “Ignore the earlier 11:00 headcount, it was wrong”
and a Japanese staff note, which must not be flagged. Seven reports are too few for a false-positive rate.</p>
{fig(img("S20_p31_stage25_injection-alert-in-report-intake.jpg", "Injection alert in Report intake", "5.0in",
         (100, 150, 700, 545)),
     "<b>Figure 9.</b> Report intake with attack A: each suspicious sentence and the layer that found it (pattern, "
     "model, or both); the extracted values were not changed (cropped). [S20 · P31]")}
{fig(img("S12_p21_stage16_data-changed-fresh-review.jpg", "Plan reloaded after a data change", "5.2in",
         (100, 150, 700, 487)),
     "<b>Figure 10.</b> Review &amp; finalize after the underlying data changed: the plan is reloaded and earlier "
     "warning acknowledgements are cleared, so staff must review again (cropped). [S12 · P21]")}
{fig(img("S13_p21_stage16_agent-refuses-to-finalize.jpg", "Agent refuses to finalize", "3.9in", (55, 60, 425, 148)),
     "<b>Figure 11.</b> Asked in chat to finalize and acknowledge warnings, the agent declines and points to the "
     "staff-only tab (cropped). [S13 · P21]")}

<!-- 7. IMPACT -->
<h2><span class="num">7</span>Impact</h2>
<div class="two">
<div class="callout blue" style="margin-top:0"><b>What was measured: technical validation.</b> Whether the app computes
the right plan (accuracy), behaves correctly when data is missing or changing (reliability), and how long its
automated steps take (processing time), on synthetic data in isolated copies.</div>
<div class="callout" style="margin-top:0"><b>What was not measured: real-world impact.</b> No external municipal staff
tested the app. No human review time or time savings were measured. The app has not been used in an exercise or a
real response, so no effect on how food reaches shelters can be claimed.</div>
</div>
<p>The results below are therefore evidence that the software does what it is designed to do, not evidence that it
improves emergency operations. All runs used isolated copies of the synthetic sample data; working records and saved
plans were verified unchanged by file hashes <i>[E: impact/impact_eval_report.md]</i>.</p>
<h3>Accuracy (technical validation)</h3>
<p>We wrote a separate calculator from the documented rules, sharing no code with the app, and compared {acc['fields']}
values across {acc['cases']} cases (the sample data; ample stock; a tie in the proportional split; a special-diet
shortage; fractional packs with deliveries before and after a report; a 12-hour planning window).
<b>All {acc['fields']} matched.</b> The first run did show mismatches, but all were errors in our calculator, which we
corrected and disclosed. The calculator was written by the same developer from the same documents, so a misunderstanding
shared by both would not be caught.</p>
<h3>Reliability (technical validation)</h3>
<p>Eight scenarios tested missing reports, pending updates, unknown special-diet counts, a report arriving during
review, rejected typos, invalid staff input, no validated inventory, and a partial recount. The calculations and
finalization behaved correctly in all of them. The tests also found <b>two real defects in the Dashboard</b>: it crashed
when two or more warnings had no specific action type, and a special diet with known demand but zero stock read
“Enough in stock”. Both were reproduced, fixed in the display code only, covered by four regression tests that fail on
the old code, and re-tested: {r40['pass']} passed / {r40['fail']} failed before, {r41['pass']} / {r41['fail']} after
({r41['exploratory']} checks are exploratory) <i>[E: impact/dashboard_fix_p41.md]</i>.</p>
{fig(img("S31_p41_stage34_BEFORE-dashboard-crash-R3-state-BUG.jpg", "Dashboard crash before the fix", "100%",
         (60, 80, 740, 128)),
     "<b>Figure 12. Before the fix:</b> with halal demand but no halal stock, the Dashboard showed only an error "
     "(cropped) [S31 · P41]")}
{fig(img("S33_p41_stage34_AFTER-special-diet-no-stock-labeled-shortage.jpg", "Special-diet shortage after the fix",
         "3.4in", (62, 322, 420, 445)),
     "<b>Figure 13. After:</b> the same state renders; halal reads “15 short (none in stock)” (cropped) [S33 · P41]")}
<h3>Processing time (automated only)</h3>
<div class="two">
<table class="keep">
<tr><th>Planning (30 runs; final saved run)</th><th class="r">Median</th><th class="r">Max</th></tr>
{timings}
</table>
<table class="keep">
<tr><th>AI report extraction + safety screen</th><th class="r">Median</th><th class="r">Range</th></tr>
<tr><td>5 new reports (all model calls)</td><td class="r">{miss['median_wall_ms'] / 1000:.1f} s</td><td class="r">{miss['min_wall_ms'] / 1000:.1f}–{miss['max_wall_ms'] / 1000:.1f} s</td></tr>
<tr><td>5 earlier reports (extraction replayed by cache; not model time)</td><td class="r">{hit['median_wall_ms'] / 1000:.1f} s</td><td class="r">{hit['min_wall_ms'] / 1000:.1f}–{hit['max_wall_ms'] / 1000:.1f} s</td></tr>
</table>
</div>
<p><b>These are machine times only.</b> No one was timed reading extractions, acknowledging warnings or finalizing,
and the app was not compared with current practice, so no time saving is claimed. The narrower, measured statement:
on this synthetic data, recomputing the plan takes milliseconds and each AI-read report takes a few seconds; how long
staff need to review the results is unknown.</p>

<!-- 8. LIMITS -->
<h2><span class="num">8</span>Limits + next steps</h2>
<ul>
<li><b>Synthetic everything.</b> Four shelters, two warehouses, five free-text reports, two drawn warehouse images
and a fictional map. Real reports, real photos (lighting, clutter, handwriting) and real scale are untested.</li>
<li><b>Missing or unvalidated information.</b> The app flags it but cannot obtain it; pending records cannot yet be
validated in the app, nor inventory counts and deliveries recorded. Extraction accuracy has not been measured on a
labeled set.</li>
<li><b>Unresolved inventory rule.</b> When only one item in a warehouse is recounted, the documents do not say whether
an earlier dispatch is already reflected; the app makes the cautious choice (counts it as gone), and the rule needs a
decision from operations staff.</li>
<li><b>No operational validation.</b> No user testing, no timing of human review, no comparison with current practice,
and the “understandable in 10 seconds” Dashboard goal is untested.</li>
<li><b>Security gaps.</b> No authentication or roles, no hard spending cap, only report text is screened for injection,
and the evaluation was a single run per case.</li>
</ul>
<p><b>Next steps, in order:</b> (1) a pilot with emergency-management staff on anonymized past data, timing review and
recording disagreements; (2) staff login with roles and a daily token budget enforced in code; (3) validation screens
for pending records, inventory counts and deliveries; (4) a labeled set of real-style reports and photos to measure
extraction and vision accuracy; (5) a decision on the partial-recount rule; (6) verified shelter coordinates before
any real map is used.</p>

<h3>Sources</h3>
<ol class="refs">
<li>Sahana Software Foundation, “Sahana Eden” (application development kit description). <a href="https://eden.sahanafoundation.org">eden.sahanafoundation.org</a>, accessed Oct 25, 2026.</li>
<li>OSGeo-Live 4.5, “Sahana Eden” overview, Sahana Eden 0.5.4 (dated; module list). <a href="https://live-archive.osgeo.org/4.5/en/overview/sahana_overview.html">live-archive.osgeo.org/4.5/en/overview/sahana_overview.html</a>, accessed Oct 25, 2026.</li>
<li>FEMA, “National Shelter System” fact sheet, May 2011. <a href="https://fema.gov/pdf/media/factsheets/2011/fema_national_shelter_system.pdf">fema.gov/pdf/media/factsheets/2011/fema_national_shelter_system.pdf</a>, accessed Oct 25, 2026.</li>
<li>World Food Programme, Office of the Inspector General, “Internal Audit of LESS Functionalities and Application Controls”, Feb 2021. <a href="https://wfp.org/audit-reports/internal-audit-less-functionalities-and-application-controls-february-2021">wfp.org/audit-reports/internal-audit-less-functionalities-and-application-controls-february-2021</a>, accessed Oct 25, 2026.</li>
<li>OpenAI Help Center, “Data analysis with ChatGPT” (article 8437071). <a href="https://help.openai.com/en/articles/8437071">help.openai.com/en/articles/8437071</a>; content read via a search index on Oct 25, 2026 (the page refused direct automated access).</li>
<li>OpenAI, API pricing (gpt-6-luna, standard tier). <a href="https://developers.openai.com/api/docs/pricing">developers.openai.com/api/docs/pricing</a>, checked Oct 24, 2026; rates saved in <i>[E: tokenomics/pricing_gpt-6-luna_2026-10-24.json]</i>.</li>
<li>OpenAI, “Prompt caching” guide. <a href="https://developers.openai.com/api/docs/guides/prompt-caching">developers.openai.com/api/docs/guides/prompt-caching</a>, checked Oct 24, 2026.</li>
</ol>
<p class="src">Screenshots [S..]: <code>evidence/screenshots/</code>, all from the real app running on synthetic data.</p>
</div>"""
    import re
    # header rows become <thead> so split tables repeat their column names on the next page
    body = re.sub(r"(<table[^>]*>\s*)(<tr><th.*?</tr>)", r"\1<thead>\2</thead>", body, flags=re.S)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Disaster FoodBridge: Final Project Report</title><style>{css}</style></head>
<body>{body}</body></html>"""


if __name__ == "__main__":
    out = os.path.join(ROOT, "report.html")
    open(out, "w", encoding="utf-8").write(build())
    print(out, os.path.getsize(out))
