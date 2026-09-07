import time

from job_manager import JobManager


def wait_for_terminal(manager, job_id):
    for _ in range(100):
        status = manager.get(job_id)
        if status["status"] in {"succeeded", "failed"}:
            return status
        time.sleep(0.005)
    raise AssertionError("job did not finish")


def test_job_manager_runs_task_and_exposes_result():
    manager = JobManager(max_workers=1)
    try:
        job_id = manager.submit("demo", lambda: {"count": 2})
        status = wait_for_terminal(manager, job_id)
    finally:
        manager.shutdown()

    assert status["job_id"] == job_id
    assert status["operation"] == "demo"
    assert status["status"] == "succeeded"
    assert status["result"] == {"count": 2}
    assert status["error"] is None
    assert status["finished_at"] is not None


def test_job_manager_hides_internal_failure_details():
    def fail():
        raise RuntimeError("database password leaked")

    manager = JobManager(max_workers=1)
    try:
        job_id = manager.submit("demo", fail)
        status = wait_for_terminal(manager, job_id)
    finally:
        manager.shutdown()

    assert status["status"] == "failed"
    assert status["result"] is None
    assert status["error"] == "작업 실행에 실패했습니다."
    assert "password" not in str(status)


def test_job_manager_returns_none_for_unknown_job():
    manager = JobManager(max_workers=1)
    try:
        assert manager.get("missing") is None
    finally:
        manager.shutdown()
