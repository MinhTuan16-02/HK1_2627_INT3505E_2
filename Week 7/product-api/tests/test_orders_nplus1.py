import pytest
from sqlalchemy import event

from product_api.extensions import db

BASE = "/api/v1/orders"


def test_create_order_multiple_products(client, make_product):
    first, second = make_product(), make_product(price_cents=300)
    response = client.post(BASE, json={"items": [{"product_id": first["id"], "qty": 2}, {"product_id": second["id"], "qty": 3}]})
    assert response.status_code == 201, response.json
    assert response.json["total_cents"] == 5900
    assert len(response.json["items"]) == 2
    assert client.get(response.headers["Location"]).status_code == 200
    assert client.get(f"/api/v1/products/{first['id']}").json["qty_in_stock"] == 98
    client.patch(f"/api/v1/products/{first['id']}", json={"price_cents": 9000})
    assert client.get(response.headers["Location"]).json["total_cents"] == 5900


def test_failed_order_rolls_back_stock_and_lines(client, make_product):
    first = make_product(qty_in_stock=10)
    second = make_product(qty_in_stock=0)
    response = client.post(BASE, json={"items": [{"product_id": first["id"], "qty": 2}, {"product_id": second["id"], "qty": 1}]})
    assert response.status_code == 409
    assert client.get(f"/api/v1/products/{first['id']}").json["qty_in_stock"] == 10
    assert client.get(BASE).json["total"] == 0


def test_missing_order_product_rolls_back(client, make_product):
    product = make_product()
    response = client.post(BASE, json={"items": [{"product_id": product["id"], "qty": 1}, {"product_id": 999, "qty": 1}]})
    assert response.status_code == 404
    assert client.get(f"/api/v1/products/{product['id']}").json["qty_in_stock"] == 100
    assert client.get(BASE + "/999").status_code == 404


@pytest.mark.parametrize("items", [[], [{"product_id": 1, "qty": 0}], [{"product_id": 1, "qty": 1}, {"product_id": 1, "qty": 2}]])
def test_order_validation(client, items):
    assert client.post(BASE, json={"items": items}).status_code == 422


def test_eager_loading_query_count_stays_constant(app, client, make_product):
    counts = []
    for number in (1, 12):
        while client.get(BASE).json["total"] < number:
            first, second = make_product(), make_product()
            response = client.post(BASE, json={"items": [{"product_id": first["id"], "qty": 1}, {"product_id": second["id"], "qty": 1}]})
            assert response.status_code == 201
        statements = []

        def capture(connection, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        with app.app_context():
            engine = db.engine
        event.listen(engine, "before_cursor_execute", capture)
        try:
            response = client.get(BASE + "?size=100")
            assert response.status_code == 200
            assert len(response.json["items"]) == number
            assert all(len(order["items"]) == 2 for order in response.json["items"])
            assert all(line["product"]["sku"] for order in response.json["items"] for line in order["items"])
        finally:
            event.remove(engine, "before_cursor_execute", capture)
        counts.append(len(statements))
    assert counts == [4, 4]  # orders + items + products + pagination count


def test_archived_product_kept_in_order_history(client, make_product):
    product = make_product()
    order = client.post(BASE, json={"items": [{"product_id": product["id"], "qty": 1}]}).json
    client.delete(f"/api/v1/products/{product['id']}")
    history = client.get(f"{BASE}/{order['id']}")
    assert history.status_code == 200
    assert history.json["items"][0]["product"]["archived"] is True
    assert client.post(BASE, json={"items": [{"product_id": product["id"], "qty": 1}]}).status_code == 404
