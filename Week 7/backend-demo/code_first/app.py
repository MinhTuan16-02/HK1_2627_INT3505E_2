"""CODE-FIRST: route + schema Python -> OpenAPI -> Swagger UI."""
from flask import Flask, redirect
from flask.views import MethodView
from flask_smorest import Api, Blueprint, abort
from marshmallow import Schema, fields, validate, RAISE
from store import ProductStore


class ProductInput(Schema):
    class Meta:
        unknown = RAISE

    name = fields.String(required=True, validate=validate.Length(min=1, max=100))
    price = fields.Float(required=True, allow_nan=False,
                         validate=validate.Range(min=0))


class ProductOutput(ProductInput):
    id = fields.Integer(dump_only=True)


def create_app():
    app = Flask(__name__)
    app.config.update(
        API_TITLE="Code-First - Product API", API_VERSION="1.0.0",
        OPENAPI_VERSION="3.0.3", OPENAPI_URL_PREFIX="/",
        OPENAPI_JSON_PATH="openapi.json", OPENAPI_SWAGGER_UI_PATH="/docs",
        OPENAPI_SWAGGER_UI_URL="/swagger-assets/",
    )
    # Swagger assets cuc bo: demo khong can CDN/Internet.
    from pathlib import Path
    from flask import send_from_directory
    from swagger_ui_bundle import swagger_ui_path

    @app.get("/swagger-assets/<path:filename>")
    def swagger_assets(filename):
        return send_from_directory(Path(swagger_ui_path), filename)

    api = Api(app)
    store = ProductStore()
    blp = Blueprint("products", __name__, url_prefix="/products",
                    description="Quan ly san pham - viet Python truoc")

    @blp.route("")
    class Products(MethodView):
        @blp.response(200, ProductOutput(many=True))
        def get(self):
            """Danh sach san pham."""
            return store.list()

        @blp.arguments(ProductInput)
        @blp.response(201, ProductOutput)
        def post(self, data):
            """Tao san pham; schema Python kiem tra request."""
            return store.create(data)

    @blp.route("/<int:product_id>")
    class Product(MethodView):
        @blp.response(200, ProductOutput)
        @blp.alt_response(404, description="Khong tim thay san pham")
        def get(self, product_id):
            """Lay mot san pham."""
            item = store.get(product_id)
            if item is None:
                abort(404, message="Khong tim thay san pham")
            return item

        @blp.response(204)
        @blp.alt_response(404, description="Khong tim thay san pham")
        def delete(self, product_id):
            """Xoa san pham."""
            if not store.delete(product_id):
                abort(404, message="Khong tim thay san pham")

    api.register_blueprint(blp)

    @app.get("/")
    def home():
        return redirect("/docs")

    return app
