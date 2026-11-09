"""DESIGN-FIRST: ten ham duoc tham chieu boi operationId trong YAML.

Khong khai bao route/decorator/schema request tai day.
"""
from flask import current_app


def _store():
    return current_app.config["PRODUCT_STORE"]


def list_products():
    return _store().list(), 200


def create_product(body):
    return _store().create(body), 201


def get_product(product_id):
    item = _store().get(product_id)
    if item is None:
        return {"message": "Khong tim thay san pham"}, 404
    return item, 200


def delete_product(product_id):
    if not _store().delete(product_id):
        return {"message": "Khong tim thay san pham"}, 404
    return "", 204
