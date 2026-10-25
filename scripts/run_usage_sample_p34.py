"""P34: a small real usage sample through the normal code path, logged to data/live/usage_log.jsonl.

New inputs (to reach the provider) plus deliberate repeats (to observe Portkey HITs) and several
follow-ups on one photo (to observe prompt-cache reuse). Read-only for app data: chat only reads the
working data, extraction saves nothing, photos are stored in a temporary folder.

    .venv/bin/python scripts/run_usage_sample_p34.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from src import config  # noqa: E402
from src.agent import run_agent  # noqa: E402
from src.extraction import extract_shelter_report  # noqa: E402
from src.vision import analyze_warehouse_photo, ask_about_photo  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHAT = ["How many evacuees are at Higashi Junior High Gym according to the latest validated report?",
        "Which shelters have special dietary needs, and which of those counts are unknown?",
        "What is the total shortage of general meals in the current draft allocation plan?",
        "Which shelters have the largest unmet demand for general meals?"]
REPORTS = [
    "Kita Community Center (SH-02), 2026-10-24 21:00. 68 evacuees. 22 meals left. 2 people need allergy-free meals.",
    "Higashi Junior High Gym (SH-03), 2026-10-24 21:15. 240 evacuees. 0 meals. Halal: 5 people. Please send dinner.",
    "Minami Elementary School (SH-01), 2026-10-24 21:30. 131 evacuees, 18 meals on hand, 3 infants need formula.",
]
QUESTIONS = ["Which shelf has the canned bread?", "Is any label partly hidden or unreadable?",
             "How many boxes of miso soup are visible?"]


def main():
    assert config.USAGE_LOG_PATH == os.path.join(config.LIVE_DATA_DIR, "usage_log.jsonl")
    config.PHOTO_DIR = tempfile.mkdtemp(prefix="p34-photos-")
    received = "2026-10-24T22:00+09:00"
    for q in CHAT:
        run_agent(q, [])
    run_agent(CHAT[0], [])                                  # deliberate repeat
    for text in REPORTS:
        extract_shelter_report(text, received)
    extract_shelter_report(REPORTS[0], received)            # deliberate repeat
    # New images (cropped variants of the synthetic samples) so the provider sees new content
    work = tempfile.mkdtemp(prefix="p34-img-")
    paths = []
    for name, box in (("synthetic_wh_a_aisle2.png", (0, 0, 1100, 620)), ("synthetic_wh_b_bay1.png", (0, 60, 1280, 760))):
        out = os.path.join(work, "crop_" + name)
        Image.open(os.path.join(ROOT, "data/sample_photos", name)).crop(box).save(out)
        paths.append(out)
    a = analyze_warehouse_photo(paths[0], "WH-A")
    analyze_warehouse_photo(paths[1], "WH-B")
    analyze_warehouse_photo(paths[0], "WH-A")               # deliberate repeat (same image and prompt)
    for q in QUESTIONS:                                      # same photo: shared prefix (analysis + image)
        ask_about_photo(a["analysis_id"], q)
    print("done:", config.USAGE_LOG_PATH)


if __name__ == "__main__":
    main()
