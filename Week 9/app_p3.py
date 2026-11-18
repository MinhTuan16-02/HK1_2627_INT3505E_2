from datetime import datetime, timezone

from flask import Flask

from blueprints.v1 import read_user
from sunset import deprecate_at

app = Flask(__name__)
V1_SUNSET = datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc)


@app.get("/api/v1/users/<int:uid>")
@deprecate_at(V1_SUNSET, replacement="/api/v2/users")
def read_v1_user(uid):
    return read_user(uid)


if __name__ == "__main__":
    app.run(port=5000, debug=True)
