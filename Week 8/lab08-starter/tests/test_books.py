import pytest
from jsonschema import ValidationError, validate


def test_list_books_empty(client):
    res = client.get("/books")
    assert res.status_code == 200
    assert res.get_json() == []


def test_get_book_not_found(client):
    res = client.get("/books/99999")
    assert res.status_code == 404
    assert res.get_json()["code"] == "NOT_FOUND"


def test_post_book_missing_title(client):
    res = client.post("/books", json={"author": "Author"})
    assert res.status_code == 400
    assert any(error["field"] == "title" for error in res.get_json()["errors"])


def test_delete_then_get_404(client, sample_book):
    res = client.delete(f"/books/{sample_book}")
    assert res.status_code == 204
    res = client.get(f"/books/{sample_book}")
    assert res.status_code == 404


def test_response_extra_field_blocked(client, sample_book):
    schema = {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "title": {"type": "string"},
            "author": {"type": "string"},
            "year": {"type": ["integer", "null"]},
            "isbn": {"type": ["string", "null"]},
        },
        "required": ["id", "title", "author", "year", "isbn"],
        "additionalProperties": False,
    }
    res = client.get(f"/books/{sample_book}")
    assert res.status_code == 200
    payload = res.get_json()
    validate(payload, schema)
    payload["password_hash"] = "secret"
    with pytest.raises(ValidationError, match="password_hash"):
        validate(payload, schema)
