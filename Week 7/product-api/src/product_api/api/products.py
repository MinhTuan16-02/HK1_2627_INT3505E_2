from flask import url_for
from flask.views import MethodView
from flask_smorest import Blueprint
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from marshmallow import RAISE

from ..errors import Conflict, NotFound, OutOfStock
from ..extensions import db
from ..models import Product
from .schemas import ErrorOut, PaginationIn, ProductIn, ProductOut, ProductPage, ProductPatch, ReserveIn

products_bp = Blueprint("products", __name__, url_prefix="/api/v1/products", description="Product CRUD and stock reservation")


def active_product(product_id):
    product = db.session.scalar(db.select(Product).where(Product.id == product_id, Product.archived.is_(False)))
    if product is None:
        raise NotFound("Product not found")
    return product


def take_stock(product_id, qty):
    # Predicate and decrement share one statement, preventing overselling.
    product = db.session.scalar(
        update(Product).where(
            Product.id == product_id, Product.archived.is_(False), Product.qty_in_stock >= qty
        ).values(qty_in_stock=Product.qty_in_stock - qty)
        .returning(Product).execution_options(populate_existing=True)
    )
    if product is None:
        active_product(product_id)
        raise OutOfStock("Insufficient stock")
    return product


@products_bp.route("")
class ProductList(MethodView):
    @products_bp.arguments(PaginationIn, location="query", unknown=RAISE)
    @products_bp.response(200, ProductPage)
    def get(self, query):
        """List active products with pagination."""
        base = db.select(Product).where(Product.archived.is_(False))
        rows = db.session.scalars(base.order_by(Product.id).offset((query["page"] - 1) * query["size"]).limit(query["size"])).all()
        total = db.session.scalar(db.select(func.count()).select_from(Product).where(Product.archived.is_(False)))
        return {"items": rows, **query, "total": total}

    @products_bp.arguments(ProductIn)
    @products_bp.response(201, ProductOut)
    @products_bp.alt_response(409, schema=ErrorOut)
    def post(self, body):
        """Create a product; SKU remains unique after archiving."""
        product = Product(**body)
        db.session.add(product)
        try:
            db.session.commit()
        except IntegrityError as error:
            db.session.rollback()
            raise Conflict("SKU already exists") from error
        return product, 201, {"Location": url_for("products.ProductDetail", product_id=product.id)}


@products_bp.route("/<int:product_id>")
class ProductDetail(MethodView):
    @products_bp.response(200, ProductOut)
    @products_bp.alt_response(404, schema=ErrorOut)
    def get(self, product_id):
        """Get an active product."""
        return active_product(product_id)

    @products_bp.arguments(ProductPatch(partial=True))
    @products_bp.response(200, ProductOut)
    def patch(self, body, product_id):
        """Update only fields present in the request."""
        product = active_product(product_id)
        for key, value in body.items():
            setattr(product, key, value)
        db.session.commit()
        return product

    @products_bp.response(204)
    def delete(self, product_id):
        """Archive a product."""
        product = active_product(product_id)
        product.archived = True
        db.session.commit()
        return ""


@products_bp.route("/<int:product_id>/reserve")
class ProductReserve(MethodView):
    @products_bp.arguments(ReserveIn)
    @products_bp.response(200, ProductOut)
    @products_bp.alt_response(409, schema=ErrorOut)
    def post(self, body, product_id):
        """Atomically decrease stock."""
        product = take_stock(product_id, body["qty"])
        db.session.commit()
        return product
