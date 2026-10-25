"""Working data: the app reads and writes copies in LIVE_DATA_DIR, never the sample data.

ensure_working_data() creates each missing working log by copying it from SEED_DATA_DIR
(first setup). An existing working file is never overwritten, so restarts keep all
approved reports, counts, and dispatch records. assert_writable() refuses any write
into SEED_DATA_DIR.
"""
import logging
import os
import shutil
import tempfile

from src import config

logger = logging.getLogger(__name__)

# working file setting -> file name in SEED_DATA_DIR
SEEDED_LOGS = {
    "SHELTER_LOG_PATH": "shelter_log.csv",
    "INVENTORY_LOG_PATH": "inventory_log.csv",
    "COMMITMENTS_LOG_PATH": "commitments_log.csv",
}


class ProtectedPathError(RuntimeError):
    """Raised when something tries to write into the seed (sample) data."""


def _inside(path, folder):
    path, folder = os.path.realpath(path), os.path.realpath(folder)
    return os.path.commonpath([path, folder]) == folder


def assert_writable(path):
    if config.SEED_DATA_DIR and _inside(path, config.SEED_DATA_DIR):
        raise ProtectedPathError(f"refusing to write to the sample data: {path}")


def _copy_if_missing(src, dst):
    """Copy src to dst only if dst doesn't exist. Atomic and never overwrites: the copy is
    written to a temporary file and hard-linked into place, which fails if dst exists."""
    if os.path.exists(dst):
        return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(dst), prefix=".seed-")
    os.close(fd)
    try:
        shutil.copyfile(src, tmp)
        os.link(tmp, dst)                      # FileExistsError if another process won the race
        return True
    except FileExistsError:
        return False
    finally:
        os.unlink(tmp)


def ensure_working_data():
    """Seed missing working logs from SEED_DATA_DIR. Returns {path: "seeded" | "kept" | "no seed"}."""
    report = {}
    for setting, seed_name in SEEDED_LOGS.items():
        dst = getattr(config, setting)
        assert_writable(dst)
        src = os.path.join(config.SEED_DATA_DIR, seed_name) if config.SEED_DATA_DIR else ""
        if os.path.exists(dst):
            report[dst] = "kept"
        elif src and os.path.exists(src):
            report[dst] = "seeded" if _copy_if_missing(src, dst) else "kept"
        else:
            report[dst] = "no seed"
        logger.info("working data %s: %s", report[dst], dst)
    return report
