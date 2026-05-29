import csv
import io
from datetime import datetime, timezone

from sqlalchemy import inspect, text

from models import db


def upgrade_database():
    """Add new columns/tables for existing databases."""
    db.create_all()
    inspector = inspect(db.engine)
    existing = {t: {c["name"] for c in inspector.get_columns(t)} for t in inspector.get_table_names()}

    book_cols = {
        "isbn": "VARCHAR(20)",
        "publisher": "VARCHAR(150)",
        "shelf_location": "VARCHAR(50)",
        "description": "TEXT",
    }
    member_cols = {
        "address": "VARCHAR(300)",
        "expiry_date": "DATE",
        "max_books_override": "INTEGER",
        "notes": "TEXT",
        "portal_token": "VARCHAR(64)",
        "portal_token_expires": "TIMESTAMP",
        "portal_last_login": "TIMESTAMP",
    }
    staff_cols = {
        "phone": "VARCHAR(20)",
    }
    txn_cols = {
        "renewal_count": "INTEGER DEFAULT 0",
        "receipt_no": "VARCHAR(30)",
        "notes": "VARCHAR(255)",
    }
    book_status_col = {"book_status": "VARCHAR(20) DEFAULT 'Active'"}

    def add_cols(table, cols):
        if table not in existing:
            return
        for col, col_type in cols.items():
            if col not in existing[table]:
                db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
        db.session.commit()

    add_cols("books", book_cols)
    add_cols("books", book_status_col)
    add_cols("members", member_cols)
    add_cols("staff_users", staff_cols)
    add_cols("transactions", txn_cols)
    damage_report_cols = {
        "member_message": "TEXT",
        "member_message_at": "TIMESTAMP",
        "member_message_read": "BOOLEAN DEFAULT FALSE",
    }
    add_cols("book_damage_reports", damage_report_cols)

    if "sms_logs" in existing:
        db.session.execute(text("ALTER TABLE sms_logs ALTER COLUMN member_id DROP NOT NULL"))
        db.session.commit()

    from utils.portal_chat import migrate_legacy_portal_messages

    migrate_legacy_portal_messages()
    seed_default_staff()

    if "library_settings" in existing:
        db.session.execute(
            text(
                "UPDATE library_settings SET value = 'hid' "
                "WHERE key = 'rfid_mode' AND value = 'simulation'"
            )
        )
        db.session.commit()


def export_csv(headers, rows, filename):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    output.seek(0)
    return output.getvalue(), filename


def seed_default_staff():
    from flask import current_app

    from models.staff_user import StaffUser
    from utils.otp_service import normalize_phone

    default_phone = normalize_phone(current_app.config.get("DEFAULT_ADMIN_PHONE", "9876543210"))

    if StaffUser.query.first():
        admin = StaffUser.query.filter_by(username=current_app.config.get("DEFAULT_ADMIN_USERNAME", "admin")).first()
        if admin and not admin.phone and len(default_phone) == 10:
            admin.phone = default_phone
            db.session.commit()
        return
    admin = StaffUser(
        username=current_app.config.get("DEFAULT_ADMIN_USERNAME", "admin"),
        full_name=current_app.config.get("DEFAULT_ADMIN_NAME", "Library Admin"),
        phone=current_app.config.get("DEFAULT_ADMIN_PHONE", "9876543210"),
        role="admin",
    )
    admin.set_password(current_app.config.get("DEFAULT_ADMIN_PASSWORD", "admin123"))
    db.session.add(admin)
    db.session.commit()

