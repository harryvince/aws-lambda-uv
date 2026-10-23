import logging
import os
from functools import cache
from typing import Any

import boto3

logger = logging.getLogger(__name__)

# Non-prod stages log at DEBUG, which would include every step of each AWS SDK call.
for sdk_logger in ("boto3", "botocore", "urllib3"):
    logging.getLogger(sdk_logger).setLevel(logging.WARNING)


@cache
def sqs_client() -> Any:
    return boto3.client("sqs")


def handler(event: dict[str, Any], context: object) -> dict[str, int]:
    """Runs on an EventBridge Scheduler schedule and reports the dead-letter queue's depth."""
    attributes = sqs_client().get_queue_attributes(
        QueueUrl=os.environ["DEAD_LETTER_QUEUE_URL"],
        AttributeNames=["ApproximateNumberOfMessages"],
    )["Attributes"]
    failed = int(attributes["ApproximateNumberOfMessages"])

    if failed:
        logger.warning("%d failed jobs are waiting in the dead-letter queue", failed)
    else:
        logger.info("No failed jobs")

    return {"failedJobs": failed}
