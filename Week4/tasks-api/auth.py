import os
from datetime import datetime, timedelta, timezone

import jwt

SECRET = os.getenv("JWT_SECRET", "local-dev-secret-only")


def valid_token(header):
    if not header.startswith("Bearer "):
        return False
    token = header[7:].strip()
    try:
        jwt.decode(token, SECRET, algorithms=["HS256"], options={"require": ["sub", "exp"]})
        return True
    except jwt.InvalidTokenError:
        return False


if __name__ == "__main__":
    payload = {
        "sub": "week4-demo",
        "exp": datetime.now(timezone.utc) + timedelta(hours=2),
    }
    print(jwt.encode(payload, SECRET, algorithm="HS256"))
