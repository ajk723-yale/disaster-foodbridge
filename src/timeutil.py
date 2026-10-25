"""UTC for stored timestamps; a configurable local zone (config.DISPLAY_TIMEZONE) for display."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from src import config


def to_utc(value):
    """Timezone-aware timestamp in UTC. Naive times are rejected as ambiguous."""
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        raise ValueError(f"timestamp {value!r} has no timezone; refusing to guess")
    return ts.tz_convert("UTC")


def utc_now():
    return pd.Timestamp(datetime.now(timezone.utc))


def utc_iso(value):
    return to_utc(value).isoformat()


def display_time(value, tz_name=None, fmt="%Y-%m-%d %H:%M %Z"):
    """Format a stored timestamp in the display timezone (default config.DISPLAY_TIMEZONE)."""
    if value is None or value == "":
        return ""
    return to_utc(value).tz_convert(ZoneInfo(tz_name or config.DISPLAY_TIMEZONE)).strftime(fmt)
