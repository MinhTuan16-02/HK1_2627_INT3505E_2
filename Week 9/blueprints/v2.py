from threading import Lock

from flask import Blueprint, jsonify, request

from .users_data import USERS, get_user

bp = Blueprint("v2", __name__, url_prefix="/users")
_users_lock = Lock()


@bp.get("/<int:uid>")
def read_user(uid):
    user = get_user(uid)
    if user is None:
        return jsonify(error="User not found"), 404

    return jsonify(user)


@bp.post("")
def create_user():
    data = request.get_json(silent=True)
    fields = ("first_name", "last_name", "email")
    if not isinstance(data, dict) or not all(
        isinstance(data.get(field), str) and data[field].strip() for field in fields
    ):
        return jsonify(error="first_name, last_name, and email are required"), 400

    with _users_lock:
        uid = max(USERS, default=0) + 1
        user = {"id": uid, **{field: data[field].strip() for field in fields}}
        USERS[uid] = user

    return jsonify(user), 201
