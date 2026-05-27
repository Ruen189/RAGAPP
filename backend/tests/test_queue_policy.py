from app.services.queue_policy import check_queue_capacity


def test_queue_allows_when_under_limit():
    allowed, position = check_queue_capacity(active_size=1, max_size=3)
    assert allowed is True
    assert position == 2


def test_queue_rejects_when_full():
    allowed, position = check_queue_capacity(active_size=3, max_size=3)
    assert allowed is False
    assert position == 3


def test_queue_allows_first_position():
    allowed, position = check_queue_capacity(active_size=0, max_size=3)
    assert allowed is True
    assert position == 1
