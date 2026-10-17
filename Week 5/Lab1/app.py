from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request, url_for
from flask_sqlalchemy import SQLAlchemy
from jsonschema import Draft202012Validator, ValidationError, validate
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    event,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload


db = SQLAlchemy()

SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "book.json"
BOOK_SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

# Kiểm tra schema ngay khi ứng dụng được import.
Draft202012Validator.check_schema(BOOK_SCHEMA)


@event.listens_for(Engine, "connect")
def enable_foreign_keys(conn, _record):
    """Bật foreign-key enforcement cho SQLite."""
    if conn.__class__.__module__.startswith("sqlite3"):
        conn.execute("PRAGMA foreign_keys=ON")


def utc_iso(value: datetime | None) -> str | None:
    """Chuyển datetime sang ISO 8601 UTC."""
    if value is None:
        return None

    if value.tzinfo is None:
        # SQLite thường làm mất timezone metadata.
        value = value.replace(tzinfo=timezone.utc)

    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


# ============================================================
# MODELS
# ============================================================

class BookAuthor(db.Model):
    __tablename__ = "book_authors"

    book_id: Mapped[int] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"),
        primary_key=True,
    )
    author_id: Mapped[int] = mapped_column(
        ForeignKey("authors.id"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default="co",
    )

    __table_args__ = (
        CheckConstraint(
            "role IN ('lead','co','ed')",
            name="ck_book_author_role",
        ),
    )

    book: Mapped["Book"] = relationship(
        back_populates="author_links"
    )
    author: Mapped["Author"] = relationship(
        back_populates="book_links"
    )


class Category(db.Model):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(
        String(60),
        unique=True,
        nullable=False,
    )

    books: Mapped[list["Book"]] = relationship(
        back_populates="category"
    )


class Author(db.Model):
    __tablename__ = "authors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    bio: Mapped[str | None] = mapped_column(Text)

    book_links: Mapped[list[BookAuthor]] = relationship(
        back_populates="author"
    )


class User(db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    # Field nội bộ, không expose qua API.
    internal_note: Mapped[str | None] = mapped_column(
        String(255)
    )

    reviews: Mapped[list["Review"]] = relationship(
        back_populates="user"
    )


class Book(db.Model):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    isbn: Mapped[str] = mapped_column(
        String(13),
        unique=True,
        nullable=False,
    )

    price_amount: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    price_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="VND",
    )

    # Chỉ có ý nghĩa trực tiếp khi currency = VND.
    price_vnd: Mapped[int | None] = mapped_column(Integer)

    stock: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id")
    )

    published_at: Mapped[date | None] = mapped_column(
        db.Date
    )

    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    category: Mapped[Category | None] = relationship(
        back_populates="books"
    )

    author_links: Mapped[list[BookAuthor]] = relationship(
        back_populates="book",
        cascade="all, delete-orphan",
    )

    reviews: Mapped[list["Review"]] = relationship(
        back_populates="book",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "stock >= 0",
            name="ck_book_stock",
        ),
    )

    def to_dict(self) -> dict:
        """
        API representation:
        - ID có prefix.
        - Không lộ foreign key / field nội bộ.
        - Time theo ISO 8601.
        - Embed category và authors cần thiết cho client.
        """
        links = sorted(
            self.author_links,
            key=lambda link: link.author_id,
        )

        return {
            "id": f"book_{self.id}",
            "title": self.title,
            "isbn": self.isbn,
            "price": {
                "amount": self.price_amount,
                "currency": self.price_currency,
            },
            "inStock": self.stock > 0,
            "stock": self.stock,
            "category": (
                {
                    "id": f"category_{self.category.id}",
                    "name": self.category.name,
                    "slug": self.category.slug,
                }
                if self.category
                else None
            ),
            "authors": [
                {
                    "id": f"author_{link.author.id}",
                    "name": link.author.name,
                    "role": link.role,
                }
                for link in links
            ],
            "publishedAt": (
                self.published_at.isoformat()
                if self.published_at
                else None
            ),
            "createdAt": utc_iso(self.created_at),
        }


class Review(db.Model):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)

    rating: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    comment: Mapped[str | None] = mapped_column(Text)

    book_id: Mapped[int] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "rating BETWEEN 1 AND 5",
            name="ck_review_rating",
        ),
    )

    book: Mapped[Book] = relationship(
        back_populates="reviews"
    )

    user: Mapped[User] = relationship(
        back_populates="reviews"
    )

    def to_dict(self) -> dict:
        return {
            "id": f"review_{self.id}",
            "rating": self.rating,
            "comment": self.comment,
            "user": {
                "id": f"user_{self.user.id}",
                "displayName": self.user.display_name,
            },
        }


# ============================================================
# HELPERS
# ============================================================

def bad(error: str, status: int = 400, **extra):
    return jsonify({
        "error": error,
        **extra,
    }), status


def validation_error_response(e: ValidationError):
    """
    Chuẩn hóa lỗi JSON Schema.

    Với lỗi required, jsonschema thường trả path của object cha.
    Ta bổ sung chính tên field đang thiếu để response hữu ích hơn.
    """
    field = list(e.path)

    if e.validator == "required":
        missing_fields = [
            name
            for name in e.validator_value
            if name not in e.instance
        ]

        if missing_fields:
            field.append(missing_fields[0])

    return jsonify({
        "error": "validation_failed",
        "field": field,
        "message": e.message,
    }), 400


def parse_prefixed_id(
    value: str,
    prefix: str,
) -> int | None:
    """
    author_12 -> 12
    category_3 -> 3

    Trả None nếu format không hợp lệ.
    """
    if not isinstance(value, str):
        return None

    expected = f"{prefix}_"

    if not value.startswith(expected):
        return None

    raw_id = value[len(expected):]

    if not raw_id.isdigit():
        return None

    parsed = int(raw_id)

    if parsed < 1:
        return None

    return parsed


def load_book(book_ref: str) -> Book | None:
    """
    Chấp nhận book_42.
    """
    book_id = parse_prefixed_id(book_ref, "book")

    if book_id is None:
        return None

    return db.session.get(Book, book_id)


def ensure_references(
    payload: dict,
) -> tuple[list[tuple[Author, str]] | None, object | None]:
    """
    Kiểm tra Author và Category trước khi ghi DB.

    API dùng prefixed ID:
        author_1
        category_1

    DB vẫn lưu integer FK:
        1
    """
    links: list[tuple[Author, str]] = []
    seen_author_ids: set[int] = set()

    for index, author_data in enumerate(
        payload.get("authors", [])
    ):
        author_ref = author_data["id"]

        author_id = parse_prefixed_id(
            author_ref,
            "author",
        )

        if author_id is None:
            return None, bad(
                "invalid_author_id",
                field=["authors", index, "id"],
            )

        if author_id in seen_author_ids:
            return None, bad(
                "duplicate_author",
                field=["authors", index, "id"],
            )

        seen_author_ids.add(author_id)

        author = db.session.get(
            Author,
            author_id,
        )

        if author is None:
            return None, bad(
                "unknown_author",
                field=["authors", index, "id"],
                author_id=author_ref,
            )

        links.append(
            (
                author,
                author_data["role"],
            )
        )

    if "categoryId" in payload:
        category_ref = payload["categoryId"]

        category_id = parse_prefixed_id(
            category_ref,
            "category",
        )

        if category_id is None:
            return None, bad(
                "invalid_category_id",
                field=["categoryId"],
            )

        category = db.session.get(
            Category,
            category_id,
        )

        if category is None:
            return None, bad(
                "unknown_category",
                field=["categoryId"],
                category_id=category_ref,
            )

    return links, None


def apply_payload(
    book: Book,
    payload: dict,
    author_links: list[tuple[Author, str]],
):
    """
    Map API payload -> persistence model.

    Phần authors được đồng bộ theo ID thay vì xóa rồi insert mù,
    giúp PATCH gửi lại cùng author hiện có không gây lỗi unique PK.
    """
    if "title" in payload:
        book.title = payload["title"]

    if "isbn" in payload:
        book.isbn = payload["isbn"]

    if "price" in payload:
        book.price_amount = payload["price"]["amount"]
        book.price_currency = payload["price"]["currency"]

        book.price_vnd = (
            book.price_amount
            if book.price_currency == "VND"
            else None
        )

    if "stock" in payload:
        book.stock = payload["stock"]

    if "categoryId" in payload:
        category_id = parse_prefixed_id(
            payload["categoryId"],
            "category",
        )
        book.category_id = category_id

    if "publishedAt" in payload:
        book.published_at = date.fromisoformat(
            payload["publishedAt"]
        )

    if "authors" in payload:
        current_by_author_id = {
            link.author_id: link
            for link in book.author_links
            if link.author_id is not None
        }

        desired_author_ids = {
            author.id
            for author, _role in author_links
        }

        # Xóa relation không còn được client gửi lên.
        for existing_link in list(book.author_links):
            if (
                existing_link.author_id is not None
                and existing_link.author_id
                not in desired_author_ids
            ):
                book.author_links.remove(
                    existing_link
                )

        # Update relation cũ hoặc thêm relation mới.
        for author, role in author_links:
            existing_link = current_by_author_id.get(
                author.id
            )

            if existing_link is not None:
                existing_link.role = role
            else:
                book.author_links.append(
                    BookAuthor(
                        author=author,
                        role=role,
                    )
                )


def parse_limit() -> tuple[int | None, object | None]:
    """
    Lab 1 chỉ dùng pagination nhẹ:
    ?limit=N

    Default = 20
    Max = 100

    Pagination đầy đủ offset/cursor nằm ở Lab 2.
    """
    raw = request.args.get("limit")

    if raw is None:
        return 20, None

    try:
        limit = int(raw)
    except (TypeError, ValueError):
        return None, bad(
            "bad_limit",
            field=["limit"],
        )

    if limit < 1 or limit > 100:
        return None, bad(
            "bad_limit",
            field=["limit"],
        )

    return limit, None


# ============================================================
# SEED
# ============================================================

def seed_data():
    if (
        db.session.scalar(
            select(Book.id).limit(1)
        )
        is not None
    ):
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
    ]

    authors = [
        Author(
            id=1,
            name="Robert C. Martin",
            bio="Software author",
        ),
        Author(
            id=2,
            name="Martin Fowler",
            bio="Software architect",
        ),
        Author(
            id=3,
            name="Nguyen An",
            bio="Vietnamese writer",
        ),
    ]

    user = User(
        id=1,
        email="reader@example.com",
        display_name="Reader One",
        internal_note="DO NOT EXPOSE",
    )

    db.session.add_all(
        categories + authors + [user]
    )

    db.session.flush()

    book = Book(
        id=42,
        title="Clean Code",
        isbn="9780132350884",
        price_amount=450000,
        price_currency="VND",
        price_vnd=450000,
        stock=8,
        category_id=1,
        published_at=date(2008, 8, 1),
    )

    book.author_links.append(
        BookAuthor(
            author=authors[0],
            role="lead",
        )
    )

    book.reviews.append(
        Review(
            user=user,
            rating=5,
            comment="Excellent",
        )
    )

    second = Book(
        id=43,
        title="Refactoring",
        isbn="9780134757599",
        price_amount=520000,
        price_currency="VND",
        price_vnd=520000,
        stock=3,
        category_id=1,
    )

    second.author_links.append(
        BookAuthor(
            author=authors[1],
            role="lead",
        )
    )

    db.session.add_all([
        book,
        second,
    ])

    db.session.commit()


# ============================================================
# APPLICATION
# ============================================================

def create_app(
    test_config: dict | None = None,
) -> Flask:
    app = Flask(__name__)

    # Flask 3.x: cách đúng để giữ thứ tự dictionary JSON.
    app.json.sort_keys = False

    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///lab1.db",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    # --------------------------------------------------------
    # GET /books
    # --------------------------------------------------------

    @app.get("/api/v1/books")
    def list_books():
        limit, error = parse_limit()

        if error is not None:
            return error

        rows = db.session.scalars(
            select(Book)
            .options(
                selectinload(Book.category),
                selectinload(
                    Book.author_links
                ).selectinload(
                    BookAuthor.author
                ),
            )
            .order_by(Book.id)
            .limit(limit + 1)
        ).all()

        has_more = len(rows) > limit
        books = rows[:limit]

        return jsonify({
            "data": [
                book.to_dict()
                for book in books
            ],
            "pagination": {
                "limit": limit,
                "has_more": has_more,
            },
        })

    # --------------------------------------------------------
    # GET /books/{id}
    # --------------------------------------------------------

    @app.get("/api/v1/books/<book_ref>")
    def get_book(book_ref):
        book = load_book(book_ref)

        if not book:
            return bad(
                "not_found",
                404,
            )

        return jsonify(
            book.to_dict()
        )

    # --------------------------------------------------------
    # POST /books
    # --------------------------------------------------------

    @app.post("/api/v1/books")
    def create_book():
        payload = request.get_json(
            silent=True
        )

        try:
            validate(
                payload,
                BOOK_SCHEMA,
                format_checker=(
                    Draft202012Validator
                    .FORMAT_CHECKER
                ),
            )

        except ValidationError as e:
            return validation_error_response(e)

        links, error = ensure_references(
            payload
        )

        if error is not None:
            return error

        book = Book()

        apply_payload(
            book,
            payload,
            links,
        )

        db.session.add(book)

        try:
            db.session.commit()

        except IntegrityError:
            db.session.rollback()

            return bad(
                "isbn_conflict",
                409,
            )

        response = jsonify(
            book.to_dict()
        )

        response.status_code = 201

        response.headers["Location"] = url_for(
            "get_book",
            book_ref=f"book_{book.id}",
        )

        return response

    # --------------------------------------------------------
    # PATCH /books/{id}
    # --------------------------------------------------------

    @app.patch("/api/v1/books/<book_ref>")
    def update_book(book_ref):
        book = load_book(book_ref)

        if not book:
            return bad(
                "not_found",
                404,
            )

        payload = request.get_json(
            silent=True
        )

        partial_schema = {
            **BOOK_SCHEMA,
            "required": [],
        }

        try:
            validate(
                payload,
                partial_schema,
                format_checker=(
                    Draft202012Validator
                    .FORMAT_CHECKER
                ),
            )

        except ValidationError as e:
            return validation_error_response(e)

        if not payload:
            return bad(
                "empty_patch"
            )

        links, error = ensure_references(
            payload
        )

        if error is not None:
            return error

        apply_payload(
            book,
            payload,
            links,
        )

        try:
            db.session.commit()

        except IntegrityError:
            db.session.rollback()

            return bad(
                "isbn_conflict",
                409,
            )

        return jsonify(
            book.to_dict()
        )

    # --------------------------------------------------------
    # DELETE /books/{id}
    # --------------------------------------------------------

    @app.delete("/api/v1/books/<book_ref>")
    def delete_book(book_ref):
        book = load_book(book_ref)

        if not book:
            return bad(
                "not_found",
                404,
            )

        db.session.delete(book)
        db.session.commit()

        return "", 204

    # --------------------------------------------------------
    # GET /books/{id}/reviews
    # --------------------------------------------------------

    @app.get("/api/v1/books/<book_ref>/reviews")
    def book_reviews(book_ref):
        book = load_book(book_ref)

        if not book:
            return bad(
                "not_found",
                404,
            )

        return jsonify({
            "data": [
                review.to_dict()
                for review in book.reviews
            ]
        })

    # --------------------------------------------------------
    # GET /authors
    # --------------------------------------------------------

    @app.get("/api/v1/authors")
    def list_authors():
        authors = db.session.scalars(
            select(Author).order_by(
                Author.id
            )
        ).all()

        return jsonify({
            "data": [
                {
                    "id": f"author_{author.id}",
                    "name": author.name,
                }
                for author in authors
            ]
        })

    # --------------------------------------------------------
    # GET /categories
    # --------------------------------------------------------

    @app.get("/api/v1/categories")
    def list_categories():
        categories = db.session.scalars(
            select(Category).order_by(
                Category.id
            )
        ).all()

        return jsonify({
            "data": [
                {
                    "id": f"category_{cat.id}",
                    "name": cat.name,
                    "slug": cat.slug,
                }
                for cat in categories
            ]
        })

    with app.app_context():
        db.create_all()

        if app.config.get(
            "SEED_DATA",
            True,
        ):
            seed_data()

    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
    )