"""Kho du lieu RAM dung chung logic; moi app co mot kho rieng."""
from copy import deepcopy
from threading import Lock


class ProductStore:
    def __init__(self):
        self._lock = Lock()
        self._items = {
            1: {"id": 1, "name": "Ban phim", "price": 450000},
            2: {"id": 2, "name": "Chuot", "price": 200000},
        }
        self._next_id = 3

    def list(self):
        with self._lock:
            return deepcopy(list(self._items.values()))

    def get(self, product_id):
        with self._lock:
            return deepcopy(self._items.get(product_id))

    def create(self, data):
        with self._lock:
            item = {**data, "id": self._next_id}
            self._items[self._next_id] = item
            self._next_id += 1
            return deepcopy(item)

    def delete(self, product_id):
        with self._lock:
            return self._items.pop(product_id, None) is not None
