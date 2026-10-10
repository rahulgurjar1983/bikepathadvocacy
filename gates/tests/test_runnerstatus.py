import datetime
import json


def test_fr0_36_wait_status_keeps_reason_and_retry_while_heartbeating(repo):
    from gates.runnerstatus import heartbeat, write

    write("quota_wait", row="C1.4", reason="Both plan limits", retry_seconds=120, pr=118)
    path = repo.path / ".ralph/status.json"
    first = json.loads(path.read_text())
    assert first["phase"] == "quota_wait"
    assert first["row"] == "C1.4"
    assert (
        110
        < (
            datetime.datetime.fromisoformat(first["retry_at"]) - datetime.datetime.now(datetime.UTC)
        ).total_seconds()
        <= 120
    )
    heartbeat()
    second = json.loads(path.read_text())
    assert second["retry_at"] == first["retry_at"]
    assert second["reason"] == first["reason"]
    assert second["heartbeat_at"] >= first["heartbeat_at"]
    write("running", row="C1.4")
    current = json.loads(path.read_text())
    assert current["row"] == "C1.4"
    assert current["pr"] == 118
    assert "retry_at" not in current
