from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass

from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import ForeignKey, Integer, String, and_, func, or_, select
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload


db = SQLAlchemy()

DEFAULT_LIMIT = 20
MAX_LIMIT = 100
MAX_INT = 2**31 - 1
CURSOR_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class Category(db.Model):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    slug: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)

    books: Mapped[list["Book"]] = relationship(back_populates="category")


class Book(db.Model):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    isbn: Mapped[str] = mapped_column(String(13), unique=True, nullable=False)
    price_vnd: Mapped[int] = mapped_column(Integer, nullable=False)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id"),
        nullable=False
    )

    category: Mapped[Category] = relationship(back_populates="books")

    def to_dict(self) -> dict:
        return {
            "id": f"book_{self.id}",
            "title": self.title,
            "isbn": self.isbn,
            "price": {
                "amount": self.price_vnd,
                "currency": "VND",
            },
            "category": {
                "id": self.category.id,
                "slug": self.category.slug,
                "name": self.category.name,
            },
        }


SORT = {
    "id": Book.id,
    "price": Book.price_vnd,
    "title": Book.title,
}


@dataclass(frozen=True)
class SortKey:
    name: str
    descending: bool

    @property
    def col(self):
        return SORT[self.name]

    def order_clause(self):
        if self.descending:
            return self.col.desc()
        return self.col.asc()


def parse_sort(raw: str):
    if not isinstance(raw, str) or not raw or len(raw) > 200:
        raise ValueError("bad_sort")

    keys = []
    seen = set()

    for part in raw.split(","):
        item = part.strip()

        if not item:
            raise ValueError("bad_sort")

        descending = item.startswith("-")
        name = item[1:] if descending else item

        if not name or name not in SORT or name in seen:
            raise ValueError("bad_sort")

        keys.append(SortKey(name, descending))
        seen.add(name)

    canonical_sort = ",".join(
        ("-" if key.descending else "") + key.name
        for key in keys
    )

    if "id" not in seen:
        keys.append(SortKey("id", keys[-1].descending))

    order_columns = [key.order_clause() for key in keys]

    return keys, order_columns, canonical_sort


def _enc(state: dict) -> str:
    payload = json.dumps(
        state,
        separators=(",", ":"),
        ensure_ascii=False
    ).encode("utf-8")

    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _dec(raw: str) -> dict:
    if (
        not isinstance(raw, str)
        or len(raw) > 2048
        or not CURSOR_RE.fullmatch(raw)
    ):
        raise ValueError("bad_cursor")

    try:
        padded = raw + "=" * (-len(raw) % 4)

        binary = base64.b64decode(
            padded,
            altchars=b"-_",
            validate=True
        )

        data = json.loads(binary.decode("utf-8"))

    except (
        binascii.Error,
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError("bad_cursor") from exc

    if not isinstance(data, dict):
        raise ValueError("bad_cursor")

    if set(data) != {"s", "v", "i", "f"}:
        raise ValueError("bad_cursor")

    return data


def _cursor_values(book: Book, keys: list[SortKey]) -> list:
    values = []

    for key in keys:
        if key.name == "id":
            continue

        if key.name == "price":
            values.append(book.price_vnd)
        else:
            values.append(getattr(book, key.name))

    return values


def apply_cursor(
    query,
    raw: str | None,
    sort: str,
    keys: list[SortKey],
    filters: dict,
):
    if raw is None:
        return query, None

    try:
        state = _dec(raw)

        if not isinstance(state["s"], str):
            raise ValueError("bad_cursor")

        if not isinstance(state["f"], dict):
            raise ValueError("bad_cursor")

        if set(state["f"]) != {"genre", "category"}:
            raise ValueError("bad_cursor")

        if state["s"] != sort:
            return query, "sort_chg"

        if state["f"] != filters:
            return query, "filter_chg"

        if (
            type(state["i"]) is not int
            or state["i"] < 1
            or state["i"] > MAX_INT
        ):
            raise ValueError("bad_cursor")

        non_id_keys = [
            key for key in keys
            if key.name != "id"
        ]

        values = state["v"]

        if not isinstance(values, list):
            raise ValueError("bad_cursor")

        if len(values) != len(non_id_keys):
            raise ValueError("bad_cursor")

        for key, value in zip(non_id_keys, values):
            if key.name == "price":
                if (
                    type(value) is not int
                    or value < 0
                    or value > MAX_INT
                ):
                    raise ValueError("bad_cursor")

            elif key.name == "title":
                if (
                    not isinstance(value, str)
                    or len(value) > 200
                ):
                    raise ValueError("bad_cursor")

            else:
                raise ValueError("bad_cursor")

        by_name = dict(
            zip(
                [key.name for key in non_id_keys],
                values
            )
        )

        by_name["id"] = state["i"]

        clauses = []
        prefix = []

        for key in keys:
            value = by_name[key.name]

            if key.descending:
                comparison = key.col < value
            else:
                comparison = key.col > value

            clauses.append(
                and_(
                    *prefix,
                    comparison
                )
            )

            prefix.append(key.col == value)

        return query.where(or_(*clauses)), None

    except ValueError:
        return query, "bad_cursor"


def build_response(
    items: list[Book],
    sort: str,
    keys: list[SortKey],
    more: bool,
    filters: dict,
):
    next_cursor = None

    if more and items:
        last = items[-1]

        next_cursor = _enc({
            "s": sort,
            "v": _cursor_values(last, keys),
            "i": last.id,
            "f": filters,
        })

    return jsonify({
        "data": [
            book.to_dict()
            for book in items
        ],
        "page": {
            "next": next_cursor,
            "more": more,
        },
    })


def _positive_int(
    raw,
    field: str,
    default: int,
    minimum: int = 1,
):
    if raw is None:
        return default

    if not re.fullmatch(r"[0-9]+", raw):
        raise ValueError("bad_" + field)

    value = int(raw)

    if value < minimum or value > MAX_INT:
        raise ValueError("bad_" + field)

    return value


def seed_data():
    existing = db.session.scalar(
        select(Book.id).limit(1)
    )

    if existing is not None:
        return

    categories = [
        Category(
            id=1,
            name="Technology",
            slug="tech",
        ),
        Category(
            id=2,
            name="Fiction",
            slug="fiction",
        ),
        Category(
            id=3,
            name="Science",
            slug="science",
        ),
    ]

    db.session.add_all(categories)

    data = [
        (1, "Python Basics", 450000, 1),
        (2, "API Design", 450000, 1),
        (3, "API Design", 450000, 1),
        (4, "Distributed Systems", 620000, 1),
        (5, "Clean Architecture", 450000, 1),
        (6, "Data Pipelines", 390000, 1),
        (7, "The Silent River", 180000, 2),
        (8, "Blue Horizon", 210000, 2),
        (9, "Winter Garden", 180000, 2),
        (10, "Astrophysics", 530000, 3),
        (11, "Quantum World", 530000, 3),
        (12, "Biology Today", 310000, 3),
    ]

    books = []

    for book_id, title, price, category_id in data:
        books.append(
            Book(
                id=book_id,
                title=title,
                price_vnd=price,
                category_id=category_id,
                isbn=f"978{1000000000 + book_id:010d}",
            )
        )

    db.session.add_all(books)
    db.session.commit()


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)

    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///lab2.db",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    app.json.sort_keys = False

    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    @app.get("/api/v1/books")
    def list_books():
        try:
            strategy = request.args.get(
                "strategy",
                "cursor"
            )

            if strategy not in {"cursor", "offset"}:
                raise ValueError("bad_strategy")

            limit = _positive_int(
                request.args.get("limit"),
                "limit",
                DEFAULT_LIMIT,
            )

            limit = min(limit, MAX_LIMIT)

            raw_sort = request.args.get(
                "sort",
                "-id"
            )

            keys, order_columns, sort = parse_sort(
                raw_sort
            )

            raw_category = request.args.get(
                "category"
            )

            if raw_category is None:
                category = None
            else:
                category = _positive_int(
                    raw_category,
                    "category",
                    0,
                )

            genre = request.args.get("genre")

            if genre is not None:
                if not re.fullmatch(
                    r"[a-z0-9-]{1,60}",
                    genre
                ):
                    raise ValueError("bad_genre")

            filters = {
                "genre": genre,
                "category": category,
            }

            predicates = []

            if genre is not None:
                predicates.append(
                    Book.category.has(
                        Category.slug == genre
                    )
                )

            if category is not None:
                predicates.append(
                    Book.category_id == category
                )

            query = (
                select(Book)
                .options(
                    selectinload(Book.category)
                )
                .where(*predicates)
                .order_by(*order_columns)
            )

            if strategy == "offset":
                if request.args.get("cursor") is not None:
                    raise ValueError("bad_cursor")

                offset = _positive_int(
                    request.args.get("offset"),
                    "offset",
                    0,
                    minimum=0,
                )

                total = db.session.scalar(
                    select(
                        func.count(Book.id)
                    ).where(*predicates)
                )

                rows = db.session.scalars(
                    query
                    .offset(offset)
                    .limit(limit)
                ).all()

                return jsonify({
                    "data": [
                        book.to_dict()
                        for book in rows
                    ],
                    "pagination": {
                        "offset": offset,
                        "limit": limit,
                        "total": total,
                        "has_next": offset + limit < total,
                    },
                })

            if request.args.get("offset") is not None:
                raise ValueError("bad_offset")

            query, error = apply_cursor(
                query,
                request.args.get("cursor"),
                sort,
                keys,
                filters,
            )

            if error:
                return jsonify({
                    "error": error
                }), 400

            rows = db.session.scalars(
                query.limit(limit + 1)
            ).all()

            return build_response(
                rows[:limit],
                sort,
                keys,
                len(rows) > limit,
                filters,
            )

        except ValueError as exc:
            return jsonify({
                "error": str(exc)
            }), 400

    with app.app_context():
        db.create_all()

        if app.config.get(
            "SEED_DATA",
            True
        ):
            seed_data()

    return app


if __name__ == "__main__":
    create_app().run(
        host="127.0.0.1",
        port=5001,
        debug=False,
    )