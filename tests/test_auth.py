import pytest

from app import create_app
from config import Config
from models import db
from models.member import Member
from models.staff_user import StaffUser


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
        if not StaffUser.query.filter_by(username="admin").first():
            admin = StaffUser(username="admin", full_name="Test Admin", phone="9876543210", role="admin")
            admin.set_password("admin123")
            db.session.add(admin)
        member = Member(rfid_card="MEM-001", name="Test Member", email="t@test.com", phone="9876543211")
        db.session.add(member)
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_staff_login_required(client):
    r = client.get("/")
    assert r.status_code == 302
    assert "/auth/login" in r.location


def test_staff_password_login(client, app):
    r = client.post("/auth/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)
    assert r.status_code == 200
    assert client.get("/").status_code == 200


def test_staff_password_login_wrong(client, app):
    r = client.post("/auth/login", data={"username": "admin", "password": "wrongpass"}, follow_redirects=True)
    assert b"Invalid username or password" in r.data


def test_member_otp_login(client, app):
    with app.app_context():
        phone = Member.query.first().phone
    client.post("/portal/send-otp", data={"phone": phone}, follow_redirects=True)
    r = client.post("/portal/verify-otp", data={"otp": "123456"}, follow_redirects=True)
    assert r.status_code == 200


def test_portal_login_page_public(client):
    r = client.get("/portal/login")
    assert r.status_code == 200
