from flask import jsonify
from marshmallow import ValidationError
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import HTTPException

from .extensions import db


class ApiError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message="Internal server error", errors=None):
        super().__init__(message)
        self.message = message
        self.errors = errors


class NotFound(ApiError):
    status_code = 404
    code = "not_found"


class Conflict(ApiError):
    status_code = 409
    code = "conflict"


class OutOfStock(Conflict):
    code = "out_of_stock"


class Unprocessable(ApiError):
    status_code = 422
    code = "validation_error"


def register_error_handlers(app):
    def render(code, message, status, errors=None):
        body = {"error": code, "detail": message, "code": code, "message": message}
        if errors is not None:
            body["errors"] = errors
        return jsonify(body), status

    @app.errorhandler(ApiError)
    def api_error(error):
        db.session.rollback()
        return render(error.code, error.message, error.status_code, error.errors)

    @app.errorhandler(ValidationError)
    def validation_error(error):
        return api_error(Unprocessable("Invalid request data", error.messages))

    @app.errorhandler(HTTPException)
    def http_error(error):
        db.session.rollback()
        details = getattr(error, "data", {}).get("messages")
        if error.code == 422:
            return api_error(Unprocessable("Invalid request data", details))
        response = error.get_response()
        body, status = render(error.name.lower().replace(" ", "_"), error.description, error.code)
        response.set_data(body.get_data())
        response.content_type = "application/json"
        response.status_code = status
        return response

    @app.errorhandler(IntegrityError)
    def integrity_error(error):
        db.session.rollback()
        return render("conflict", "Database constraint conflict", 409)

    @app.errorhandler(Exception)
    def unexpected_error(error):
        db.session.rollback()
        app.logger.exception("unhandled_error")
        return render("internal_error", "Internal server error", 500)
