import json

from app import handler


def call(body: str | None) -> tuple[int, dict]:
    result = handler({"body": body}, None)

    return result["statusCode"], json.loads(result["body"])


def test_greets_by_name() -> None:
    assert call('{"name": "Ada"}') == (200, {"message": "Hello, Ada.", "stage": "local"})


def test_greets_excitedly() -> None:
    assert call('{"name": "Ada", "excited": true}') == (
        200,
        {"message": "Hello, Ada!", "stage": "local"},
    )


def test_rejects_a_missing_name() -> None:
    status, body = call(None)

    assert status == 400
    assert body["errors"][0]["loc"] == ["name"]
