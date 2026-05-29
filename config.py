import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/library_rfid",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    LOAN_PERIOD_DAYS = 14
    FINE_PER_DAY = 2

    # Session
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 86400 * 7

    # Production
    DEBUG = os.environ.get("FLASK_DEBUG", "1") == "1"
    WTF_CSRF_TIME_LIMIT = None

    # RFID Hardware — hid | serial (real USB reader only)
    RFID_MODE = os.environ.get("RFID_MODE", "hid")
    RFID_SERIAL_PORT = os.environ.get("RFID_SERIAL_PORT", "/dev/ttyUSB0")
    RFID_BAUD_RATE = int(os.environ.get("RFID_BAUD_RATE", "9600"))

    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "uploads", "damage_reports")
    MAX_CONTENT_LENGTH = 6 * 1024 * 1024

    # SMS gateway: simulated | twilio | msg91
    SMS_PROVIDER = os.environ.get("SMS_PROVIDER", "fast2sms")
    TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
    TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "")
    MSG91_AUTH_KEY = os.environ.get("MSG91_AUTH_KEY", "")
    MSG91_SENDER_ID = os.environ.get("MSG91_SENDER_ID", "LIBRFID")
    MSG91_ROUTE = os.environ.get("MSG91_ROUTE", "4")
    FAST2SMS_API_KEY = os.environ.get("FAST2SMS_API_KEY", "")

    # Email (optional)
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    EMAIL_FROM = os.environ.get("EMAIL_FROM", "")

    # Default staff (seeded on first run if no users)
    DEFAULT_ADMIN_USERNAME = os.environ.get("DEFAULT_ADMIN_USERNAME", "admin")
    DEFAULT_ADMIN_PASSWORD = os.environ.get("DEFAULT_ADMIN_PASSWORD", "admin123")
    DEFAULT_ADMIN_NAME = os.environ.get("DEFAULT_ADMIN_NAME", "Library Admin")
    DEFAULT_ADMIN_PHONE = os.environ.get("DEFAULT_ADMIN_PHONE", "9876543210")

