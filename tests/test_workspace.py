"""Working copies in a live folder; the sample (seed) data is never modified."""
import hashlib
import os
import threading

import pytest

from src import config
from src.agent_tools import planning_config
from src.finalization import finalize_and_store, load_finalized_commitments, review_plan
from src.intake import approve_extracted_report
from src.store import append_record
from src.workspace import ProtectedPathError, ensure_working_data

SAMPLE = os.path.join(config.PROJECT_ROOT, "data", "sample")
LOGS = ("shelter_log.csv", "inventory_log.csv", "commitments_log.csv")
EXTRACTION = {"source_text": "Higashi gym here. About 250 people now?", "received_at": "2026-10-24T07:05:00+00:00",
              "shelter_row": {"shelter_id": "", "shelter_name": "Higashi gym", "reported_at": "", "evacuee_count": "",
                              "general_on_hand_meals": "", "special_needs": "halal:?", "special_on_hand_meals": ""}}
CORRECTED = {"shelter_id": "SH-03", "shelter_name": "Higashi Junior High Gym", "reported_at": "2026-10-24 16:00",
             "evacuee_count": "250", "general_on_hand_meals": "0", "special_needs": "halal:6",
             "special_on_hand_meals": ""}
NOW = "2026-10-24T09:00:00+00:00"


def sample_hashes():
    return {name: hashlib.sha256(open(os.path.join(SAMPLE, name), "rb").read()).hexdigest()
            for name in sorted(os.listdir(SAMPLE)) if os.path.isfile(os.path.join(SAMPLE, name))}


@pytest.fixture
def live(tmp_path, monkeypatch, isolated_finalization_db):
    """A fresh live folder seeded from the real sample folder (which is only read)."""
    live_dir = tmp_path / "live"
    monkeypatch.setattr(config, "SEED_DATA_DIR", SAMPLE)
    monkeypatch.setattr(config, "LIVE_DATA_DIR", str(live_dir))
    for setting, name in (("SHELTER_LOG_PATH", "shelter_log.csv"), ("INVENTORY_LOG_PATH", "inventory_log.csv"),
                          ("COMMITMENTS_LOG_PATH", "commitments_log.csv"),
                          ("FINALIZATION_DB_PATH", "finalization.db")):
        monkeypatch.setattr(config, setting, str(live_dir / name))
    before = sample_hashes()
    yield live_dir
    assert sample_hashes() == before, "sample files changed"


def paths():
    return (config.FINALIZATION_DB_PATH, config.SHELTER_LOG_PATH, config.INVENTORY_LOG_PATH,
            config.COMMITMENTS_LOG_PATH)


def test_default_paths_live_in_the_working_folder(monkeypatch):
    monkeypatch.delenv("SHELTER_LOG_PATH", raising=False)
    assert config._data_path("SHELTER_LOG_PATH", "shelter_log.csv") == \
        os.path.join(config.LIVE_DATA_DIR, "shelter_log.csv")
    assert os.path.realpath(config.LIVE_DATA_DIR) != os.path.realpath(config.SEED_DATA_DIR)


def test_first_setup_copies_the_sample_logs(live):
    report = ensure_working_data()
    assert sorted(report.values()) == ["seeded"] * 3
    for name in LOGS:
        assert (live / name).read_bytes() == open(os.path.join(SAMPLE, name), "rb").read()


def test_restart_keeps_existing_working_data(live):
    ensure_working_data()
    approve_extracted_report(config.SHELTER_LOG_PATH, EXTRACTION, CORRECTED, "Suzuki", NOW)
    changed = (live / "shelter_log.csv").read_bytes()
    report = ensure_working_data()                                      # "restart"
    assert sorted(report.values()) == ["kept"] * 3
    assert (live / "shelter_log.csv").read_bytes() == changed


def test_only_missing_files_are_seeded(live):
    ensure_working_data()
    (live / "inventory_log.csv").unlink()
    report = ensure_working_data()
    assert report[config.INVENTORY_LOG_PATH] == "seeded"
    assert report[config.SHELTER_LOG_PATH] == report[config.COMMITMENTS_LOG_PATH] == "kept"


def test_concurrent_first_setup_seeds_each_file_once(live):
    barrier, reports = threading.Barrier(4), []

    def start():
        barrier.wait()
        reports.append(ensure_working_data())

    threads = [threading.Thread(target=start) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    for path in (config.SHELTER_LOG_PATH, config.INVENTORY_LOG_PATH, config.COMMITMENTS_LOG_PATH):
        assert [r[path] for r in reports].count("seeded") == 1
    assert not [f for f in os.listdir(live) if f.startswith(".seed-")]   # no temporary files left


def test_writes_into_the_sample_folder_are_refused(live, tmp_path):
    sample_log = os.path.join(SAMPLE, "shelter_log.csv")
    with pytest.raises(ProtectedPathError):
        append_record(sample_log, {"record_id": "x"}, ["record_id"])
    result = approve_extracted_report(sample_log, EXTRACTION, CORRECTED, "Suzuki", NOW)
    assert result["status"] == "invalid" and "refusing to write to the sample data" in result["errors"][0]
    with pytest.raises(ProtectedPathError):
        finalize_and_store(os.path.join(SAMPLE, "finalization.db"), *paths()[1:], planning_config(), "x",
                           "Tanaka", NOW)
    assert not os.path.exists(os.path.join(SAMPLE, "finalization.db"))


def test_approval_recalculation_finalization_and_restart_use_the_working_copies(live):
    ensure_working_data()
    cfg = planning_config()
    reviewed = review_plan(*paths(), cfg)
    sh03 = {l["shelter_id"]: l for l in reviewed["general"]["lines"]}["SH-03"]
    assert sh03["unmet_meals"] == 590

    saved = approve_extracted_report(config.SHELTER_LOG_PATH, EXTRACTION, CORRECTED, "Suzuki", NOW)
    assert saved["status"] == "saved"
    stale = finalize_and_store(*paths(), cfg, reviewed["fingerprint"], "Tanaka", NOW)
    assert stale["status"] == "needs_confirmation"
    updated = stale["plan"]
    assert {l["shelter_id"]: l for l in updated["general"]["lines"]}["SH-03"]["unmet_meals"] == 692

    acks = [{"warning_id": w["warning_id"], "reason": "Proceeding on last validated data"}
            for w in updated["pending_data_warnings"]]
    done = finalize_and_store(*paths(), cfg, updated["fingerprint"], "Tanaka", NOW, acknowledgements=acks)
    assert done["status"] == "finalized"
    assert os.path.exists(live / "finalization.db")

    # restart: nothing re-seeded, approvals and the finalized plan are still there
    assert sorted(ensure_working_data().values()) == ["kept"] * 3
    assert saved["record_id"] in (live / "shelter_log.csv").read_text()
    assert len(load_finalized_commitments(config.FINALIZATION_DB_PATH)) == len(done["commitments"])
    after_restart = review_plan(*paths(), cfg)
    assert after_restart["general"]["available_meals"] == 0              # finalized food stays reserved
