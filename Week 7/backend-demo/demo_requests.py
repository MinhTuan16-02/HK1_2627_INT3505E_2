"""Demo HTTP that, chay sau khi da mo run.py. Khong can thu vien ngoai."""
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def call(base, method, path, body=None, expected=200):
    data = json.dumps(body).encode() if body is not None else None
    req = Request(base + path, data=data, method=method,
                  headers={"Content-Type": "application/json"})
    try:
        response = urlopen(req, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        payload = response.read().decode()
        print(f"{method:6} {path:18} -> {response.status} {payload}")
        assert response.status == expected, f"Expected {expected}"
        return json.loads(payload) if payload else None


if __name__ == "__main__":
    for port, title, invalid_status in [(5001, "CODE-FIRST", 422), (5002, "DESIGN-FIRST", 400)]:
        print(f"\n=== {title} ===")
        base = f"http://127.0.0.1:{port}"
        call(base, "GET", "/products")
        item = call(base, "POST", "/products", {"name": "Man hinh demo", "price": 2500000}, 201)
        call(base, "GET", f"/products/{item['id']}")
        call(base, "POST", "/products", {"name": "Gia sai", "price": -1}, invalid_status)
        call(base, "DELETE", f"/products/{item['id']}", expected=204)
        call(base, "GET", f"/products/{item['id']}", expected=404)
    print("\nPASS: ca hai API tra dung cac status mong doi.")
