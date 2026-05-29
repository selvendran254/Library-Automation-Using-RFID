import pytest

from app import create_app
from config import Config
from models import db
from models.book import Book
from models.member import Member
from models.staff_user import StaffUser
from models.transaction import Transaction


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-secret-key"


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        admin = StaffUser(username="admin", full_name="Admin", role="admin")
        admin.set_password("admin123")
        book = Book(rfid_tag="BOOK-001", title="Test Book", author="Author", category="Fiction", total_qty=2, available_qty=2)
        member = Member(rfid_card="MEM-001", name="Test Member", email="t@test.com", phone="9876543210")
        db.session.add_all([admin, book, member])
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def auth_client(app):
    client = app.test_client()
    client.post("/auth/login", data={"username": "admin", "password": "admin123"})
    return client


def test_issue_and_return_book(auth_client, app):
    with app.app_context():
        book = Book.query.filter_by(rfid_tag="BOOK-001").first()
        member = Member.query.first()
        r = auth_client.post("/transactions/issue", data={
            "member_card": member.rfid_card,
            "book_tag": book.rfid_tag,
        }, follow_redirects=True)
        assert r.status_code == 200
        txn = Transaction.query.filter_by(return_date=None).first()
        assert txn is not None
        db.session.refresh(book)
        assert book.available_qty == 1

        r2 = auth_client.post("/transactions/return", data={"book_tag": book.rfid_tag}, follow_redirects=True)
        assert r2.status_code == 200
        db.session.refresh(book)
        assert book.available_qty == 2


def test_member_portal_rfid_login(app):
    client = app.test_client()
    r = client.post("/portal/login-rfid", data={"rfid_card": "MEM-001"}, follow_redirects=True)
    assert r.status_code == 200
    with client.session_transaction() as sess:
        assert sess.get("member_id") is not None
