"""Shared, append-only usage log: one JSON line per actual model API call.

Captured with HTTP hooks on the per-run client created in src/llm.py, so every HTTP response
from the model API is logged exactly once (retries and failed calls included), for all
workflows: chat, extraction, safety screen, photo analysis, photo follow-up.

Recorded: workflow, model (requested and reported), timestamps, latency, HTTP status, the
raw `usage` object exactly as the API returned it, normalized token fields, and an allow-list
of provider/gateway headers (e.g. x-portkey-cache-status).
Never recorded: prompts, outputs, report text, images, request bodies, API keys.
Missing fields are stored as null (unknown), never as 0. No USD costs are written here.
"""
import fcntl
import json
import logging
import os
import time
import uuid

from src import config
from src.timeutil import utc_iso, utc_now
from src.workspace import assert_writable

logger = logging.getLogger(__name__)

WORKFLOWS = {
    "foodbridge": "chat",
    "report_extractor": "extraction",
    "instruction_screen": "safety_screen",
    "photo_analyzer": "photo_analysis",
    "photo_followup": "photo_followup",
}
# Response headers worth keeping (no keys, no identifiers of the key). Values are reported, not verified.
HEADER_ALLOWLIST = (
    "x-portkey-cache-status", "x-portkey-provider", "x-portkey-retry-attempt-count", "x-portkey-trace-id",
    "x-portkey-last-used-option-index", "x-ms-served-model", "x-ms-region", "x-ms-is-spilled-over",
    "x-ratelimit-remaining-requests", "x-ratelimit-remaining-tokens", "x-ratelimit-limit-requests",
    "x-ratelimit-limit-tokens", "cf-cache-status",
)
KNOWN_USAGE_PATHS = {
    "input_tokens": ("input_tokens",),
    "output_tokens": ("output_tokens",),
    "total_tokens": ("total_tokens",),
    "cached_read_tokens": ("input_tokens_details", "cached_tokens"),
    "cache_write_tokens": ("input_tokens_details", "cache_write_tokens"),
    "cache_write_ttl_30m_tokens": ("input_tokens_details", "cache_write_tokens_details", "ttl_30m_tokens"),
    "cache_write_ttl_12h_tokens": ("input_tokens_details", "cache_write_tokens_details", "ttl_12h_tokens"),
    "reasoning_tokens": ("output_tokens_details", "reasoning_tokens"),
}


def _get(d, path):
    for key in path:
        if not isinstance(d, dict) or key not in d:
            return None                      # unknown, not zero
        d = d[key]
    return d


def _numeric_only(value):
    """Keep the usage object's structure and numbers only (defensive: no strings from the API)."""
    if isinstance(value, dict):
        return {k: _numeric_only(v) for k, v in value.items() if isinstance(v, (dict, int, float, bool))
                or v is None}
    return value


def _flatten(d, prefix=""):
    out = {}
    for k, v in (d or {}).items():
        path = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, path + "."))
        else:
            out[path] = v
    return out


def normalize_usage(raw):
    """Normalized token fields from a raw API usage object; absent fields are None (unknown)."""
    fields = {name: (_get(raw, path) if raw is not None else None) for name, path in KNOWN_USAGE_PATHS.items()}
    known = {".".join(p) for p in KNOWN_USAGE_PATHS.values()}
    other = {k: v for k, v in _flatten(raw).items() if k not in known} if raw else {}
    return {**fields, "other_usage_fields": other}


class CallCapture:
    """httpx event hooks that record one item per model API response (no content kept)."""

    def __init__(self):
        self.calls = []
        self._started = {}

    async def on_request(self, request):
        self._started[id(request)] = (time.monotonic(), utc_iso(utc_now()))

    async def on_response(self, response):
        started = self._started.pop(id(response.request), (None, None))
        item = {"request_started_at": started[1], "response_at": utc_iso(utc_now()),
                "latency_ms": round((time.monotonic() - started[0]) * 1000) if started[0] else None,
                "endpoint": response.request.url.path, "http_status": response.status_code,
                "headers": {h: response.headers[h] for h in HEADER_ALLOWLIST if h in response.headers},
                "response_id": None, "model_reported": None, "usage_raw": None, "error": None}
        try:
            await response.aread()
            body = response.json()
        except Exception:
            body = None
        if isinstance(body, dict):
            item["response_id"] = body.get("id") if isinstance(body.get("id"), str) else None
            item["model_reported"] = body.get("model") if isinstance(body.get("model"), str) else None
            if isinstance(body.get("usage"), dict):
                item["usage_raw"] = _numeric_only(body["usage"])
            err = body.get("error")
            if isinstance(err, dict):                       # type/code only; messages may echo input
                item["error"] = {"type": err.get("type"), "code": err.get("code")}
        self.calls.append(item)

    def hooks(self):
        return {"request": [self.on_request], "response": [self.on_response]}


def build_entries(capture, agent_name, run_outcome, result=None):
    """One log entry per captured API call. PydanticAI's per-request usage is attached for comparison
    when the response id matches (it reports missing fields as 0, so it is not the source of truth)."""
    by_id = {}
    if result is not None:
        for message in result.new_messages():
            rid = getattr(message, "provider_response_id", None)
            if rid and getattr(message, "usage", None) is not None:
                u = message.usage
                by_id[rid] = {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
                              "cache_read_tokens": u.cache_read_tokens, "cache_write_tokens": u.cache_write_tokens,
                              "details": dict(u.details or {})}
    run_id = uuid.uuid4().hex[:12]
    entries = []
    for i, call in enumerate(capture.calls):
        entries.append({
            "call_id": uuid.uuid4().hex[:12], "run_id": run_id, "call_index_in_run": i,
            "logged_at": utc_iso(utc_now()), "workflow": WORKFLOWS.get(agent_name, agent_name or "unknown"),
            "agent_name": agent_name, "model_requested": config.MODEL, **call,
            "ok": 200 <= call["http_status"] < 300 and call["usage_raw"] is not None,
            "usage": normalize_usage(call["usage_raw"]),
            "pydantic_ai_request_usage": by_id.get(call["response_id"]),
            "run_outcome": run_outcome,
            "note": "Measured usage as reported by the API. Gateway headers are reported values, not verified "
                    "billing. No cost is computed here.",
        })
    return entries


def append_entries(entries, path=None):
    """Append-only JSONL write under an exclusive lock."""
    path = path or config.USAGE_LOG_PATH
    assert_writable(path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def record_run(capture, agent_name, run_outcome, result=None):
    """Write the run's calls; never raises (logging must not change agent behavior)."""
    try:
        entries = build_entries(capture, agent_name, run_outcome, result)
        if entries:
            append_entries(entries)
        return entries
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("usage log write failed: %s", exc)
        return []
