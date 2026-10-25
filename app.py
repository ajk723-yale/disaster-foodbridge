"""Disaster FoodBridge — minimal Dash chat interface plus staff review and finalization.

The chat calls src.agent.run_agent(); everything agent-related lives behind it.
Finalization is staff-only: the "Review & finalize" section calls the SQLite
finalization logic directly. The agent has no way to finalize.
Run with debug and the reloader off so one edit doesn't spawn extra servers.
"""
import base64
import json
import logging
import os
import re
import shutil
import tempfile
from dash import ALL, Dash, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

from src import config
from src.agent import run_agent
from src.agent_tools import planning_config
from src.dashboard import load_dashboard
from src.dashboard_map import details_panel, find, legend, load_training_locations, map_entities, map_figure
from src.dashboard_view import render_bottom, render_top
from src.extraction import extract_shelter_report
from src.finalization import finalize_and_store, get_saved_request, list_finalized_plans, review_plan
from src.intake import EDITABLE_FIELDS, approve_extracted_report, local_time_input
from src.llm import AgentError
from src.request_format import format_request_markdown
from src.timeutil import display_time, utc_iso, utc_now
from src.records import latest_validated
from src.store import load_inventory_log
from src.vision import analyze_warehouse_photo, ask_about_photo, load_photo_analysis, photo_folder
from src.workspace import ensure_working_data

app = Dash(__name__, title="Disaster FoodBridge",
           assets_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets"))

app.layout = html.Div(className="page", children=[
    html.Header(className="header", children=[
        html.H1("Disaster FoodBridge"),
        html.P("Shelter food allocation assistant"),
    ]),
    html.Nav(className="tabs", children=[
        html.Button("📊 Dashboard", id="tab-dashboard", className="tab active", n_clicks=0),
        html.Button("Chat", id="tab-chat", className="tab", n_clicks=0),
        html.Button("Report intake", id="tab-intake", className="tab", n_clicks=0),
        html.Button("Warehouse photos", id="tab-photos", className="tab", n_clicks=0),
        html.Button("Review & finalize", id="tab-review", className="tab", n_clicks=0),
    ]),
    html.Section(id="dashboard-section", className="review dashboard", children=[
        html.Div(className="dash-toolbar", children=[
            html.Button("↻ Refresh", id="dashboard-refresh", className="send", n_clicks=0),
        ]),
        dcc.Loading(html.Div(id="dashboard-top"), type="dot", color="#ff4fa3"),
        html.Section(className="dash dash-section map-section", children=[
            html.H2("Map"),
            html.Div(className="map-row", children=[
                dcc.Graph(id="dash-map", className="map-graph", figure=map_figure([]),
                          config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False}),
                html.Div(id="map-panel", className="map-panel", role="region", **{"aria-live": "polite"},
                         children=details_panel(None)),
            ]),
            legend(),
            html.Div(id="map-unplaced", className="muted"),
        ]),
        html.Div(id="dashboard-bottom"),
        dcc.Store(id="map-entities", data=[]),
        dcc.Store(id="map-selected", data=None),
    ]),
    html.Main(id="chat-section", className="chat", style={"display": "none"}, children=[
        html.Div(id="messages", className="messages", role="log", **{"aria-live": "polite"}),
        dcc.Checklist(id="show-tools", className="tool-toggle",
                      options=[{"label": " Show tool activity", "value": "on"}], value=[]),
        html.Div(className="composer", children=[
            dcc.Textarea(id="message-input", placeholder="Type a message… (Enter to send, Shift+Enter for a new line)",
                         rows=2, className="input"),
            html.Button("Send", id="send", className="send", n_clicks=0),
        ]),
    ]),
    html.Section(id="review-section", className="review", style={"display": "none"}, children=[
        html.P("Staff only. Review Plan A from the latest validated data, acknowledge each data warning with "
               "a reason, then confirm. Finalizing records approved allocations; it does not dispatch food "
               "or send any request.", className="muted"),
        html.Button("Load current plan", id="load-plan", className="send", n_clicks=0),
        html.Div(id="review-notice", role="status"),
        html.Div(id="review-body"),
        html.Div(className="finalize-box", children=[
            dcc.Input(id="staff-name", type="text", placeholder="Your name (required)", className="text-input"),
            dcc.Checklist(id="confirm-finalize", value=[], options=[
                {"label": " I have reviewed this Plan A and confirm finalization", "value": "yes"}]),
            html.Button("Finalize", id="finalize", className="send", n_clicks=0, disabled=True),
        ]),
        html.Div(id="finalize-result", role="status"),
        html.H3("Saved plans and their draft supply requests"),
        html.Div(className="finalize-box", children=[
            dcc.Dropdown(id="saved-plan-select", placeholder="Choose a finalized plan", className="plan-select"),
            html.Button("Show saved request", id="show-saved-request", className="send", n_clicks=0),
        ]),
        html.Div(id="saved-request"),
    ]),
    html.Section(id="intake-section", className="review", style={"display": "none"}, children=[
        html.P("Staff only. Paste a free-text shelter report and extract its fields with AI. Nothing is saved "
               "until you check and correct the fields and approve the report; it is then added to the shelter "
               "report log as validated data.", className="muted"),
        dcc.Textarea(id="intake-text", rows=5, className="input intake-text",
                     placeholder="Paste the shelter's report here (English or Japanese)"),
        html.Button("Extract fields", id="run-extraction", className="send", n_clicks=0),
        dcc.Loading(html.Div(id="intake-message", role="status"), type="dot", color="#ff4fa3"),
        html.Div(id="intake-safety", role="alert"),
        html.Div(id="intake-form", style={"display": "none"}, children=[
            html.Div(className="intake-grid", children=[
                html.Div(className="intake-original", children=[
                    html.H3("Original report (kept as is)"),
                    html.Pre(id="intake-original"),
                    html.H3("Warnings from extraction"),
                    html.Div(id="intake-warnings"),
                ]),
                html.Div(className="intake-fields", children=[
                    html.H3("Fields (correct before approving)"),
                    html.Label([html.Span("Shelter ID"), dcc.Input(id="intake-shelter_id", type="text", className="text-input", debounce=False)], className="field"),
                    html.Label([html.Span("Shelter name"), dcc.Input(id="intake-shelter_name", type="text", className="text-input", debounce=False)], className="field"),
                    html.Label([html.Span("Report time (YYYY-MM-DD HH:MM, display timezone)"), dcc.Input(id="intake-reported_at", type="text", className="text-input", debounce=False)], className="field"),
                    html.Label([html.Span("Evacuee count"), dcc.Input(id="intake-evacuee_count", type="text", className="text-input", debounce=False)], className="field"),
                    html.Label([html.Span("General meals on hand"), dcc.Input(id="intake-general_on_hand_meals", type="text", className="text-input", debounce=False)], className="field"),
                    html.Label([html.Span("Special needs (tag:people; …, ? = unknown)"), dcc.Input(id="intake-special_needs", type="text", className="text-input", debounce=False)], className="field"),
                    html.Label([html.Span("Special-diet meals on hand (tag:meals; …)"), dcc.Input(id="intake-special_on_hand_meals", type="text", className="text-input", debounce=False)], className="field"),
                ]),
            ]),
            html.Div(className="finalize-box", children=[
                dcc.Input(id="intake-staff", type="text", placeholder="Your name (required)", className="text-input"),
                dcc.Checklist(id="intake-confirm", value=[], options=[
                    {"label": " I checked these fields against the original report and approve them", "value": "yes"}]),
                html.Button("Approve and save as validated", id="approve-report", className="send", n_clicks=0),
            ]),
        ]),
        html.Div(id="intake-result", role="status"),
    ]),
    html.Section(id="photos-section", className="review", style={"display": "none"}, children=[
        html.P("Staff only, read-only. Upload a warehouse photo and choose the warehouse. AI identifies visible "
               "items and compares them with the latest validated inventory records. A photo may show only part of "
               "the warehouse, and nothing here changes inventory records or allocation plans.", className="muted"),
        html.Div(className="finalize-box", children=[
            dcc.Upload(id="photo-upload", className="upload", accept="image/png,image/jpeg,image/webp",
                       max_size=10 * 1024 * 1024, multiple=False,
                       children=html.Div(["Drop a photo here or ", html.Span("choose a file", className="link")])),
            dcc.Dropdown(id="photo-warehouse", placeholder="Warehouse", className="plan-select warehouse-select"),
            html.Button("Analyze photo", id="analyze-photo", className="send", n_clicks=0),
        ]),
        html.Div(id="photo-upload-name", className="muted"),
        dcc.Loading(html.Div(id="photo-message", role="status"), type="dot", color="#ff4fa3"),
        html.Div(id="photo-result"),
        html.Div(id="photo-followup-box", style={"display": "none"}, children=[
            html.H3("Follow-up questions about this image"),
            html.Div(className="composer", children=[
                dcc.Input(id="photo-question", type="text", className="text-input photo-question",
                          placeholder="e.g. Which label could you not read?"),
                html.Button("Ask", id="ask-photo", className="send", n_clicks=0),
            ]),
            dcc.Loading(html.Div(id="photo-followups"), type="dot", color="#ff4fa3"),
        ]),
    ]),
    dcc.Store(id="photo-analysis-id", data=None),  # analysis shown in the photos tab
    dcc.Store(id="intake-extraction", data=None),  # extraction awaiting staff review (not saved)
    dcc.Store(id="review-plan", data=None),  # the plan staff are reviewing (incl. its fingerprint)
    dcc.Store(id="history", data=[]),    # [{"role", "content", "tool_events"?}]
    dcc.Store(id="pending", data=None),  # message waiting for the agent
])


def markdown_safe(text):
    """Escape [brackets] that aren't real [text](url) links, so placeholders such as
    [DATE] are shown as written instead of being turned into empty links."""
    return re.sub(r"\[([^\[\]\n]+)\](?!\()", r"\\[\1\\]", text)


def render_messages(history, pending, show_tools):
    labels = {"user": "You", "assistant": "FoodBridge", "error": "Error"}
    bubbles = []
    for m in history:
        text = (dcc.Markdown(markdown_safe(m["content"]), className="text markdown") if m["role"] == "assistant"
                else html.Div(m["content"], className="text"))
        children = [html.Div(labels[m["role"]], className="role"), text]
        if show_tools and m.get("tool_events"):
            children.append(html.Details(className="tools", children=[
                html.Summary(f"Tool activity ({len(m['tool_events'])})"),
                html.Ul([html.Li([html.Code(e["tool"]), f" — {e['detail']}"]) for e in m["tool_events"]]),
            ]))
        bubbles.append(html.Div(children, className=f"bubble {m['role']}"))
    if pending:
        bubbles.append(html.Div(className="bubble assistant thinking", children=[
            html.Div("FoodBridge", className="role"),
            html.Div([html.Span(className="dot") for _ in range(3)], className="dots",
                     **{"aria-label": "FoodBridge is thinking"}),
        ]))
    if not bubbles:
        bubbles = [html.Div("Ask about shelters, inventory, or today's allocation.", className="empty")]
    return bubbles


# Each callback renders the chat itself. A separate render callback listening to
# `history` would be held back by Dash until the agent finishes, hiding the
# user's message and the thinking indicator.
@app.callback(
    Output("history", "data", allow_duplicate=True),
    Output("pending", "data"),
    Output("message-input", "value"),
    Output("messages", "children", allow_duplicate=True),
    Output("send", "disabled", allow_duplicate=True),
    Input("send", "n_clicks"),
    State("message-input", "value"),
    State("history", "data"),
    State("pending", "data"),
    State("show-tools", "value"),
    prevent_initial_call=True,
)
def submit(_, text, history, pending, show_tools):
    """Show the user's message and the thinking indicator right away, then queue it for the agent."""
    if pending or not text or not text.strip():
        raise PreventUpdate
    text = text.strip()
    history = history + [{"role": "user", "content": text}]
    return history, text, "", render_messages(history, text, show_tools), True


@app.callback(
    Output("history", "data"),
    Output("pending", "data", allow_duplicate=True),
    Output("messages", "children", allow_duplicate=True),
    Output("send", "disabled"),
    Input("pending", "data"),
    State("history", "data"),
    State("show-tools", "value"),
    prevent_initial_call=True,
)
def respond(pending, history, show_tools):
    if not pending:
        raise PreventUpdate
    prior = [{"role": m["role"], "content": m["content"]} for m in history[:-1] if m["role"] != "error"]
    try:
        result = run_agent(pending, prior)
        reply = {"role": "assistant", "content": result["reply"], "tool_events": result.get("tool_events", [])}
    except Exception as exc:  # show a recoverable error instead of breaking the chat
        reply = {"role": "error", "content": f"Something went wrong: {exc}. You can try sending again."}
    history = history + [reply]
    return history, None, render_messages(history, None, show_tools), False


@app.callback(
    Output("messages", "children"),
    Input("show-tools", "value"),
    State("history", "data"),
    State("pending", "data"),
)
def toggle_tools(show_tools, history, pending):
    return render_messages(history, pending, show_tools)


# ---- Review & finalize (staff only) ------------------------------------------

def _paths():
    return (config.FINALIZATION_DB_PATH, config.SHELTER_LOG_PATH, config.INVENTORY_LOG_PATH,
            config.COMMITMENTS_LOG_PATH)


def _table(header, rows):
    return html.Table(className="review-table", children=[
        html.Thead(html.Tr([html.Th(h) for h in header])),
        html.Tbody([html.Tr([html.Td(c) for c in row]) for row in rows]),
    ])


def render_review(plan):
    if not plan:
        return [html.P("No plan loaded.", className="muted")]
    g = plan["general"]
    general = _table(["Shelter", "Unmet meals", "Plan A meals", "Shortfall"],
                     [[f"{l['shelter_name']} ({l['shelter_id']})", l["unmet_meals"], l["allocated_meals"],
                       l["shortfall_meals"]] for l in g["lines"]])
    action = {"ok": None, "shortage": "staff decision (stock short)", "no_stock": "staff decision (no stock)",
              "missing_info": "confirm counts first"}
    special_rows = []
    for grp in plan["special"]:
        per_shelter = ", ".join(f"{l['shelter_id']}: {l['suggested_meals']}" for l in grp["lines"]
                                if l["suggested_meals"])
        special_rows.append([grp["diet_tag"], grp["status"], grp["available_meals"], grp["total_unmet_meals"],
                             action[grp["status"]] or per_shelter or "none"])
    warnings = plan["pending_data_warnings"]
    warning_items = [html.Div(className="warning", children=[
        html.P(w["message"]),
        dcc.Checklist(id={"type": "ack-check", "index": w["warning_id"]}, value=[],
                      options=[{"label": " Acknowledge: proceed without this data", "value": "yes"}]),
        dcc.Textarea(id={"type": "ack-reason", "index": w["warning_id"]}, rows=2, className="input",
                     placeholder="Reason for proceeding without this data (required)"),
    ]) for w in warnings]
    notes = [f"{f['diet_tag']}{' at ' + f['shelter_id'] if f['shelter_id'] else ''}: {f['message']}"
             for f in plan["flags"]]
    return [
        html.H3("Plan A: general meals"),
        html.P(f"Available {g['available_meals']} · unmet {g['total_unmet_meals']} · Plan A "
               f"{g['allocated_meals']} · shortage {g['shortage_meals']} meals "
               f"({plan['config']['meals_per_person_per_day']:g} meals/person/day, "
               f"{plan['config']['planning_window_hours']:g} h)"),
        general,
        html.H3("Special diets (separate)"),
        _table(["Diet", "Status", "Available", "Unmet (known)", "Plan A"], special_rows) if special_rows
        else html.P("No special-diet needs.", className="muted"),
        html.H3(f"Data warnings to acknowledge ({len(warnings)})"),
        *(warning_items or [html.P("No pending-data warnings.", className="muted")]),
        html.H3("Other data notes"),
        html.Ul([html.Li(n) for n in notes]) if notes else html.P("None.", className="muted"),
    ]


TABS = ("dashboard", "chat", "intake", "photos", "review")


@app.callback(
    *[Output(f"{t}-section", "style") for t in TABS], *[Output(f"tab-{t}", "className") for t in TABS],
    *[Input(f"tab-{t}", "n_clicks") for t in TABS],
    Input({"type": "goto-tab", "tab": ALL, "item": ALL}, "n_clicks"),  # buttons in the dashboard's action list
    prevent_initial_call=True,
)
def switch_tab(*_):
    trigger = ctx.triggered_id
    if isinstance(trigger, dict):                 # a dashboard "Open … →" button
        if not ctx.triggered[0]["value"]:         # buttons being (re)rendered, not clicked
            raise PreventUpdate
        active = trigger["tab"]
    else:
        active = (trigger or "tab-dashboard").removeprefix("tab-")
    return ([{} if t == active else {"display": "none"} for t in TABS]
            + ["tab active" if t == active else "tab" for t in TABS])


@app.callback(
    Output("dashboard-top", "children"), Output("dashboard-bottom", "children"),
    Output("dash-map", "figure"), Output("map-entities", "data"), Output("map-panel", "children"),
    Output("map-unplaced", "children"),
    Input("tab-dashboard", "n_clicks"), Input("dashboard-refresh", "n_clicks"),
    State("map-selected", "data"),
)
def show_dashboard(_, __, selected):
    """Read-only overview from the latest validated data (same calculations as the chat tools)."""
    try:
        d = load_dashboard()
        top, bottom = render_top(d), render_bottom(d)
    except Exception as exc:  # show the problem instead of a blank tab
        logging.getLogger(__name__).exception("dashboard failed")
        return (html.P(f"Dashboard could not be built: {type(exc).__name__}: {exc}", className="error-text"),
                None, map_figure([]), [], details_panel(None), "")
    try:
        entities = map_entities(d, load_training_locations())
    except Exception as exc:  # the rest of the dashboard still works without the map
        logging.getLogger(__name__).exception("map failed")
        return top, bottom, map_figure([]), [], html.P(f"Map unavailable: {type(exc).__name__}: {exc}",
                                                       className="error-text"), ""
    current = find(entities, selected)
    unplaced = [e["id"] for e in entities if e["x"] is None]
    note = f"Not on the map (no training position): {', '.join(unplaced)}" if unplaced else ""
    return top, bottom, map_figure(entities, selected if current else None), entities, details_panel(current), note


@app.callback(
    Output("map-selected", "data"), Output("map-panel", "children", allow_duplicate=True),
    Output("dash-map", "figure", allow_duplicate=True),
    Input("dash-map", "clickData"), State("map-entities", "data"),
    prevent_initial_call=True,
)
def select_on_map(click, entities):
    """Selecting a marker shows that shelter's or warehouse's details beside the map (read-only)."""
    if not click or not click.get("points"):
        raise PreventUpdate
    entity_id = click["points"][0].get("customdata")
    entity = find(entities or [], entity_id)
    if entity is None:
        raise PreventUpdate
    return entity_id, details_panel(entity), map_figure(entities, entity_id)


@app.callback(
    Output("review-plan", "data"), Output("review-notice", "children"),
    Output("finalize-result", "children"), Output("confirm-finalize", "value"),
    Input("load-plan", "n_clicks"),
    prevent_initial_call=True,
)
def load_plan(_):
    plan = review_plan(*_paths(), planning_config())
    loaded = display_time(utc_now(), fmt="%Y-%m-%d %H:%M:%S %Z")
    return plan, html.P(f"Plan loaded {loaded}. Review it, then acknowledge any warnings.", className="notice"), "", []


@app.callback(
    Output("review-body", "children"), Output("finalize", "disabled"),
    Input("review-plan", "data"),
)
def show_review(plan):
    return render_review(plan), not plan


@app.callback(
    Output("finalize-result", "children", allow_duplicate=True),
    Output("review-plan", "data", allow_duplicate=True),
    Output("review-notice", "children", allow_duplicate=True),
    Output("confirm-finalize", "value", allow_duplicate=True),
    Input("finalize", "n_clicks"),
    State("review-plan", "data"), State("staff-name", "value"), State("confirm-finalize", "value"),
    State({"type": "ack-check", "index": ALL}, "value"), State({"type": "ack-check", "index": ALL}, "id"),
    State({"type": "ack-reason", "index": ALL}, "value"), State({"type": "ack-reason", "index": ALL}, "id"),
    prevent_initial_call=True,
)
def finalize(_, plan, staff, confirm, checks, check_ids, reasons, reason_ids):
    if not plan:
        raise PreventUpdate
    if not (staff or "").strip():
        return html.P("Enter your name before finalizing.", className="error-text"), no_update, no_update, no_update
    if "yes" not in (confirm or []):
        return (html.P("Tick the confirmation box to finalize.", className="error-text"),
                no_update, no_update, no_update)
    reason_by_id = {rid["index"]: (r or "") for rid, r in zip(reason_ids, reasons)}
    acks = [{"warning_id": cid["index"], "reason": reason_by_id.get(cid["index"], "")}
            for cid, value in zip(check_ids, checks) if "yes" in (value or [])]
    at = utc_iso(utc_now())
    result = finalize_and_store(*_paths(), planning_config(), plan["fingerprint"], staff.strip(), at,
                                acknowledgements=acks)

    if result["status"] == "finalized":
        snap = result["snapshot"]
        saved = get_saved_request(config.FINALIZATION_DB_PATH, result["plan_id"])
        return (html.Div(className="success", children=[
            html.P(["Finalized. Plan ID: ", html.Strong(result["plan_id"], id="saved-plan-id")]),
            html.P(f"By {snap['finalized_by']} at {display_time(snap['finalized_at'])}: "
                   f"{len(result['commitments'])} approved allocation lines, "
                   f"{len(snap['acknowledgements'])} acknowledged warnings. The draft supply request below was "
                   "saved with this plan."),
            html.Div(className="request-draft", id="finalized-request",
                     children=dcc.Markdown(markdown_safe(format_request_markdown(saved)))),
        ]), None, html.P("Plan finalized. Load the current plan to review the next one.", className="notice"), [])
    if result["status"] == "needs_confirmation":
        return (html.P("Not finalized: the data or warnings changed since this plan was loaded. The updated plan "
                       "is shown below; review it and acknowledge its warnings again.", className="error-text"),
                result["plan"], html.P("Updated plan loaded after a data change. Previous acknowledgements were "
                                       "cleared.", className="notice"), [])
    if result["status"] == "acknowledgement_required":
        subjects = {w["warning_id"]: w["subject"] for w in result["warnings"]}
        return (html.Div(className="error-text", children=[
            html.P("Not finalized: every data warning needs to be acknowledged with a reason."),
            html.Ul([html.Li(f"{subjects.get(p['warning_id'], p['warning_id'])}: {p['problem']}")
                     for p in result["problems"]]),
        ]), no_update, no_update, no_update)
    if result["status"] == "already_finalized":
        return (html.P(f"Already finalized as plan {result['plan_id']} by {result['finalized_by']} at "
                       f"{display_time(result['finalized_at'])}. Load the current plan to review the next one.",
                       className="error-text"), None, no_update, [])
    raise PreventUpdate


@app.callback(
    Output("saved-plan-select", "options"),
    Input("tab-review", "n_clicks"), Input("finalize-result", "children"),
)
def refresh_saved_plans(_, __):
    return [{"label": f"{pid} · {display_time(at)} · {by}", "value": pid}
            for pid, by, at in list_finalized_plans(config.FINALIZATION_DB_PATH)]


@app.callback(
    Output("saved-request", "children"),
    Input("show-saved-request", "n_clicks"),
    State("saved-plan-select", "value"),
    prevent_initial_call=True,
)
def show_saved_request(_, plan_id):
    if not plan_id:
        return html.P("Choose a finalized plan first.", className="error-text")
    saved = get_saved_request(config.FINALIZATION_DB_PATH, plan_id)
    if not saved:
        return html.P(f"No saved request for plan {plan_id}.", className="error-text")
    return html.Div(className="request-draft", children=dcc.Markdown(markdown_safe(format_request_markdown(saved))))


# ---- Report intake (staff only) -----------------------------------------------

def _issue_list(issues):
    if not issues:
        return html.P("None.", className="muted")
    return html.Ul([html.Li(f"[{i['source']}] {i['field']} ({i['kind']}): {i['message']}") for i in issues])


@app.callback(
    Output("intake-extraction", "data"), Output("intake-message", "children"), Output("intake-form", "style"),
    Output("intake-original", "children"), Output("intake-warnings", "children"),
    *[Output(f"intake-{f}", "value") for f in EDITABLE_FIELDS],
    Output("intake-confirm", "value"), Output("intake-result", "children"), Output("intake-safety", "children"),
    Input("run-extraction", "n_clicks"), State("intake-text", "value"),
    prevent_initial_call=True,
)
def run_extraction(_, text):
    hidden = {"display": "none"}
    blank = [""] * len(EDITABLE_FIELDS)
    if not (text or "").strip():
        return (None, html.P("Paste a report first.", className="error-text"), hidden, "", "", *blank, [], "", "")
    try:
        result = extract_shelter_report(text, utc_iso(utc_now()))
    except AgentError as exc:
        return (None, html.P(f"Extraction failed: {exc}", className="error-text"), hidden, "", "", *blank, [], "",
                "")
    row = result["shelter_row"]
    values = [local_time_input(row["reported_at"]) if f == "reported_at" else row.get(f, "") for f in EDITABLE_FIELDS]
    u = result["usage"]
    message = html.P(f"Extracted (not saved). {len(result['issues'])} warning(s). Model {result['model']}, "
                     f"{u['input_tokens']} input / {u['output_tokens']} output tokens (extraction + safety screen).",
                     className="notice")
    return (result, message, {}, result["source_text"], _issue_list(result["issues"]), *values, [], "",
            render_safety_alert(result.get("safety_screen")))


def render_safety_alert(screen):
    """Prominent warning when the report contains text aimed at the AI or software."""
    if not screen or not screen["flagged"]:
        return ""
    return html.Div(className="safety-alert", children=[
        html.Strong("Warning: this report contains text that looks like instructions to the AI or software."),
        html.P("They were not followed. The original report is kept below. Check the values with the shelter "
               "before approving."),
        html.Ul([html.Li([f"{', '.join(c.replace('_', ' ') for c in f['categories'])} ({f['source']}): ",
                          html.Q(f["quote"])]) for f in screen["findings"]]),
    ] + ([html.P(f"Model screen unavailable: {screen['model_screen_error']}", className="muted")]
         if screen.get("model_screen_error") else []))


@app.callback(
    Output("intake-result", "children", allow_duplicate=True),
    Output("intake-extraction", "data", allow_duplicate=True),
    Output("intake-form", "style", allow_duplicate=True),
    Input("approve-report", "n_clicks"),
    State("intake-extraction", "data"), State("intake-staff", "value"), State("intake-confirm", "value"),
    *[State(f"intake-{f}", "value") for f in EDITABLE_FIELDS],
    prevent_initial_call=True,
)
def approve_report(_, extraction, staff, confirm, *values):
    if not extraction:
        raise PreventUpdate
    if "yes" not in (confirm or []):
        return html.P("Tick the confirmation box to approve.", className="error-text"), no_update, no_update
    corrected = dict(zip(EDITABLE_FIELDS, values))
    result = approve_extracted_report(config.SHELTER_LOG_PATH, extraction, corrected, staff)
    if result["status"] != "saved":
        return (html.Div(className="error-text", children=[
            html.P("Not saved: please correct these fields."),
            html.Ul([html.Li(e) for e in result["errors"]])]), no_update, no_update)
    rec = result["row"]
    return (html.Div(className="success", children=[
        html.P(["Saved as validated. Record ID: ", html.Strong(rec["record_id"], id="saved-record-id")]),
        html.P(f"{rec['shelter_id']} {rec['shelter_name']}: {rec['evacuee_count']} evacuees, report time "
               f"{display_time(rec['reported_at'])}. Approved by {rec['validated_by']} at "
               f"{display_time(rec['validated_at'])}. {rec['notes']}."),
        *[html.P(f"Note: {w}", className="muted") for w in result["warnings"]],
        html.P("Load the current plan in Review & finalize to see the effect on allocation.", className="muted"),
    ]), None, {"display": "none"})


# ---- Warehouse photos (staff only, read-only) ------------------------------------

STATUS_LABELS = {
    "possible_discrepancy": ("Possible discrepancy", "badge-alert"),
    "needs_review": ("Needs review", "badge-warn"),
    "inconclusive_partial_view": ("Inconclusive (partial view)", "badge-muted"),
    "not_comparable": ("Not comparable", "badge-muted"),
    "consistent_with_record": ("Consistent with record", "badge-ok"),
}


def _count_text(item):
    if item["count_basis"] == "counted":
        return f"{item['visible_count']} counted"
    if item["count_basis"] == "estimated":
        return f"about {item['estimate_low']}–{item['estimate_high']} (estimate)"
    return "not countable"


def render_photo_analysis(record, image_bytes):
    """Image beside the analysis: facts vs estimates, items, comparison with validated records."""
    a, c, u = record["analysis"], record["comparison"], record["usage"]
    src = f"data:{record['image']['media_type']};base64,{base64.b64encode(image_bytes).decode()}"
    items = _table(["Label (as read)", "Readable", "Unit", "Count", "Per container (label)", "Uncertainty"],
                   [[(i["label_text"] or "—").replace("\n", " "), i["label_readability"], i["unit_seen"] or "—",
                     _count_text(i), i["units_per_container_on_label"] or "—", i["uncertainty"] or ""]
                    for i in a["items"]])
    findings = _table(["Status", "Item", "Finding"],
                      [[html.Span(STATUS_LABELS[f["status"]][0], className=f"badge {STATUS_LABELS[f['status']][1]}"),
                        (f.get("item_name") or f["label_text"] or "unreadable item").replace("\n", " "),
                        f["message"]] for f in c["findings"]])
    return html.Div(className="photo-grid", children=[
        html.Div(className="photo-image", children=[
            html.Img(src=src, alt=f"Analyzed photo {record['image']['original_name']}", id="photo-img"),
            html.P(f"{record['image']['original_name']} · warehouse {record['warehouse_id']} · analysis "
                   f"{record['analysis_id']} · analyzed {display_time(record['analyzed_at'])}", className="muted"),
            html.P(f"Model {record['model']} · {u['input_tokens']} input / {u['output_tokens']} output tokens · "
                   f"image SHA-256 {record['image']['sha256'][:12]}…", className="muted"),
        ]),
        html.Div(className="photo-analysis", children=[
            html.H3("What is visible (view coverage)"), html.P(a["view_coverage"]),
            html.H3("Observed facts"), html.Ul([html.Li(x) for x in a["observed_facts"]]),
            html.H3("Uncertain estimates"),
            html.Ul([html.Li(x) for x in a["uncertain_estimates"] + a["image_quality_issues"]])
            if a["uncertain_estimates"] or a["image_quality_issues"] else html.P("None reported.", className="muted"),
            html.H3("Identified items"), items,
            html.H3(f"Compared with validated inventory for {c['warehouse_id']}"), findings,
            html.P("Recorded items not identified in this photo (no conclusion: the photo may show only part of "
                   "the warehouse): " + (", ".join(f"{n['item_name']} ({n['recorded_quantity']:g} "
                                                   f"{n['recorded_unit']})" for n in c["not_visible"]) or "none"),
                   className="muted"),
            html.P(c["note"], className="notice"),
        ]),
    ])


def render_followups(folder):
    path = os.path.join(folder, "followups.jsonl")
    if not os.path.exists(path):
        return html.P("No questions yet.", className="muted")
    entries = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    return html.Div([html.Div(className="bubble assistant followup", children=[
        html.Div(f"Q: {e['question']}", className="role"),
        dcc.Markdown(markdown_safe(e["answer"]), className="text markdown"),
        html.Div(f"{display_time(e['asked_at'])} · {e['usage']['input_tokens']} input / "
                 f"{e['usage']['output_tokens']} output tokens", className="muted small"),
    ]) for e in entries])


@app.callback(
    Output("photo-warehouse", "options"),
    Input("tab-photos", "n_clicks"),
    prevent_initial_call=True,
)
def warehouse_options(_):
    log, _ = load_inventory_log(config.INVENTORY_LOG_PATH)
    latest = latest_validated(log, ["warehouse_id", "item_id"], "counted_at")
    ids = [] if latest is None or latest.empty else sorted(set(latest["warehouse_id"]))
    return [{"label": w, "value": w} for w in ids]


@app.callback(
    Output("photo-upload-name", "children"),
    Input("photo-upload", "filename"),
    prevent_initial_call=True,
)
def show_upload_name(filename):
    return f"Selected: {filename}" if filename else ""


@app.callback(
    Output("photo-analysis-id", "data"), Output("photo-message", "children"), Output("photo-result", "children"),
    Output("photo-followup-box", "style"), Output("photo-followups", "children"),
    Input("analyze-photo", "n_clicks"),
    State("photo-upload", "contents"), State("photo-upload", "filename"), State("photo-warehouse", "value"),
    prevent_initial_call=True,
)
def analyze_photo(_, contents, filename, warehouse):
    hidden = {"display": "none"}
    if not contents or not filename:
        return no_update, html.P("Choose a photo first.", className="error-text"), no_update, no_update, no_update
    if not warehouse:
        return no_update, html.P("Choose the warehouse the photo was taken in.", className="error-text"), \
            no_update, no_update, no_update
    workdir = tempfile.mkdtemp(prefix="upload-")
    try:
        data = base64.b64decode(contents.split(",", 1)[1])
        path = os.path.join(workdir, os.path.basename(filename))
        with open(path, "wb") as f:
            f.write(data)
        record = analyze_warehouse_photo(path, warehouse)
    except AgentError as exc:
        return None, html.P(f"Analysis failed: {exc}", className="error-text"), "", hidden, ""
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    stored, image_bytes = load_photo_analysis(record["analysis_id"])
    summary = ", ".join(f"{n} {STATUS_LABELS[k][0].lower()}" for k, n in stored["comparison"]["summary"].items())
    message = html.P(f"Analysis {stored['analysis_id']} saved with its image (read-only; inventory unchanged). "
                     f"Findings: {summary or 'none'}.", className="notice")
    return (stored["analysis_id"], message, render_photo_analysis(stored, image_bytes), {},
            render_followups(photo_folder(stored["analysis_id"])))


@app.callback(
    Output("photo-followups", "children", allow_duplicate=True), Output("photo-question", "value"),
    Input("ask-photo", "n_clicks"),
    State("photo-question", "value"), State("photo-analysis-id", "data"),
    prevent_initial_call=True,
)
def ask_photo(_, question, analysis_id):
    if not analysis_id or not (question or "").strip():
        raise PreventUpdate
    try:
        ask_about_photo(analysis_id, question.strip())
    except AgentError as exc:
        return html.Div([render_followups(photo_folder(analysis_id)),
                         html.P(f"Question failed: {exc}", className="error-text")]), no_update
    return render_followups(photo_folder(analysis_id)), ""


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    ensure_working_data()  # first setup copies the sample data; existing working data is kept
    app.run(debug=False, use_reloader=False, port=int(os.getenv("PORT", "8050")))
