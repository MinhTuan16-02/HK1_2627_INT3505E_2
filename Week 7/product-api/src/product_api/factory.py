import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, request
from flask_smorest import Api
from werkzeug.utils import import_string
from werkzeug.exceptions import BadRequest

from .config import DefaultConfig
from .errors import register_error_handlers
from .extensions import db, migrate
from .logging_config import configure


def create_app(config=None):
    load_dotenv()
    app = Flask(__name__, instance_path=str(Path.cwd() / "instance"))
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    selected = config if config is not None else os.getenv("APP_CONFIG", DefaultConfig)
    if isinstance(selected, str):
        selected = import_string(selected)
    app.config.from_object(DefaultConfig())
    if isinstance(selected, dict):
        app.config.update(selected)
    else:
        app.config.from_object(selected() if isinstance(selected, type) else selected)
    app.config.from_prefixed_env("APP")
    app.json.sort_keys = False
    db.init_app(app)
    migrate.init_app(app, db, directory=str(Path(__file__).parent / "migrations"))
    configure(app)

    @app.before_request
    def require_json():
        if request.path.startswith("/api/v1/") and request.method in {"POST", "PATCH"}:
            if not request.is_json:
                raise BadRequest("Content-Type must be application/json")

    from .api.products import products_bp
    from .api.orders import orders_bp
    from .api.health import health_bp

    api = Api(app)
    api.register_blueprint(products_bp)
    api.register_blueprint(orders_bp)
    app.register_blueprint(health_bp)
    register_error_handlers(app)
    return app
