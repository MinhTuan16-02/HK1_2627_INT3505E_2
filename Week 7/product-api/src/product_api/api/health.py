from flask import Blueprint, current_app
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db

health_bp = Blueprint("health", __name__)


@health_bp.get("/healthz")
def liveness():
    return {"status": "ok"}, 200


@health_bp.get("/ready")
def readiness():
    try:
        db.session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.warning("database_unavailable")
        return {"status": "degraded", "checks": {"db": "err"}}, 503
    return {"status": "ok", "checks": {"db": "ok"}}, 200
