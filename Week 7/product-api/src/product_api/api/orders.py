from flask import url_for
from flask.views import MethodView
from flask_smorest import Blueprint
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from marshmallow import RAISE

from ..errors import NotFound
from ..extensions import db
from ..models import Order, OrderItem
from .products import take_stock
from .schemas import ErrorOut, OrderIn, OrderOut, OrderPage, PaginationIn

orders_bp = Blueprint("orders", __name__, url_prefix="/api/v1/orders", description="Orders with multiple product lines")


def orders_query():
    # Two selectinload levels bound serialization to three SELECTs.
    return db.select(Order).options(selectinload(Order.items).selectinload(OrderItem.product))


@orders_bp.route("")
class OrderList(MethodView):
    @orders_bp.arguments(PaginationIn, location="query", unknown=RAISE)
    @orders_bp.response(200, OrderPage)
    def get(self, query):
        """List orders with eager-loaded items and products."""
        rows = db.session.scalars(orders_query().order_by(Order.id).offset((query["page"] - 1) * query["size"]).limit(query["size"])).all()
        total = db.session.scalar(db.select(func.count()).select_from(Order))
        return {"items": rows, **query, "total": total}

    @orders_bp.arguments(OrderIn)
    @orders_bp.response(201, OrderOut)
    @orders_bp.alt_response(404, schema=ErrorOut)
    @orders_bp.alt_response(409, schema=ErrorOut)
    def post(self, body):
        """Create all lines and deduct stock in one transaction."""
        order = Order(items=[])
        # Consistent lock order avoids opposing product-lock acquisition.
        for line in sorted(body["items"], key=lambda item: item["product_id"]):
            product = take_stock(line["product_id"], line["qty"])
            order.items.append(OrderItem(product=product, qty=line["qty"], unit_price_cents=product.price_cents))
        db.session.add(order)
        db.session.flush()
        order_id = order.id
        db.session.commit()
        saved = db.session.scalar(orders_query().where(Order.id == order_id))
        return saved, 201, {"Location": url_for("orders.OrderDetail", order_id=order_id)}


@orders_bp.route("/<int:order_id>")
class OrderDetail(MethodView):
    @orders_bp.response(200, OrderOut)
    @orders_bp.alt_response(404, schema=ErrorOut)
    def get(self, order_id):
        """Get an order including its product lines."""
        order = db.session.scalar(orders_query().where(Order.id == order_id))
        if order is None:
            raise NotFound("Order not found")
        return order
