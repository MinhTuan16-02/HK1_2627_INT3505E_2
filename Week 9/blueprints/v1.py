from flask import Blueprint, jsonify

from .users_data import get_user

bp = Blueprint("v1", __name__, url_prefix="/users")


@bp.get("/<int:uid>")
def read_user(uid):
    user = get_user(uid)
    if user is None:
        return jsonify(error="User not found"), 404

    return jsonify(
        id=user["id"],
        full_name=f"{user['first_name']} {user['last_name']}",
        email=user["email"],
    )
