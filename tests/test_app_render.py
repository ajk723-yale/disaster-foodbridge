from app import markdown_safe


def test_placeholders_keep_their_brackets():
    assert markdown_safe("Date: [DATE]") == r"Date: \[DATE\]"
    assert markdown_safe("To: [RECIPIENT: PREFECTURE]\nFrom: [SENDER]") == r"To: \[RECIPIENT: PREFECTURE\]" + "\n" + r"From: \[SENDER\]"


def test_real_links_and_plain_text_are_unchanged():
    assert markdown_safe("see [the guide](https://example.org)") == "see [the guide](https://example.org)"
    assert markdown_safe("| a | b |\n|---|---|") == "| a | b |\n|---|---|"
