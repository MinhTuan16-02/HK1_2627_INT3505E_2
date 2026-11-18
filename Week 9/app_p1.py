from flask import Flask

from blueprints.v1 import bp as v1
from blueprints.v2 import bp as v2

app = Flask(__name__)
app.register_blueprint(v1, url_prefix=f"/api/v1{v1.url_prefix}")
app.register_blueprint(v2, url_prefix=f"/api/v2{v2.url_prefix}")


if __name__ == "__main__":
    app.run(port=5000, debug=True)
