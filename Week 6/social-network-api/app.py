import os
import secrets
from collections import deque
from functools import wraps
from math import ceil
from threading import Lock
from time import monotonic, time

from argon2 import PasswordHasher, Type
from argon2.exceptions import VerificationError
from flask import Flask, jsonify, request
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    create_refresh_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
)

app = Flask(__name__)
app.config.update(
    JWT_SECRET_KEY=os.environ.get("JWT_SECRET_KEY") or secrets.token_hex(32),
    JWT_ACCESS_TOKEN_EXPIRES=900,
    JWT_REFRESH_TOKEN_EXPIRES=2592000,
    JWT_ALGORITHM="HS256",
    JWT_DECODE_ALGORITHMS=["HS256"],
    JWT_TOKEN_LOCATION=["headers"],
    JWT_ENCODE_ISSUER="social-network-api",
    JWT_DECODE_ISSUER="social-network-api",
    JWT_ENCODE_AUDIENCE="social-network-client",
    JWT_DECODE_AUDIENCE="social-network-client",
)
jwt = JWTManager(app)
ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, type=Type.ID)

USERS = {
    1: {
        "id": 1,
        "username": "alice",
        "email": "alice@example.com",
        "role": "user",
        "scopes": ["posts:read", "posts:write"],
        "password_hash": "$argon2id$v=19$m=65536,t=3,p=4$b/j4jGvHy1sanMge0iXN7w$tm1oWZoU8wZulcUZO7G3JRSb/Vf7HubXEz35q/XWwsw",
    },
    2: {
        "id": 2,
        "username": "bob",
        "email": "bob@example.com",
        "role": "user",
        "scopes": ["posts:read"],
        "password_hash": "$argon2id$v=19$m=65536,t=3,p=4$JxCmf+HVIB2Z6OptQa1XDw$8hXTnpoIAQKWz5MkSyGjAJjIQlqBIkkS4kBHCpIYBus",
    },
}
DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$5BXI7JfKLj0uSvdGD3F/hg$MErRUsC2m9Dsu/SZgIsJ8HtyU98E+PzkbtA9apcZ4N8"

POSTS = {
    1: {"id": 1, "title": "Hello SOA", "content": "Alice's public post.",
        "author_id": 1, "is_private": False},
    2: {"id": 2, "title": "Alice's notes", "content": "Alice's private post.",
        "author_id": 1, "is_private": True},
    3: {"id": 3, "title": "Bob's notes", "content": "Bob's private post.",
        "author_id": 2, "is_private": True},
}

BLOCKLIST = {}
TOKEN_LOCK = Lock()
LOGIN_ATTEMPTS = {}
LOGIN_LOCK = Lock()
LOGIN_LIMIT = 10
LOGIN_WINDOW = 60
MAX_LOGIN_CLIENTS = 1024


def login_retry_after():
    now = monotonic()
    client_ip = request.remote_addr or "unknown"
    with LOGIN_LOCK:
        for ip, attempts in list(LOGIN_ATTEMPTS.items()):
            while attempts and attempts[0] <= now - LOGIN_WINDOW:
                attempts.popleft()
            if not attempts:
                del LOGIN_ATTEMPTS[ip]
        if client_ip not in LOGIN_ATTEMPTS:
            if len(LOGIN_ATTEMPTS) >= MAX_LOGIN_CLIENTS:
                return LOGIN_WINDOW
            LOGIN_ATTEMPTS[client_ip] = deque()
        attempts = LOGIN_ATTEMPTS[client_ip]
        if len(attempts) >= LOGIN_LIMIT:
            return max(1, ceil(attempts[0] + LOGIN_WINDOW - now))
        attempts.append(now)
    return 0


def prune_blocklist():
    now = time()
    for jti, expires_at in list(BLOCKLIST.items()):
        if expires_at <= now:
            del BLOCKLIST[jti]


@jwt.token_in_blocklist_loader
def token_is_revoked(jwt_header, jwt_payload):
    with TOKEN_LOCK:
        prune_blocklist()
        return jwt_payload["jti"] in BLOCKLIST


@jwt.unauthorized_loader
def missing_token(reason):
    return jsonify(error="unauthorized"), 401


@jwt.invalid_token_loader
def invalid_token(reason):
    return jsonify(error="unauthorized"), 401


@jwt.expired_token_loader
def expired_token(jwt_header, jwt_payload):
    return jsonify(error="unauthorized"), 401


@jwt.revoked_token_loader
def revoked_token(jwt_header, jwt_payload):
    return jsonify(error="unauthorized"), 401


@app.after_request
def prevent_sensitive_caching(response):
    response.headers["Cache-Control"] = "no-store"
    return response


def issue_tokens(user):
    claims = {
        "user_id": user["id"],
        "roles": [user["role"]],
        "scopes": list(user["scopes"]),
    }
    identity = str(user["id"])
    return {
        "access_token": create_access_token(identity=identity, additional_claims=claims),
        "refresh_token": create_refresh_token(identity=identity),
    }


def require_scopes(*needed):
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            granted = get_jwt().get("scopes", [])
            if (not isinstance(granted, list)
                    or not all(isinstance(scope, str) for scope in granted)
                    or not set(needed).issubset(granted)):
                return jsonify(error="insufficient_scope"), 403
            return fn(*args, **kwargs)
        return wrapped
    return decorate


@app.post("/auth/login")
def login():
    retry_after = login_retry_after()
    if retry_after:
        return jsonify(error="rate_limited"), 429, {"Retry-After": str(retry_after)}

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="invalid_request"), 400
    identifier = data.get("username") or data.get("email")
    password = data.get("password")
    if (not isinstance(identifier, str) or not identifier.strip()
            or not isinstance(password, str) or not password
            or len(identifier) > 254 or len(password) > 1024):
        return jsonify(error="invalid_request"), 400

    identifier = identifier.strip().lower()
    user = next((u for u in USERS.values()
                 if identifier in (u["username"], u["email"])), None)
    # User không tồn tại vẫn chạy Argon2 với cùng tham số chi phí.
    password_hash = user["password_hash"] if user else DUMMY_HASH
    try:
        verified = ph.verify(password_hash, password)
    except VerificationError:
        verified = False
    if user is None or not verified:
        return jsonify(error="invalid_credentials"), 401
    if ph.check_needs_rehash(user["password_hash"]):
        user["password_hash"] = ph.hash(password)
    return jsonify(issue_tokens(user)), 200


@app.post("/auth/refresh")
@jwt_required(refresh=True)
def refresh():
    user = next((u for u in USERS.values()
                 if str(u["id"]) == get_jwt_identity()), None)
    if user is None:
        return jsonify(error="unauthorized"), 401
    token = get_jwt()
    # Kiểm tra lại và thu hồi trong cùng khóa để hai request không rotate cùng jti.
    with TOKEN_LOCK:
        prune_blocklist()
        if token["jti"] in BLOCKLIST:
            return jsonify(error="unauthorized"), 401
        pair = issue_tokens(user)
        BLOCKLIST[token["jti"]] = token["exp"]
    return jsonify(pair), 200


@app.get("/posts/<int:id>")
@jwt_required()
@require_scopes("posts:read")
def get_post(id):
    post = POSTS.get(id)
    if post is None:
        return jsonify(error="not_found"), 404
    # Scope cho phép hành động đọc; bài riêng tư còn phải đúng chủ sở hữu.
    current_user_id = get_jwt().get("user_id")
    if post["is_private"] and current_user_id != post["author_id"]:
        return jsonify(
            error="forbidden",
            message="You do not have permission to view this private post",
        ), 403
    return jsonify({key: post[key] for key in
                    ("id", "title", "content", "author_id", "is_private")}), 200


if __name__ == "__main__":
    app.run(port=5000, debug=True)
