import logging
from typing import Any

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

# Uploads above this are refused, to show a failing job.
MAX_SIZE = 10 * 1024 * 1024


class Job(BaseModel):
    bucket: str
    key: str
    size: int = Field(ge=0)


def process(job: Job) -> None:
    if job.size > MAX_SIZE:
        raise ValueError(f"{job.key} is {job.size} bytes, over the {MAX_SIZE} byte limit")

    logger.info("Processed s3://%s/%s (%d bytes)", job.bucket, job.key, job.size)


def handler(event: dict[str, Any], context: object) -> dict[str, list[dict[str, str]]]:
    """Handles a batch of SQS messages.

    Each failed message is reported on its own (ReportBatchItemFailures), so only those go back on
    the queue to be retried, and after maxReceiveCount attempts SQS moves them to the dead-letter
    queue. The rest of the batch counts as done.
    """
    failures = []

    for record in event["Records"]:
        try:
            process(Job.model_validate_json(record["body"]))
        except (ValidationError, ValueError) as error:
            logger.warning("Job %s failed: %s", record["messageId"], error)
            failures.append({"itemIdentifier": record["messageId"]})

    return {"batchItemFailures": failures}
