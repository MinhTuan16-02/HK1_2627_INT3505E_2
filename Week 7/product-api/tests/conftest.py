import pytest

from product_api import create_app
from product_api.config import TestConfig
from product_api.extensions import db


@pytest.fixture
def app():
    application = create_app(TestConfig)
    with application.app_context():
        db.create_all()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_product(client):
    counter = 0

    def create(**overrides):
        nonlocal counter
        counter += 1
        data = {"sku": f"SKU-{counter:04d}", "name": "Keyboard", "price_cents": 2500, "qty_in_stock": 100}
        data.update(overrides)
        response = client.post("/api/v1/products", json=data)
        assert response.status_code == 201, response.json
        return response.json

    return create
