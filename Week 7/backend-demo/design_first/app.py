"""DESIGN-FIRST: OpenAPI YAML -> routes + validation -> handlers."""
from pathlib import Path
from connexion import FlaskApp
from store import ProductStore


def create_app():
    app = FlaskApp(__name__, specification_dir=str(Path(__file__).parent))
    app.app.config["PRODUCT_STORE"] = ProductStore()
    app.add_api("openapi.yaml", strict_validation=True, validate_responses=True)

    @app.app.get("/")
    def home():
        from flask import redirect
        return redirect("/ui/")

    return app
