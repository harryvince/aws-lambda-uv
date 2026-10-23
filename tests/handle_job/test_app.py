import json
from pathlib import Path

from app import MAX_SIZE, handler

EVENT = json.loads((Path(__file__).parents[2] / "events" / "handle_job.json").read_text())


def message(message_id: str, body: str) -> dict:
    return {"messageId": message_id, "body": body}


def test_processes_the_sample_event() -> None:
    assert handler(EVENT, None) == {"batchItemFailures": []}


def test_reports_only_the_failed_messages() -> None:
    event = {
        "Records": [
            message("ok", '{"bucket": "b", "key": "small.csv", "size": 10}'),
            message("too-big", json.dumps({"bucket": "b", "key": "big.csv", "size": MAX_SIZE + 1})),
            message("malformed", "not json"),
        ]
    }

    assert handler(event, None) == {
        "batchItemFailures": [{"itemIdentifier": "too-big"}, {"itemIdentifier": "malformed"}]
    }
