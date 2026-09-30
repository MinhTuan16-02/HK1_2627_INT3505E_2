import logging
from flask import Flask, jsonify, make_response, request
from werkzeug.exceptions import HTTPException

logging.basicConfig(level=logging.ERROR)

app = Flask(__name__)
app.config["PROPAGATE_EXCEPTIONS"] = False


# RFC 7807 custom exception
class ProblemError(Exception):
    def __init__(self, status=400, title=None, detail=None, type_uri="about:blank", instance=None):
        super().__init__(detail or title)
        self.status = status
        self.title = title or {
            400: "Bad Request",
            404: "Not Found",
            422: "Unprocessable Entity",
            500: "Internal Server Error"
        }.get(status, "Error")
        self.detail = detail
        self.type_uri = type_uri
        self.instance = instance


def build_problem_response(status, title, detail, type_uri="about:blank", instance=None):
    payload = {
        "type": type_uri,
        "title": title,
        "status": status,
        "detail": detail,
        "instance": instance or request.path
    }
    resp = make_response(jsonify(payload), status)
    resp.headers["Content-Type"] = "application/problem+json"
    return resp


@app.errorhandler(ProblemError)
def handle_problem_error(err):
    return build_problem_response(
        status=err.status,
        title=err.title,
        detail=err.detail,
        type_uri=err.type_uri,
        instance=err.instance or request.path
    )


@app.errorhandler(HTTPException)
def handle_http_exception(err):
    return build_problem_response(
        status=err.code,
        title=err.name,
        detail=err.description,
        type_uri="about:blank",
        instance=request.path
    )


@app.errorhandler(Exception)
def handle_unexpected_exception(err):
    app.logger.error("Unhandled Exception: %s", str(err), exc_info=True)
    return build_problem_response(
        status=500,
        title="Internal Server Error",
        detail="An unexpected error occurred on the server.",
        type_uri="about:blank",
        instance=request.path
    )


RESOURCES = {
    1: {"id": 1, "name": "Resource A"}
}


@app.get("/resources/<int:res_id>")
def get_resource(res_id):
    item = RESOURCES.get(res_id)
    if not item:
        raise ProblemError(
            status=404,
            title="Not Found",
            detail=f"Resource {res_id} not found",
            type_uri="about:blank"
        )
    return jsonify(item), 200


@app.get("/crash")
def crash():
    return 1 / 0


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)