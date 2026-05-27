from app.services.summary_policy import merge_summaries, should_compress


def test_summary_compress_threshold():
    assert should_compress(total_messages=20, raw_messages_size=10, messages_summary_size=5) is True
    assert should_compress(total_messages=14, raw_messages_size=10, messages_summary_size=5) is False


def test_merge_summaries():
    merged = merge_summaries("old", "new")
    assert merged == "old\nnew"


def test_summary_disabled_if_message_summary_size_zero():
    assert should_compress(total_messages=50, raw_messages_size=10, messages_summary_size=0) is False
