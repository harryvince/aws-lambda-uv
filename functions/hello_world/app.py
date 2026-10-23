import json
import logging
import os
from typing import Any

from pydantic import BaseModel, Field, ValidationError

# Set per stack by template.yaml: dev, test, stage or prod.
STAGE = os.environ.get("STAGE", "local")

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


class GreetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    excited: bool = False


def greet(request: GreetRequest) -> str:
    return f"Hello, {request.name}{'!' if request.excited else '.'}"


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Handles an API Gateway HTTP API (payload format 2.0) request."""
    try:
        request = GreetRequest.model_validate_json(event.get("body") or "{}")
    except ValidationError as error:
        logger.debug("Rejected request: %s", error)

        return response(400, {"errors": error.errors(include_url=False, include_context=False)})

    return response(200, {"message": greet(request), "stage": STAGE})


def response(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }
