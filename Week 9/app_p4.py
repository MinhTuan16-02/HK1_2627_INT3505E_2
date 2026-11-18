from flask import Flask, jsonify, request

from gateway import dispatch

app = Flask(__name__)


@app.post("/orders")
def create_order():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(error="Expected a JSON object"), 400

    result = dispatch(body)
    version = result["version"]
    response = jsonify(result)
    response.headers["X-Order-Handler"] = version
    return response, 201 if version == "v2" else 200


if __name__ == "__main__":
    app.run(port=5000, debug=True)
