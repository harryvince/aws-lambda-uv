import app
import pytest


class FakeSqs:
    def __init__(self, depth: int) -> None:
        self.depth = depth

    def get_queue_attributes(self, **kwargs: object) -> dict:
        return {"Attributes": {"ApproximateNumberOfMessages": str(self.depth)}}


@pytest.mark.parametrize("depth", [0, 3])
def test_reports_the_dead_letter_queue_depth(monkeypatch: pytest.MonkeyPatch, depth: int) -> None:
    monkeypatch.setattr(app, "sqs_client", lambda: FakeSqs(depth))
    monkeypatch.setenv("DEAD_LETTER_QUEUE_URL", "https://sqs.example/dlq")

    assert app.handler({}, None) == {"failedJobs": depth}
