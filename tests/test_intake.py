"""Staff approval of AI-extracted reports: append-only validated records, and the effect on planning."""
import threading

from src.finalization import finalize_and_store, review_plan
from src.intake import approve_extracted_report, local_time_input, parse_local_time
from src.records import latest_validated
from src.store import load_shelter_log
from tests.test_allocation_tool import CM, INV, V

FULL_HEADER = ("record_id,source,received_at,status,validated_by,validated_at,supersedes,source_text,shelter_id,"
               "shelter_name,reported_at,evacuee_count,general_on_hand_meals,special_needs,special_on_hand_meals,"
               "reporter,notes\n")
VF = "csv,2026-01-01T07:00+09:00,validated,T,2026-01-01T07:10+09:00,,"
SHELTERS = (f"a,{VF},S1,One,2026-01-01T06:00+09:00,10,0,,,,\n"
            f"b,{VF},S2,Two,2026-01-01T06:00+09:00,30,0,,,,\n")

CONFIG = {"meals_per_person_per_day": 3, "planning_window_hours": 24}
RICE_60 = f"x,{V},W1,I1,Rice,meal,general,pack,60,1,2026-01-01T05:00+09:00\n"
TEXT = "Two shelter update, 1 Jan 09:00.\nAbout 50 people now?\nFood: some rice."
EXTRACTION = {"source_text": TEXT, "received_at": "2026-01-01T00:05:00+00:00",
              "shelter_row": {"shelter_id": "", "shelter_name": "Two", "reported_at": "", "evacuee_count": "",
                              "general_on_hand_meals": "", "special_needs": "", "special_on_hand_meals": ""}}
CORRECTED = {"shelter_id": "S2", "shelter_name": "Two", "reported_at": "2026-01-01 09:00", "evacuee_count": "50",
             "general_on_hand_meals": "0", "special_needs": "", "special_on_hand_meals": ""}
AT = "2026-01-01T03:00:00+00:00"                     # 12:00 JST


def write_logs(tmp_path, shelters=SHELTERS):
    for name, text in (("s", FULL_HEADER + shelters), ("i", INV + RICE_60), ("c", CM)):
        (tmp_path / f"{name}.csv").write_text(text)
    return [str(tmp_path / f"{n}.csv") for n in ("s", "i", "c")]


def setup(tmp_path):
    return write_logs(tmp_path)


def test_times_are_entered_in_display_zone_and_stored_in_utc():
    assert parse_local_time("2026-01-01 09:00") == "2026-01-01T00:00:00+00:00"
    assert parse_local_time("2026-01-01T09:00+00:00") == "2026-01-01T09:00:00+00:00"
    assert local_time_input("2026-01-01T00:00:00+00:00") == "2026-01-01 09:00"


def test_approval_appends_a_validated_record_without_touching_earlier_ones(tmp_path):
    paths = setup(tmp_path)
    before = open(paths[0], "rb").read()
    result = approve_extracted_report(paths[0], EXTRACTION, CORRECTED, "Tanaka", AT)
    assert result["status"] == "saved"
    after = open(paths[0], "rb").read()
    assert after.startswith(before)                                    # earlier rows untouched
    log, issues = load_shelter_log(paths[0])
    assert not [i for i in issues if i["severity"] == "error"]
    # mixed +09:00 (existing) and UTC (new) timestamps must all parse
    assert log["received_at"].notna().all() and log["validated_at"].notna().all()
    rec = log[log["record_id"] == result["record_id"]].iloc[0]
    assert (rec["status"], rec["source"], rec["validated_by"]) == ("validated", "ai_extraction", "Tanaka")
    assert rec["source_text"] == TEXT                                  # original text, newlines included
    assert str(rec["validated_at"]) == "2026-01-01 03:00:00+00:00"
    assert rec["evacuee_count"] == 50 and str(rec["reported_at"]) == "2026-01-01 00:00:00+00:00"
    assert "staff corrected:" in rec["notes"] and "evacuee_count" in rec["notes"]
    # it is now the latest validated report for S2
    latest = latest_validated(log, ["shelter_id"], "reported_at")
    assert latest.set_index("shelter_id").loc["S2", "record_id"] == result["record_id"]


def test_invalid_or_unapproved_input_writes_nothing(tmp_path):
    paths = setup(tmp_path)
    before = open(paths[0], "rb").read()
    cases = [
        ({**CORRECTED, "evacuee_count": ""}, "Tanaka"),                # still missing
        ({**CORRECTED, "evacuee_count": "about 50"}, "Tanaka"),        # not a number
        ({**CORRECTED, "reported_at": ""}, "Tanaka"),                  # no time
        ({**CORRECTED, "reported_at": "2026-01-02 09:00"}, "Tanaka"),  # later than approval
        ({**CORRECTED, "special_needs": "halal:60"}, "Tanaka"),        # 60 > 50 evacuees
        (CORRECTED, "  "),                                             # no approver
    ]
    for corrected, staff in cases:
        result = approve_extracted_report(paths[0], EXTRACTION, corrected, staff, AT)
        assert result["status"] == "invalid" and result["errors"], corrected
    assert open(paths[0], "rb").read() == before


def test_approved_report_changes_the_plan_and_old_review_needs_confirmation(tmp_path, isolated_finalization_db):
    db = isolated_finalization_db
    paths = setup(tmp_path)
    reviewed = review_plan(db, *paths, CONFIG)
    assert [l["unmet_meals"] for l in reviewed["general"]["lines"]] == [30, 90]
    approve_extracted_report(paths[0], EXTRACTION, CORRECTED, "Tanaka", AT)    # S2: 30 -> 50 people
    updated = review_plan(db, *paths, CONFIG)
    assert [l["unmet_meals"] for l in updated["general"]["lines"]] == [30, 150]
    result = finalize_and_store(db, *paths, CONFIG, reviewed["fingerprint"], "Tanaka", AT)
    assert result["status"] == "needs_confirmation"
    assert result["plan"]["fingerprint"] == updated["fingerprint"]


def test_approval_resolves_an_older_pending_report_warning(tmp_path, isolated_finalization_db):
    paths = write_logs(tmp_path, SHELTERS + "p1,csv,2026-01-01T08:05+09:00,pending,,,,,S2,Two,"
                                            "2026-01-01T08:00+09:00,40,0,,,,\n")
    assert review_plan(isolated_finalization_db, *paths, CONFIG)["pending_data_warnings"]
    approve_extracted_report(paths[0], EXTRACTION, CORRECTED, "Tanaka", AT)    # validated 09:00 > pending 08:00
    assert review_plan(isolated_finalization_db, *paths, CONFIG)["pending_data_warnings"] == []


def test_concurrent_approvals_all_land_intact(tmp_path):
    path = str(tmp_path / "new_log.csv")                                       # file created on first write
    barrier, results = threading.Barrier(8), []

    def approve(n):
        barrier.wait()
        results.append(approve_extracted_report(path, EXTRACTION, {**CORRECTED, "evacuee_count": str(40 + n)},
                                                f"staff-{n}", AT))

    threads = [threading.Thread(target=approve, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(r["status"] == "saved" for r in results)
    log, issues = load_shelter_log(path)
    assert len(log) == 8 and not [i for i in issues if i["severity"] == "error"]
    assert sorted(log["evacuee_count"]) == list(range(40, 48))


def test_log_without_source_text_column_is_refused_not_truncated(tmp_path):
    path = tmp_path / "old_format.csv"
    path.write_text("record_id,source,received_at,status,validated_by,validated_at,shelter_id,shelter_name,"
                    f"reported_at,evacuee_count,general_on_hand_meals\na,{VF[:-2]},S1,One,2026-01-01T06:00+09:00,10,0\n")
    before = path.read_bytes()
    result = approve_extracted_report(str(path), EXTRACTION, CORRECTED, "Tanaka", AT)
    assert result["status"] == "invalid" and "cannot store" in result["errors"][0]
    assert path.read_bytes() == before
