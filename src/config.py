"""Settings loaded from the environment. No data values are hardcoded here.

Planning defaults can be overridden via environment variables or in the UI.
"""
import os

from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def env_files(project_root=PROJECT_ROOT):
    """The .env files read at startup, in priority order: the project folder, then its parent.

    Variables already set in the environment always win; a value in the project .env wins over the
    same name in the parent .env. No other folders are searched."""
    return [os.path.join(project_root, ".env"), os.path.join(os.path.dirname(project_root), ".env")]


def load_env(project_root=PROJECT_ROOT):
    """Load the .env files that exist (never overriding values that are already set). Returns their paths."""
    loaded = []
    for path in env_files(project_root):
        if os.path.isfile(path):
            load_dotenv(path, override=False)
            loaded.append(path)
    return loaded


ENV_FILES_LOADED = load_env()

PORTKEY_API_KEY = os.getenv("PORTKEY_API_KEY")  # never log or print
MODEL = os.getenv("MODEL", "gpt-6-luna")

# Configurable planning defaults (not fixed assumptions)
MEALS_PER_PERSON_PER_DAY = float(os.getenv("MEALS_PER_PERSON_PER_DAY", "3"))
PLANNING_WINDOW_HOURS = float(os.getenv("PLANNING_WINDOW_HOURS", "24"))

# Agent limits
AGENT_REQUEST_LIMIT = int(os.getenv("AGENT_REQUEST_LIMIT", "3"))          # model requests per user message
AGENT_TIMEOUT_SECONDS = float(os.getenv("AGENT_TIMEOUT_SECONDS", "60"))
AGENT_MAX_HISTORY_MESSAGES = int(os.getenv("AGENT_MAX_HISTORY_MESSAGES", "20"))

# Data locations (relative paths are resolved from the project root).
# The app works on copies in LIVE_DATA_DIR. SEED_DATA_DIR (the sample data) is read only
# to create missing working files on first setup and is never written to.
LIVE_DATA_DIR = os.path.join(PROJECT_ROOT, os.getenv("LIVE_DATA_DIR", "data/live"))
SEED_DATA_DIR = os.path.join(PROJECT_ROOT, os.getenv("SEED_DATA_DIR", "data/sample"))


def _data_path(env_name, file_name):
    """An explicit per-file override wins; otherwise the file lives in LIVE_DATA_DIR."""
    override = os.getenv(env_name)
    return os.path.join(PROJECT_ROOT, override) if override else os.path.join(LIVE_DATA_DIR, file_name)


SHELTER_LOG_PATH = _data_path("SHELTER_LOG_PATH", "shelter_log.csv")
INVENTORY_LOG_PATH = _data_path("INVENTORY_LOG_PATH", "inventory_log.csv")
COMMITMENTS_LOG_PATH = _data_path("COMMITMENTS_LOG_PATH", "commitments_log.csv")
FINALIZATION_DB_PATH = _data_path("FINALIZATION_DB_PATH", "finalization.db")

# Timezones: stored timestamps are UTC; this zone is only for display
DISPLAY_TIMEZONE = os.getenv("DISPLAY_TIMEZONE", "Asia/Tokyo")

# Timezone applied to report times that state a date and time but no timezone.
# Applying it is always flagged for staff review (it is a configured rule, not read from the report).
REPORT_TIMEZONE = os.getenv("REPORT_TIMEZONE", "Asia/Tokyo")

# Stored warehouse photo analyses (image copy + analysis JSON per folder)
PHOTO_DIR = os.path.join(LIVE_DATA_DIR, "photos")

# Append-only per-call usage log (measured token usage; no costs, no content)
USAGE_LOG_PATH = _data_path("USAGE_LOG_PATH", "usage_log.jsonl")
# Map positions for the dashboard. The sample records have no coordinates, so this is a FICTIONAL
# training layout (schematic x/y, not latitude/longitude); see the file's own label.
TRAINING_LOCATIONS_PATH = os.path.join(PROJECT_ROOT, os.getenv(
    "TRAINING_LOCATIONS_PATH", "data/training_locations/fictional_training_locations.json"))
