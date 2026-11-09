import json
import logging
import re
import sys
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from flask import g, has_request_context, request


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        if has_request_context():
            payload["request_id"] = getattr(g, "request_id", "-")
        for key in ("status", "latency_ms", "method", "path"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure(app):
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    app.logger.handlers = [handler]
    app.logger.propagate = False
    app.logger.setLevel(app.config["LOG_LEVEL"])

    @app.before_request
    def start_request():
        incoming = request.headers.get("X-Request-Id", "")
        g.request_id = incoming if re.fullmatch(r"[A-Za-z0-9._-]{1,128}", incoming) else uuid4().hex
        g.started_at = perf_counter()

    @app.after_request
    def finish_request(response):
        response.headers["X-Request-Id"] = g.request_id
        app.logger.info("request_completed", extra={
            "status": response.status_code,
            "latency_ms": round((perf_counter() - g.started_at) * 1000, 3),
            "method": request.method,
            "path": request.path,
        })
        return response
