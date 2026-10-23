import json
import logging
import os
from functools import cache
from typing import Any
from urllib.parse import unquote_plus

import boto3

logger = logging.getLogger(__name__)

# Non-prod stages log at DEBUG, which would include every step of each AWS SDK call.
for sdk_logger in ("boto3", "botocore", "urllib3"):
    logging.getLogger(sdk_logger).setLevel(logging.WARNING)


@cache
def sqs_client() -> Any:
    return boto3.client("sqs")


def handler(event: dict[str, Any], context: object) -> dict[str, int]:
    """Handles S3 ObjectCreated notifications by queueing one job per new object."""
    queue_url = os.environ["JOBS_QUEUE_URL"]
    queued = 0

    for record in event["Records"]:
        s3 = record["s3"]
        # S3 URL-encodes keys in events, with spaces as "+".
        job = {
            "bucket": s3["bucket"]["name"],
            "key": unquote_plus(s3["object"]["key"]),
            "size": s3["object"].get("size", 0),
        }

        sqs_client().send_message(QueueUrl=queue_url, MessageBody=json.dumps(job))
        logger.info("Queued job for s3://%s/%s", job["bucket"], job["key"])
        queued += 1

    return {"queued": queued}
