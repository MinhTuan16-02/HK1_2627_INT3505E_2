import base64
import json
from flask import Flask, jsonify, request

app = Flask(__name__)

ORDERS = [
    {"id": 1, "customer_id": 101, "total": 120.5, "status": "paid", "created_at": "2026-03-01T08:00:00Z"},
    {"id": 2, "customer_id": 102, "total": 450.0, "status": "pending", "created_at": "2026-03-02T09:30:00Z"},
    {"id": 3, "customer_id": 101, "total": 89.0, "status": "paid", "created_at": "2026-03-03T11:15:00Z"},
    {"id": 4, "customer_id": 103, "total": 310.0, "status": "cancelled", "created_at": "2026-03-04T14:20:00Z"},
    {"id": 5, "customer_id": 102, "total": 150.0, "status": "paid", "created_at": "2026-03-05T15:00:00Z"},
    {"id": 6, "customer_id": 104, "total": 620.0, "status": "paid", "created_at": "2026-03-06T16:45:00Z"},
    {"id": 7, "customer_id": 101, "total": 210.0, "status": "pending", "created_at": "2026-03-07T18:10:00Z"},
    {"id": 8, "customer_id": 105, "total": 95.0, "status": "paid", "created_at": "2026-03-08T19:00:00Z"},
]


def encode_cursor(last_id):
    """Mã hóa ID bản ghi cuối thành token opaque (Base64) theo chuẩn Stripe"""
    payload = json.dumps({"after_id": last_id})
    return base64.b64encode(payload.encode("utf-8")).decode("utf-8")


def decode_cursor(cursor_str):
    """Giải mã cursor token; trả về None nếu chuỗi bị lỗi cấu trúc"""
    try:
        raw_bytes = base64.b64decode(cursor_str.encode("utf-8"), validate=True)
        data = json.loads(raw_bytes.decode("utf-8"))
        if "after_id" not in data or not isinstance(data["after_id"], int):
            return None
        return data["after_id"]
    except Exception:
        return None


@app.get("/orders")
def get_orders():
    cursor_param = request.args.get("cursor")
    after_id = None
    if cursor_param:
        after_id = decode_cursor(cursor_param)
        if after_id is None:
            return jsonify({
                "type": "about:blank",
                "title": "Bad Request",
                "status": 400,
                "detail": "Invalid or corrupted cursor format",
                "instance": request.path
            }), 400

    try:
        limit = int(request.args.get("limit", 5))
        if limit <= 0:
            limit = 5
        limit = min(limit, 50)
    except ValueError:
        return jsonify({
            "type": "about:blank",
            "title": "Bad Request",
            "status": 400,
            "detail": "limit parameter must be a positive integer",
            "instance": request.path
        }), 400

    results = list(ORDERS)

    status_filter = request.args.get("status")
    if status_filter:
        results = [o for o in results if o["status"].lower() == status_filter.strip().lower()]

    cust_filter = request.args.get("customer_id")
    if cust_filter:
        try:
            cid = int(cust_filter)
            results = [o for o in results if o["customer_id"] == cid]
        except ValueError:
            return jsonify({
                "type": "about:blank",
                "title": "Bad Request",
                "status": 400,
                "detail": "customer_id must be an integer",
                "instance": request.path
            }), 400

    sort_query = request.args.get("sort", "id").strip()
    reverse = False
    sort_field = sort_query

    if sort_query.startswith("-"):
        reverse = True
        sort_field = sort_query[1:]
    elif sort_query.endswith("_desc"):
        reverse = True
        sort_field = sort_query.replace("_desc", "")

    if results and sort_field in results[0]:
        results = sorted(results, key=lambda x: x[sort_field], reverse=reverse)

    if after_id is not None:
        idx_match = None
        for i, item in enumerate(results):
            if item["id"] == after_id:
                idx_match = i
                break
        if idx_match is not None:
            results = results[idx_match + 1:]
        else:
            results = []

    page_items = results[:limit]

    has_more = len(results) > limit
    next_cursor = encode_cursor(page_items[-1]["id"]) if (has_more and page_items) else None

    fields_query = request.args.get("fields")
    if fields_query:
        selected_fields = [f.strip() for f in fields_query.split(",") if f.strip()]
        page_items = [
            {k: item[k] for k in selected_fields if k in item}
            for item in page_items
        ]

    return jsonify({
        "data": page_items,
        "pagination": {
            "limit": limit,
            "has_more": has_more,
            "next_cursor": next_cursor
        }
    }), 200


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)