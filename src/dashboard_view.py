"""Dash components for the dashboard tab (display only; data comes from src.dashboard).

Three sections: current situation, actions required, allocation plan. Colors: neutral for
normal information, amber for uncertainty, red for shortages that need attention. Status is
never color alone (each colored item also has an icon or a text label). Proposed allocations
are always labeled as proposed, never as approved or dispatched.
"""
from dash import html

from src.dashboard import SHORTAGE_STATUSES, diet_name, when

TAB_LABELS = {"intake": "Report intake", "review": "Review & finalize", "photos": "Warehouse photos", "chat": "Chat"}


def n(value):
    return f"{value:,}" if isinstance(value, (int, float)) else str(value)


def pct(share):
    return f"{round(share * 100)}%"


# ---- 1. current situation ---------------------------------------------------------------

def _figure(value, label, tone="neutral"):
    return html.Div(className=f"figure tone-{tone}", children=[
        html.Div(n(value), className="figure-value"),
        html.Div(label, className="figure-label"),
    ])


def situation(d):
    s = d["situation"]
    short = s["not_covered_meals"]
    segments = [html.Div(className="seg seg-covered", style={"width": f"{s['covered_share'] * 100:.2f}%"},
                         title=f"Covered by current stock: {n(s['covered_meals'])} meals")]
    if short:
        segments.append(html.Div(className="seg seg-short", style={"width": f"{(1 - s['covered_share']) * 100:.2f}%"},
                                 title=f"Not covered: {n(short)} meals"))
    return html.Section(className="dash-section", children=[
        html.H2("Current situation"),
        html.Div(className="figures", children=[
            _figure(s["available_meals"], "Available general meals"),
            _figure(s["unmet_meals"], "Total unmet demand"),
            _figure(s["additional_meals_needed"], "Additional meals needed",
                    "short" if s["additional_meals_needed"] else "neutral"),
        ]),
        html.Div(className="coverage", children=[
            html.Div(className="coverage-text", children=[
                html.Span(["Current stock covers ", html.B(pct(s["covered_share"])), " of unmet demand"]),
                html.Span(f"{n(short)} meals not covered", className="text-short") if short else
                html.Span("All unmet demand covered", className="text-ok"),
            ]),
            html.Div(segments, className="coverage-bar", role="img",
                     **{"aria-label": f"{pct(s['covered_share'])} of {n(s['unmet_meals'])} meals covered by "
                                      f"current stock; {n(short)} not covered"}),
        ]),
    ])


# ---- 2. actions required -------------------------------------------------------------------

def _action_item(a):
    """Compact: title and next step; "why it matters" is in the tooltip and in the map's details panel."""
    icon = "⛔" if a["severity"] == "shortage" else "⚠️"
    text = html.Div(className="action-text", children=[
        html.Div(className="action-title", children=[html.Span(icon, className="action-icon", **{"aria-hidden": "true"}),
                                                     html.Span(a["title"])]),
        html.Div(["Next step: ", a["next_step"]], className="action-next"),
    ])
    children = [text]
    if a.get("tab"):
        children.append(html.Button(f"Open {TAB_LABELS[a['tab']]} →", className="goto", n_clicks=0,
                                    id={"type": "goto-tab", "tab": a["tab"], "item": a["rank"]}))
    return html.Li(className=f"action compact sev-{a['severity']}", title=f"Why it matters: {a['why']}",
                   children=children)


def actions(d):
    items = d["actions"]
    if not items:
        return html.Section(className="dash-section", children=[
            html.H2("Actions required"), html.P("✓ No open issues in the current data.", className="text-ok")])
    return html.Section(className="dash-section", children=[
        html.H2(["Actions required ", html.Span(str(len(items)), className="count",
                                                title=f"{len(items)} open items")]),
        html.Ol([_action_item(a) for a in items], className="action-list"),
    ])


# ---- 3. allocation plan ------------------------------------------------------------------

def _plan_line(r, which):
    if which == "A":
        segs = [html.Div(className="seg seg-proposed", style={"width": f"{r['plan_a_share'] * 100:.2f}%"},
                         title=f"Proposed: {n(r['plan_a_meals'])} meals")]
        value = [html.Span(f"{n(r['plan_a_meals'])} proposed")]
        if r["plan_a_shortfall_meals"]:
            segs.append(html.Div(className="seg seg-short", style={"width": f"{r['plan_a_short_share'] * 100:.2f}%"},
                                 title=f"Still short: {n(r['plan_a_shortfall_meals'])} meals"))
            value.append(html.Span(f" · {n(r['plan_a_shortfall_meals'])} short", className="text-short"))
    else:
        segs = [html.Div(className="seg seg-proposed", style={"width": f"{r['plan_b_share'] * 100:.2f}%"},
                         title=f"Proposed: {n(r['plan_b_meals'])} meals")]
        value = [html.Span(f"{n(r['plan_b_meals'])} proposed")]
    return html.Div(className="plan-line", children=[
        html.Div(r["shelter_name"], className="plan-shelter"),
        html.Div(segs, className="plan-bar"),
        html.Div(value, className="plan-value"),
    ])


def _special(d):
    """Shortage (incl. no stock) in red, unknown demand in amber, confirmed zero distinct from "enough"."""
    rows = []
    for x in d["plans"]["special_diets"]:
        needed = n(x["needed_meals_known"])
        if x["demand"] == "unknown":
            needed = "unknown" if not x["needed_meals_known"] else f"{needed} + unknown"
        if x["status"] in SHORTAGE_STATUSES:
            state = f"⛔ {n(x['shortage_meals_known'])} short" + (" (none in stock)" if not x["available_meals"] else "")
            cls = "text-short"
        elif x["demand"] == "unknown":
            state, cls = "⚠️ count unknown", "text-uncertain"
        elif x["status"] == "ok" and x["demand"] == "zero":
            state, cls = "No unmet need", ""
        elif x["status"] == "ok":
            state, cls = "Enough in stock", ""
        else:                                            # any status not known to this view: never "enough"
            state, cls = f"⚠️ {x['status'].replace('_', ' ')}", "text-uncertain"
        rows.append(html.Tr([html.Td(diet_name(x["diet_category"]).capitalize()),
                             html.Td(needed), html.Td(n(x["available_meals"])),
                             html.Td(state, className=cls)]))
    return html.Table(className="simple-table", children=[
        html.Thead(html.Tr([html.Th("Diet"), html.Th("Needed (known)"), html.Th("In stock"), html.Th("Status")])),
        html.Tbody(rows)])


def _details(d):
    det = d["details"]
    a = det["assumptions"]
    shelters = html.Table(className="simple-table", children=[
        html.Thead(html.Tr([html.Th(h) for h in ("Shelter", "Evacuees", "On general meals", "Need", "On hand",
                                                  "On its way", "Unmet", "Validated report", "Newer report waiting")])),
        html.Tbody([html.Tr([html.Td(f"{s['shelter_name']} ({s['shelter_id']})"), html.Td(n(s["evacuees"])),
                             html.Td(n(s["general_people"])), html.Td(n(s["need_meals"])),
                             html.Td(n(s["on_hand_meals"])), html.Td(n(s["on_its_way_meals"])),
                             html.Td(n(s["unmet_meals"])),
                             html.Td(when(s["reported_at"]) + (f" · {s['validated_by']}" if s["validated_by"] else "")),
                             html.Td(when(s["newer_report_at"]) if s["newer_report_at"] else "—")])
                    for s in det["shelters"]])])
    items = [html.Li(f"{a['meals_per_person_per_day']:g} meals per person per day, "
                     f"{a['planning_window_hours']:g}-hour planning window")]
    if a.get("unmet_formula"):
        items.append(html.Li(f"Unmet = {a['unmet_formula']}"))
    if a.get("rounding"):
        items.append(html.Li(f"Rounding: {a['rounding']}"))
    items += [html.Li(f"Warehouse {wh}: last validated count {when(t)}")
              for wh, t in sorted(det["inventory_counted_at"].items())]
    if a.get("plan_fingerprint"):
        items.append(html.Li(f"Plan fingerprint {a['plan_fingerprint'][:12]} (changes whenever the data changes)"))
    parts = [html.Details([html.Summary("Shelter details"), shelters]),
             html.Details([html.Summary("Assumptions and timestamps"), html.Ul(items)])]
    if det["data_warnings"]:
        parts.append(html.Details([html.Summary(f"All data notes ({len(det['data_warnings'])})"),
                                   html.Ul([html.Li(w) for w in det["data_warnings"]])]))
    return html.Div(parts, className="expanders")


def allocation_plan(d):
    p = d["plans"]
    a_summary = [html.B(n(p["plan_a_total_meals"])), " meals proposed from current stock"]
    if p["shortage_meals"]:
        a_summary.append(html.Span(f" · {n(p['shortage_meals'])} still short", className="text-short"))
    b_summary = [html.B(n(p["total_unmet_meals"])), " meals proposed"]
    if isinstance(p["plan_b_procurement_meals"], int) and p["plan_b_procurement_meals"]:
        b_summary.append(html.Span(f" · {n(p['plan_b_procurement_meals'])} must be procured", className="text-short"))
    return html.Section(className="dash-section", children=[
        html.H2("Allocation plan"),
        html.P("Proposed only: nothing has been approved, reserved, or dispatched. General meals; special diets "
               "are planned separately below.", className="plan-note"),
        html.Div(className="legend", children=[
            html.Span([html.I(className="key seg-proposed"), "Proposed allocation"]),
            html.Span([html.I(className="key seg-short"), "Remaining shortage"])]),
        html.Div(className="plan-cols", children=[
            html.Div(className="plan-col", children=[
                html.H3("Plan A · uses available inventory"),
                html.P(a_summary, className="plan-summary"),
                *[_plan_line(r, "A") for r in p["rows"]]]),
            html.Div(className="plan-col", children=[
                html.H3("Plan B · requires additional procurement"),
                html.P(b_summary, className="plan-summary"),
                *[_plan_line(r, "B") for r in p["rows"]]]),
        ]),
        html.H3("Special diets (separate from general meals)"),
        _special(d),
        _details(d),
    ])


def render_top(d):
    return html.Div(className="dash", children=[situation(d), actions(d)])


def render_bottom(d):
    return html.Div(className="dash", children=[allocation_plan(d)])


def render_dashboard(d):
    """Whole dashboard without the map (the map is a fixed component in app.py)."""
    return html.Div(className="dash", children=[situation(d), actions(d), allocation_plan(d)])
