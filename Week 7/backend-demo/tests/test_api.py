"""Kiem thu cung hanh vi HTTP tren hai implementation."""
import pytest
import httpx
from starlette.testclient import TestClient
from code_first.app import create_app as create_code_app
from design_first.app import create_app as create_design_app


@pytest.fixture(params=["code", "design"])
def client(request):
    if request.param == "code":
        test_client = httpx.Client(transport=httpx.WSGITransport(app=create_code_app()),
                                   base_url="http://testserver", follow_redirects=True)
    else:
        test_client = TestClient(create_design_app())
    with test_client:
        yield test_client, request.param


def test_product_lifecycle(client):
    c, _ = client
    assert len(c.get("/products").json()) == 2
    response = c.post("/products", json={"name": "Man hinh", "price": 2500000})
    assert response.status_code == 201
    item = response.json()
    assert item == {"id": 3, "name": "Man hinh", "price": 2500000}
    assert c.get(f"/products/{item['id']}").json() == item
    response = c.delete(f"/products/{item['id']}")
    assert response.status_code == 204
    assert response.content == b""
    assert c.get(f"/products/{item['id']}").status_code == 404
    assert c.delete(f"/products/{item['id']}").status_code == 404


@pytest.mark.parametrize("body", [
    {}, {"name": "Test"}, {"name": "Test", "price": -1},
    {"name": "", "price": 1}, {"name": "x" * 101, "price": 1},
    {"name": None, "price": 1}, {"name": "Test", "price": "abc"},
    {"name": "Test", "price": 1, "unexpected": True},
])
def test_invalid_input_is_rejected_without_writing(client, body):
    c, mode = client
    response = c.post("/products", json=body)
    assert response.status_code == (422 if mode == "code" else 400)
    assert len(c.get("/products").json()) == 2


def test_malformed_json(client):
    c, _ = client
    assert c.post("/products", content="{bad", headers={"Content-Type": "application/json"}).status_code == 400


def test_documentation_and_contract(client):
    c, mode = client
    ui, spec = ("/docs", "/openapi.json") if mode == "code" else ("/ui/", "/openapi.json")
    response = c.get(ui)
    assert response.status_code == 200
    assert "swagger" in response.text.lower()
    contract = c.get(spec).json()
    assert contract["openapi"].startswith("3.0.")
    assert "post" in contract["paths"]["/products"]
    if mode == "design":
        assert contract["paths"]["/products"]["post"]["operationId"] == "design_first.handlers.create_product"
    else:
        assert c.get("/swagger-assets/swagger-ui-bundle.js").status_code == 200


def test_new_app_has_fresh_store():
    # Khong chia se state giua cac application factory.
    first, second = create_code_app(), create_code_app()
    first.test_client().post("/products", json={"name": "Only first", "price": 1})
    assert len(second.test_client().get("/products").json) == 2
