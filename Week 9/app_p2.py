from functools import wraps

from flask import Flask, jsonify, make_response, request

app = Flask(__name__)

LATEST = "2"
SUPPORTED = {"1", "2", "2024-06-20"}
USERS = {
    1: {"id": 1, "first_name": "Văn", "last_name": "Nguyễn", "email": "van.nguyen@example.com"},
    2: {"id": 2, "first_name": "Trang", "last_name": "Trần", "email": "trang.tran@example.com"},
}


def api_version():
    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            version = request.headers.get("X-API-Version", LATEST)
            if version in SUPPORTED:
                response = make_response(view(*args, version=version, **kwargs))
                response.headers["X-API-Version-Served"] = version
            else:
                response = make_response(jsonify(error="Unsupported API version"), 400)
                response.headers["X-API-Version-Served"] = ""
            return response

        return wrapped

    return decorate


@app.get("/users/<int:uid>")
@api_version()
def read_user(uid, version):
    user = USERS.get(uid)
    if user is None:
        return jsonify(error="User not found"), 404

    if version == "1":
        return jsonify(
            id=user["id"],
            full_name=f"{user['first_name']} {user['last_name']}",
            email=user["email"],
        )

    return jsonify(user)


if __name__ == "__main__":
    app.run(port=5000, debug=True)
