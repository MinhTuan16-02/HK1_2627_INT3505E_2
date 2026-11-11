import pytest

from app import create_app
from models import Book, db


@pytest.fixture
def app():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def sample_book(app):
    with app.app_context():
        book = Book(title="API Design Patterns", author="J.J. Geewax", year=2021)
        db.session.add(book)
        db.session.commit()
        bid = book.id
    yield bid
