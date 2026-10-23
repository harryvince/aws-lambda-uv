import json
from pathlib import Path

import app
import pytest

EVENT = json.loads((Path(__file__).parents[2] / "events" / "process_upload.json").read_text())


class FakeSqs:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send_message(self, **kwargs: str) -> None:
        self.sent.append(kwargs)


@pytest.fixture
def sqs(monkeypatch: pytest.MonkeyPatch) -> FakeSqs:
    fake = FakeSqs()
    monkeypatch.setattr(app, "sqs_client", lambda: fake)
    monkeypatch.setenv("JOBS_QUEUE_URL", "https://sqs.example/jobs")

    return fake


def test_queues_a_job_per_upload(sqs: FakeSqs) -> None:
    assert app.handler(EVENT, None) == {"queued": 1}
    assert sqs.sent[0]["QueueUrl"] == "https://sqs.example/jobs"
    assert json.loads(sqs.sent[0]["MessageBody"]) == {
        "bucket": "aws-lambda-uv-dev-uploads",
        "key": "incoming/quarterly report.csv",
        "size": 1024,
    }
