def check_queue_capacity(active_size: int, max_size: int) -> tuple[bool, int]:
    """Returns (allowed, queue_position)."""
    if active_size >= max_size:
        return False, active_size
    return True, active_size + 1
