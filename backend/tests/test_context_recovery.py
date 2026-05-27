from app.models import JobStatus


def recover_statuses(statuses: list[JobStatus]) -> list[JobStatus]:
    return [JobStatus.queued if item in {JobStatus.thinking, JobStatus.retrieving, JobStatus.responding} else item for item in statuses]


def test_recovery_moves_inflight_to_queue():
    recovered = recover_statuses([JobStatus.thinking, JobStatus.responding, JobStatus.done])
    assert recovered == [JobStatus.queued, JobStatus.queued, JobStatus.done]
