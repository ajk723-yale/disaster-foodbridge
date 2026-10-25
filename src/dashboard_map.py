"""Dashboard map: shelters and warehouses on a FICTIONAL training layout, plus a details panel.

The sample records contain no coordinates, so positions come from a separate file that must be
labeled fictional (load_training_locations refuses anything else). Positions are schematic x/y,
not latitude/longitude, and no basemap is drawn, so nothing looks like a real place. The map
shows no distances, routes, or travel times.

Marker status comes only from the dashboard data (src.dashboard), i.e. the existing calculations:
red = shortage after Plan A (general or special diet), amber = no validated report,
amber ring = pending or unknown information, gray = no shortage. Warehouses are squares.
"""
import json

import plotly.graph_objects as go
from dash import html

from src import config
from src.dashboard import diet_name, when

COLORS = {"shortage": "#e5484d", "no_report": "#fab219", "ok": "#b9b4bd", "ring": "#fab219",
          "warehouse": "#8f8a96", "selected": "#ff4fa3", "surface": "#16161a", "grid": "#24242b",
          "text": "#f3eef2", "muted": "#a79aa3"}
PENDING_KINDS = ("pending_report", "unknown_special_count", "other_note", "pending_inventory_count")
TAB_LABELS = {"intake": "Report intake", "review": "Review & finalize"}


class NotFictionalError(ValueError):
    """The locations file is not labeled as fictional training data."""


def load_training_locations(path=None):
    path = path or config.TRAINING_LOCATIONS_PATH
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if data.get("fictional") is not True or "FICTIONAL" not in data.get("label", "").upper():
        raise NotFictionalError(f"{path} is not labeled as fictional training locations; refusing to map it")
    return data


def _actions_for(d, place_id):
    return [a for a in d["actions"] if place_id in a.get("places", [])]


def map_entities(d, locations):
    """Shelters and warehouses with status, panel facts, and fictional positions."""
    pos = {loc["id"]: loc for loc in locations["locations"]}
    plan = {r["shelter_id"]: r for r in d["plans"]["rows"]}
    entities = []
    for s in d["details"]["shelters"]:
        sid, acts = s["shelter_id"], _actions_for(d, s["shelter_id"])
        short = plan.get(sid, {}).get("plan_a_shortfall_meals", 0)
        special_short = any(a["kind"] == "special_diet_shortage" for a in acts)
        entities.append({
            "id": sid, "kind": "shelter", "name": s["shelter_name"], "has_report": True,
            "status": "shortage" if short or special_short else "ok",
            "pending": any(a["kind"] in PENDING_KINDS for a in acts),
            "facts": {"unmet_meals": s["unmet_meals"], "need_meals": s["need_meals"],
                      "general_people": s["general_people"], "evacuees": s["evacuees"],
                      "on_hand_meals": s["on_hand_meals"], "on_its_way_meals": s["on_its_way_meals"],
                      "plan_a_meals": plan.get(sid, {}).get("plan_a_meals"), "shortfall_meals": short,
                      "special_diets": s["special_diets"], "reported_at": s["reported_at"],
                      "validated_by": s["validated_by"]},
            "actions": acts})
    for m in d.get("missing_shelters", []):
        entities.append({"id": m["shelter_id"], "kind": "shelter", "name": m["shelter_name"], "has_report": False,
                         "status": "no_report", "pending": True,
                         "facts": {"pending_report_at": m.get("pending_report_at")},
                         "actions": _actions_for(d, m["shelter_id"])})
    for w in d["details"].get("warehouses", []):
        acts = _actions_for(d, w["warehouse_id"])
        entities.append({"id": w["warehouse_id"], "kind": "warehouse", "name": f"Warehouse {w['warehouse_id']}",
                         "status": "ok", "pending": bool(w["pending_counts"]) or bool(acts),
                         "facts": {"items": w["items"]}, "actions": acts})
    for e in entities:
        loc = pos.get(e["id"])
        e["x"], e["y"] = (loc["x"], loc["y"]) if loc else (None, None)
    return entities


STATUS_TEXT = {"shortage": "⛔ Short after Plan A", "no_report": "❓ No validated report", "ok": "No shortage"}


def _hover(e):
    if e["kind"] == "warehouse":
        return f"{e['name']}" + ("<br>⚠ newer count pending" if e["pending"] else "")
    return f"{e['name']} ({e['id']})<br>{STATUS_TEXT[e['status']]}" + (
        "<br>⚠ pending or unknown information" if e["pending"] and e["has_report"] else "")


def map_figure(entities, selected=None):
    fig = go.Figure()
    placed = [e for e in entities if e["x"] is not None]
    for kind, symbol, size in (("warehouse", "square", 20), ("shelter", "circle", 26)):
        pts = [e for e in placed if e["kind"] == kind]
        if not pts:
            continue
        fill = [COLORS["warehouse"] if kind == "warehouse" else COLORS[e["status"]] for e in pts]
        ring = [COLORS["ring"] if e["pending"] and e["status"] != "no_report" else COLORS["surface"] for e in pts]
        fig.add_trace(go.Scatter(
            x=[e["x"] for e in pts], y=[e["y"] for e in pts], mode="markers+text", name=kind,
            text=[e["id"] for e in pts], textposition="bottom center",
            textfont={"color": COLORS["text"], "size": 13},
            customdata=[e["id"] for e in pts], hovertext=[_hover(e) for e in pts], hoverinfo="text",
            marker={"symbol": symbol, "size": size, "color": fill, "line": {"color": ring, "width": 4}}))
    sel = next((e for e in placed if e["id"] == selected), None)
    if sel:
        fig.add_trace(go.Scatter(x=[sel["x"]], y=[sel["y"]], mode="markers", hoverinfo="skip", name="selected",
                                 marker={"symbol": "circle-open" if sel["kind"] == "shelter" else "square-open",
                                         "size": 42, "color": COLORS["selected"],  # open symbols use color
                                         "line": {"color": COLORS["selected"], "width": 3}}))
    xs = [e["x"] for e in placed] or [0, 10]
    ys = [e["y"] for e in placed] or [0, 10]
    pad = 1.4
    axis = {"showticklabels": False, "zeroline": False, "showgrid": True, "gridcolor": COLORS["grid"],
            "fixedrange": True, "title": None}
    fig.update_layout(
        showlegend=False, dragmode=False, hovermode="closest", height=430,
        margin={"l": 8, "r": 8, "t": 50, "b": 8}, paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["surface"],
        xaxis={**axis, "range": [min(xs) - pad, max(xs) + pad]},
        yaxis={**axis, "range": [min(ys) - pad, max(ys) + pad]},
        font={"color": COLORS["text"]},
        annotations=[{"text": "FICTIONAL TRAINING LAYOUT — not real locations<br>No distances, routes, or travel times",
                      "xref": "paper", "yref": "paper", "x": 0, "y": 1.02, "xanchor": "left", "yanchor": "bottom",
                      "align": "left", "showarrow": False,
                      "font": {"color": COLORS["muted"], "size": 12}}])
    return fig


def legend():
    def key(cls, label):
        return html.Span([html.I(className=f"map-key {cls}"), label])
    return html.Div(className="legend", children=[
        key("mk-short", "Short after Plan A"), key("mk-noreport", "No validated report"),
        key("mk-ring", "Pending or unknown info"), key("mk-ok", "No shortage"), key("mk-wh", "Warehouse")])


def _num(v):
    return f"{v:,}" if isinstance(v, (int, float)) else str(v)


def _fact(label, value, cls=""):
    return html.Div(className="panel-fact", children=[html.Span(label, className="panel-label"),
                                                      html.Span(value, className=f"panel-value {cls}")])


def _panel_actions(e):
    if not e["actions"]:
        return html.P("No data issues for this location.", className="muted")
    items = []
    for a in e["actions"]:
        children = [html.Div(("⛔ " if a["severity"] == "shortage" else "⚠️ ") + a["title"], className="panel-issue"),
                    html.P(a["why"], className="panel-why"), html.P(["Next step: ", a["next_step"]],
                                                                     className="panel-next")]
        if a.get("tab"):
            children.append(html.Button(f"Open {TAB_LABELS.get(a['tab'], a['tab'])} →", className="goto", n_clicks=0,
                                        id={"type": "goto-tab", "tab": a["tab"], "item": f"map-{e['id']}-{a['rank']}"}))
        items.append(html.Li(children, className=f"sev-{a['severity']}"))
    return html.Ul(items, className="panel-issues")


def details_panel(e):
    """Panel for one selected entity (or a prompt when nothing is selected)."""
    if e is None:
        return html.Div(className="map-panel-empty", children=[
            html.P("Select a shelter or warehouse on the map to see its details."),
            html.P("Positions are fictional (training layout).", className="muted")])
    f = e["facts"]
    head = html.Div(className="panel-head", children=[
        html.Div(e["name"], className="panel-name"),
        html.Div(e["id"] if e["kind"] == "shelter" else "Warehouse", className="muted")])
    note = html.P("Map position is fictional (training layout).", className="muted panel-foot")
    if e["kind"] == "warehouse":
        rows = [html.Li(f"{i['item_name']}: {_num(i['quantity'])} {i['unit']}"
                        + (f" ({_num(i['meal_equivalents'])} meals)" if i.get("counts_as_meals") else " (not meals)")
                        + f" · counted {when(i['counted_at'])}") for i in f["items"]]
        return html.Div([head, html.Div("Validated stock counts", className="panel-section"),
                         html.Ul(rows, className="panel-list"),
                         html.P("Counts before reservations and dispatches; available meals are in Current "
                                "situation.", className="muted"),
                         html.Div("Issues", className="panel-section"), _panel_actions(e), note])
    if not e["has_report"]:                      # the issue below explains why and what to do
        return html.Div([head, html.Div(STATUS_TEXT["no_report"], className="panel-status st-no_report"),
                         html.Div("Issues", className="panel-section"), _panel_actions(e), note])
    short = f["shortfall_meals"] or 0
    special = [html.Li(f"{diet_name(x['diet_category']).capitalize()}: "
                       + (f"{_num(x['people'])} people · {_num(x['unmet_meals'])} "
                          f"{'meal' if x['unmet_meals'] == 1 else 'meals'} unmet"
                          if x["unmet_meals"] is not None else "count unknown"))
               for x in f["special_diets"]]
    return html.Div([
        head,
        html.Div(STATUS_TEXT[e["status"]], className=f"panel-status st-{e['status']}"),
        _fact("Validated demand (unmet)", f"{_num(f['unmet_meals'])} meals"),
        html.P(f"Need {_num(f['need_meals'])} for {_num(f['general_people'])} people on general meals; "
               f"{_num(f['on_hand_meals'])} on hand, {_num(f['on_its_way_meals'])} on its way.",
               className="muted panel-sub"),
        _fact("Plan A (proposed)", f"{_num(f['plan_a_meals'])} meals"),
        _fact("Remaining shortage", f"{_num(short)} meals", "text-short" if short else ""),
        html.Div("Special diets", className="panel-section") if special else None,
        html.Ul(special, className="panel-list") if special else None,
        html.Div("Issues", className="panel-section"), _panel_actions(e),
        html.P(f"Validated report {when(f['reported_at'])}" + (f" · {f['validated_by']}" if f["validated_by"] else ""),
               className="muted panel-foot"),
        note,
    ])


def find(entities, entity_id):
    return next((e for e in entities if e["id"] == entity_id), None)
