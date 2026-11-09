import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from sqlalchemy.exc import OperationalError

from product_api import create_app
from product_api.extensions import db
from product_api.logging_config import JsonFormatter

BASE = "/api/v1/products"


def test_product_lifecycle(client, make_product):
    product = make_product(description="Mechanical")
    path = f"{BASE}/{product['id']}"
    assert client.get(path).json["description"] == "Mechanical"
    response = client.patch(path, json={"name": "New name"})
    assert response.json["price_cents"] == 2500
    assert response.json["qty_in_stock"] == 100
    assert response.json["name"] == "New name"
    assert client.post(path + "/reserve", json={"qty": 3}).json["qty_in_stock"] == 97
    assert client.delete(path).status_code == 204
    assert client.get(path).status_code == 404
    assert client.get(BASE).json["total"] == 0
    assert client.post(path + "/reserve", json={"qty": 1}).status_code == 404


def test_duplicate_sku_rollback(client, make_product):
    product = make_product()
    payload = {key: product[key] for key in ("sku", "name", "price_cents")}
    response = client.post(BASE, json=payload)
    assert response.status_code == 409
    assert response.json["error"] == response.json["code"] == "conflict"
    make_product()
    assert client.get(BASE).json["total"] == 2


@pytest.mark.parametrize("change", [
    {"sku": "ab"}, {"sku": "x" * 33}, {"name": " "}, {"name": "x" * 256},
    {"price_cents": -1}, {"price_cents": 1.5}, {"price_cents": True},
    {"price_cents": "12"}, {"qty_in_stock": -1}, {"qty_in_stock": None},
    {"id": 1}, {"archived": True}, {"description": "x" * 2001},
])
def test_invalid_product(client, change):
    payload = {"sku": "ABC", "name": "Valid", "price_cents": 5}
    payload.update(change)
    response = client.post(BASE, json=payload)
    assert response.status_code == 422
    assert response.json["code"] == "validation_error"
    assert response.json["errors"]
    assert client.get(BASE).json["total"] == 0


@pytest.mark.parametrize("payload", [{}, [], None])
def test_invalid_json_shapes(client, payload):
    response = client.post(BASE, data=json.dumps(payload), content_type="application/json")
    assert response.status_code == 422


def test_bad_json_and_content_type(client):
    assert client.post(BASE, data="{", content_type="application/json").status_code == 400
    assert client.post(BASE, data="{}", content_type="text/plain").status_code in (400, 415)
    response = client.get("/missing")
    assert response.status_code == 404
    assert response.is_json


def test_pagination(client, make_product):
    for _ in range(5):
        make_product()
    page = client.get(BASE + "?page=2&size=2").json
    assert (page["page"], page["size"], page["total"]) == (2, 2, 5)
    assert [item["id"] for item in page["items"]] == [3, 4]
    for query in ("page=abc", "page=0", "size=101", "size=-1", "unknown=1"):
        assert client.get(BASE + "?" + query).status_code == 422


def test_reserve_insufficient_and_invalid(client, make_product):
    product = make_product(qty_in_stock=2)
    path = f"{BASE}/{product['id']}"
    assert client.post(path + "/reserve", json={"qty": 3}).status_code == 409
    assert client.get(path).json["qty_in_stock"] == 2
    for qty in (0, -1, 1.5, True):
        assert client.post(path + "/reserve", json={"qty": qty}).status_code == 422
    assert client.post(BASE + "/999/reserve", json={"qty": 1}).status_code == 404


def test_patch_rejects_empty_and_immutable_fields(client, make_product):
    product = make_product()
    for body in ({}, {"sku": "OTHER"}, {"price_cents": -1}, {"name": ""}, {"archived": True}):
        assert client.patch(f"{BASE}/{product['id']}", json=body).status_code == 422


def test_health_probes_and_request_id(client):
    response = client.get("/healthz", headers={"X-Request-Id": "lab-request-1"})
    assert response.json == {"status": "ok"}
    assert response.headers["X-Request-Id"] == "lab-request-1"
    assert client.get("/ready").json["checks"]["db"] == "ok"
    with patch.object(db.session, "execute", side_effect=OperationalError("SELECT 1", {}, Exception("offline"))):
        assert client.get("/healthz").status_code == 200
        assert client.get("/ready").status_code == 503


def test_method_not_allowed_keeps_allow_header(client):
    response = client.put(BASE, json={})
    assert response.status_code == 405
    assert "POST" in response.headers["Allow"]


def test_concurrent_reservations_do_not_oversell(tmp_path):
    app = create_app({"TESTING": True, "LOG_LEVEL": "WARNING", "SQLALCHEMY_DATABASE_URI": "sqlite:///" + (tmp_path / "stock.db").as_posix()})
    with app.app_context():
        db.create_all()
    with app.test_client() as client:
        product = client.post(BASE, json={"sku": "LAST", "name": "Last", "price_cents": 1, "qty_in_stock": 1}).json
    path = f"{BASE}/{product['id']}"

    def reserve(_):
        with app.test_client() as client:
            return client.post(path + "/reserve", json={"qty": 1}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve, range(2))) == [200, 409]
    with app.test_client() as client:
        assert client.get(path).json["qty_in_stock"] == 0
    with app.app_context():
        db.engine.dispose()


def test_openapi(client):
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    assert spec.json["openapi"] == "3.0.3"
    assert "/api/v1/orders" in spec.json["paths"]
    assert "post" in spec.json["paths"]["/api/v1/products/{product_id}/reserve"]


def test_logging_has_structured_fields(app, client):
    records = []
    with patch.object(app.logger.handlers[0], "emit", side_effect=records.append):
        client.get("/healthz", headers={"X-Request-Id": "trace-123"})
    # Capture at INFO; the testing profile intentionally filters these events.
    app.logger.setLevel("INFO")
    with patch.object(app.logger.handlers[0], "emit", side_effect=records.append):
        client.get("/healthz")
    record = records[-1]
    payload = json.loads(JsonFormatter().format(record))
    assert payload["status"] == 200
    assert payload["latency_ms"] >= 0
