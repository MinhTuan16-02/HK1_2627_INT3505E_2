from marshmallow import RAISE, Schema, ValidationError, fields, validate, validates_schema

MAX_INT = 2_147_483_647


def nonblank(value):
    if not value.strip():
        raise ValidationError("Must not be blank.")


class StrictSchema(Schema):
    class Meta:
        unknown = RAISE


class ProductIn(StrictSchema):
    sku = fields.Str(required=True, validate=[validate.Length(min=3, max=32), nonblank])
    name = fields.Str(required=True, validate=[validate.Length(min=1, max=255), nonblank])
    description = fields.Str(allow_none=True, validate=validate.Length(max=2000))
    price_cents = fields.Int(required=True, strict=True, validate=validate.Range(min=0, max=MAX_INT))
    qty_in_stock = fields.Int(load_default=0, strict=True, validate=validate.Range(min=0, max=MAX_INT))


class ProductPatch(ProductIn):
    class Meta:
        unknown = RAISE
        exclude = ("sku",)

    @validates_schema
    def require_changes(self, data, **kwargs):
        if not data:
            raise ValidationError("Provide at least one mutable field.")


class ReserveIn(StrictSchema):
    qty = fields.Int(required=True, strict=True, validate=validate.Range(min=1, max=MAX_INT))


class ProductOut(Schema):
    id = fields.Int()
    sku = fields.Str()
    name = fields.Str()
    description = fields.Str(allow_none=True)
    price_cents = fields.Int()
    qty_in_stock = fields.Int()
    archived = fields.Bool()
    created_at = fields.DateTime()
    updated_at = fields.DateTime()


class PaginationIn(StrictSchema):
    page = fields.Int(load_default=1, validate=validate.Range(min=1, max=MAX_INT))
    size = fields.Int(load_default=20, validate=validate.Range(min=1, max=100))


class ProductPage(Schema):
    items = fields.List(fields.Nested(ProductOut))
    page = fields.Int()
    size = fields.Int()
    total = fields.Int()


class OrderItemIn(ReserveIn):
    product_id = fields.Int(required=True, strict=True, validate=validate.Range(min=1, max=MAX_INT))


class OrderIn(StrictSchema):
    items = fields.List(fields.Nested(OrderItemIn), required=True, validate=validate.Length(min=1, max=100))

    @validates_schema
    def unique_products(self, data, **kwargs):
        ids = [item["product_id"] for item in data["items"]]
        if len(ids) != len(set(ids)):
            raise ValidationError({"items": ["Each product may appear only once."]})


class OrderItemOut(Schema):
    id = fields.Int()
    product_id = fields.Int()
    qty = fields.Int()
    unit_price_cents = fields.Int()
    product = fields.Nested(ProductOut)


class OrderOut(Schema):
    id = fields.Int()
    created_at = fields.DateTime()
    total_cents = fields.Int()
    items = fields.List(fields.Nested(OrderItemOut))


class OrderPage(ProductPage):
    items = fields.List(fields.Nested(OrderOut))


class ErrorOut(Schema):
    error = fields.Str()
    detail = fields.Str()
    code = fields.Str()
    message = fields.Str()
    errors = fields.Raw()
