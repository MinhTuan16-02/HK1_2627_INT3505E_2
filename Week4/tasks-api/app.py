from datetime import date
from pathlib import Path
from uuid import uuid4

import yaml
from flask import Flask, jsonify, make_response, request, url_for

from auth import valid_token
from db import get_connection, init_db

app = Flask(__name__)
SPEC_PATH = Path(__file__).with_name("openapi.yaml")

STATUS_VALUES = {"open", "in_progress", "done"}
PRIORITY_VALUES = {"low", "normal", "high"}
FIELD_MAP = {
    "title": "title",
    "status": "status",
    "priority": "priority",
    "dueDate": "due_date",
    "assigneeId": "assignee_id",
}


def problem(status, title, detail):
    response = jsonify({
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
    })
    response.status_code = status
    response.content_type = "application/problem+json"
    return response


def task_json(row):
    return {
        "id": row["id"],
        "title": row["title"],
        "status": row["status"],
        "priority": row["priority"],
        "dueDate": row["due_date"],
        "assigneeId": row["assignee_id"],
    }


def check_task(data, partial=False):
    if not isinstance(data, dict):
        return "Body phải là JSON object."
    if not partial and "title" not in data:
        return "Thiếu trường title."
    if partial and not data:
        return "Cần ít nhất một trường để cập nhật."

    extra = set(data) - set(FIELD_MAP)
    if extra:
        return f"Trường không hỗ trợ: {', '.join(sorted(extra))}."

    if "title" in data:
        title = data["title"]
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 200:
            return "title phải là chuỗi từ 1 đến 200 ký tự."

    if "status" in data and (not isinstance(data["status"], str) or data["status"] not in STATUS_VALUES):
        return "status chỉ nhận open, in_progress hoặc done."
    if "priority" in data and (not isinstance(data["priority"], str) or data["priority"] not in PRIORITY_VALUES):
        return "priority chỉ nhận low, normal hoặc high."

    if "dueDate" in data and data["dueDate"] is not None:
        value = data["dueDate"]
        if not isinstance(value, str) or len(value) != 10:
            return "dueDate phải có dạng YYYY-MM-DD."
        try:
            if date.fromisoformat(value).isoformat() != value:
                return "dueDate phải có dạng YYYY-MM-DD."
        except ValueError:
            return "dueDate không hợp lệ."

    if "assigneeId" in data:
        user_id = data["assigneeId"]
        if user_id is not None and (not isinstance(user_id, str) or not user_id.strip()):
            return "assigneeId phải là chuỗi không rỗng hoặc null."
    return None


@app.before_request
def require_auth():
    if request.path.startswith("/v1/tasks"):
        if not valid_token(request.headers.get("Authorization", "")):
            response = problem(401, "Unauthorized", "Thiếu hoặc sai Bearer token.")
            response.headers["WWW-Authenticate"] = "Bearer"
            return response


@app.get("/openapi.json")
def get_spec():
    with SPEC_PATH.open(encoding="utf-8") as file:
        return jsonify(yaml.safe_load(file))


@app.get("/docs")
def docs():
    return """<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>Tasks API - Swagger UI</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    SwaggerUIBundle({url: '/openapi.json', dom_id: '#swagger-ui'});
  </script>
</body>
</html>"""


@app.get("/v1/tasks")
def list_tasks():
    status = request.args.get("status")
    limit_text = request.args.get("limit", "20")
    if status is not None and status not in STATUS_VALUES:
        return problem(400, "Bad Request", "status không hợp lệ.")
    try:
        limit = int(limit_text)
    except ValueError:
        return problem(400, "Bad Request", "limit phải là số nguyên.")
    if not 1 <= limit <= 100:
        return problem(400, "Bad Request", "limit phải nằm trong khoảng 1–100.")

    clause = "WHERE status = ?" if status else ""
    args = (status,) if status else ()
    with get_connection() as db:
        total = db.execute(f"SELECT COUNT(*) FROM tasks {clause}", args).fetchone()[0]
        rows = db.execute(
            f"SELECT * FROM tasks {clause} ORDER BY rowid DESC LIMIT ?",
            (*args, limit),
        ).fetchall()
    return jsonify({"items": [task_json(row) for row in rows], "total": total, "limit": limit})


@app.post("/v1/tasks")
def create_task():
    if not request.is_json:
        return problem(415, "Unsupported Media Type", "Cần Content-Type: application/json.")
    data = request.get_json(silent=True)
    if data is None:
        return problem(400, "Bad Request", "Body JSON không hợp lệ.")
    detail = check_task(data)
    if detail:
        return problem(422, "Unprocessable Content", detail)

    task_id = str(uuid4())
    title = data["title"].strip()
    status = data.get("status", "open")
    priority = data.get("priority", "normal")
    due_date = data.get("dueDate")
    assignee_id = data.get("assigneeId")
    with get_connection() as db:
        db.execute("""
            INSERT INTO tasks (id, title, status, priority, due_date, assignee_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (task_id, title, status, priority, due_date, assignee_id))
        row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()

    response = make_response(jsonify(task_json(row)), 201)
    response.headers["Location"] = url_for("get_task", task_id=task_id, _external=True)
    return response


@app.get("/v1/tasks/<task_id>")
def get_task(task_id):
    with get_connection() as db:
        row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        return problem(404, "Not Found", "Không tìm thấy task.")
    return jsonify(task_json(row))


@app.patch("/v1/tasks/<task_id>")
def patch_task(task_id):
    if not request.is_json:
        return problem(415, "Unsupported Media Type", "Cần Content-Type: application/json.")
    data = request.get_json(silent=True)
    if data is None:
        return problem(400, "Bad Request", "Body JSON không hợp lệ.")
    detail = check_task(data, partial=True)
    if detail:
        return problem(422, "Unprocessable Content", detail)

    updates = ", ".join(f"{FIELD_MAP[key]} = ?" for key in data)
    values = [data[key].strip() if key == "title" else data[key] for key in data]
    with get_connection() as db:
        found = db.execute("SELECT id FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if found is None:
            return problem(404, "Not Found", "Không tìm thấy task.")
        db.execute(f"UPDATE tasks SET {updates} WHERE id = ?", (*values, task_id))
        row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return jsonify(task_json(row))


@app.delete("/v1/tasks/<task_id>")
def delete_task(task_id):
    with get_connection() as db:
        result = db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        if result.rowcount == 0:
            return problem(404, "Not Found", "Không tìm thấy task.")
    return "", 204


init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
