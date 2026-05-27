def should_compress(total_messages: int, raw_messages_size: int, messages_summary_size: int) -> bool:
    if messages_summary_size < 1:
        return False
    threshold = raw_messages_size + messages_summary_size - 1
    return total_messages > threshold


def merge_summaries(existing: str | None, fresh: str) -> str:
    return "\n".join(item for item in [existing, fresh] if item).strip()
