from datetime import datetime, timedelta, timezone

from models import db
from models.activity_log import ActivityLog
from models.settings import LibrarySetting


def utcnow_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def log_activity(action, entity_type, entity_id, description, user_label=None):
    if user_label is None:
        try:
            from flask import g

            if getattr(g, "staff_user", None):
                user_label = g.staff_user.full_name
            elif getattr(g, "member", None):
                user_label = g.member.name
            else:
                user_label = "Admin"
        except RuntimeError:
            user_label = "Admin"
    db.session.add(
        ActivityLog(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
            user_label=user_label,
        )
    )


def get_loan_days():
    return LibrarySetting.get_int("loan_period_days", 14)


def get_fine_per_day():
    return LibrarySetting.get_float("fine_per_day", 2.0)


def get_max_books(member):
    defaults = {"Standard": 3, "Premium": 5, "Student": 2}
    base = LibrarySetting.get_int("max_books_default", 3)
    type_limit = LibrarySetting.get_int(
        f"max_books_{member.membership_type.lower()}",
        defaults.get(member.membership_type, base),
    )
    if member.max_books_override:
        return member.max_books_override
    return type_limit


def get_max_renewals():
    return LibrarySetting.get_int("max_renewals", 2)


def get_renewal_days():
    return LibrarySetting.get_int("renewal_days", 7)


def get_low_stock_threshold():
    return LibrarySetting.get_int("low_stock_threshold", 1)


def get_reservation_hold_days():
    return LibrarySetting.get_int("reservation_hold_days", 3)


def get_portal_token_ttl_days():
    return LibrarySetting.get_int("portal_token_ttl_days", 30)


def generate_portal_token(member):
    import secrets

    ttl = get_portal_token_ttl_days()
    member.portal_token = secrets.token_urlsafe(32)
    member.portal_token_expires = utcnow_naive() + timedelta(days=ttl)
    db.session.commit()
    return member.portal_token


def portal_token_valid(member):
    if not member.portal_token or not member.portal_token_expires:
        return False
    return member.portal_token_expires >= utcnow_naive()


def revoke_portal_token(member):
    member.portal_token = None
    member.portal_token_expires = None
    db.session.commit()


def member_active_issues(member):
    return member.transactions.filter_by(return_date=None).count()


def can_member_borrow(member):
    if member.status != "Active":
        return False, "Member is not active."
    if member.pending_fine > 0:
        return False, f"Pending fine of ₹{member.pending_fine:.0f} must be cleared first."
    if member.expiry_date and member.expiry_date < utcnow_naive().date():
        return False, "Membership has expired. Please renew."
    active = member_active_issues(member)
    if active >= get_max_books(member):
        return False, f"Member already has {active} books (limit: {get_max_books(member)})."
    return True, "OK"


def seed_default_settings():
    defaults = [
        ("loan_period_days", "14", "Loan Period (Days)", "Days before book is due"),
        ("fine_per_day", "2", "Fine Per Day (₹)", "Daily fine after due date"),
        ("max_books_default", "3", "Max Books (Default)", "Default borrow limit"),
        ("max_books_standard", "3", "Max Books (Standard)", "Standard member limit"),
        ("max_books_premium", "5", "Max Books (Premium)", "Premium member limit"),
        ("max_books_student", "2", "Max Books (Student)", "Student member limit"),
        ("max_renewals", "2", "Max Renewals", "Times a book can be renewed"),
        ("renewal_days", "7", "Renewal Extension (Days)", "Days added on renewal"),
        ("reservation_hold_days", "3", "Reservation Hold (Days)", "Days to hold reserved book"),
        ("low_stock_threshold", "1", "Low Stock Alert", "Alert when available <= this"),
        ("sms_enabled", "1", "SMS Alerts Enabled", "1=On, 0=Off"),
        ("sms_provider", "fast2sms", "SMS Provider", "fast2sms = real OTP to phone"),
        ("fast2sms_api_key", "", "Fast2SMS API Key", "Get from fast2sms.com → Dev API"),
        ("msg91_auth_key", "", "MSG91 Auth Key", "Optional — if using MSG91 instead"),
        ("sms_due_reminder_days", "2", "Due Reminder (Days Before)", "Send SMS this many days before due date"),
        ("rfid_mode", "hid", "RFID Mode", "hid | serial (real hardware only)"),
        ("rfid_serial_port", "/dev/ttyUSB0", "RFID Serial Port", "e.g. /dev/ttyUSB0 or COM3"),
        ("rfid_baud_rate", "9600", "RFID Baud Rate", "Serial baud rate (usually 9600)"),
        ("rfid_tag_prefix", "", "RFID Tag Prefix Strip", "Remove prefix from scanned tag"),
        ("rfid_tag_suffix", "", "RFID Tag Suffix Strip", "Remove suffix e.g. \\r\\n"),
        ("rfid_usb_keyword", "", "USB Device Keyword", "Match reader name in lsusb e.g. 1a86 or RFID"),
        ("portal_token_ttl_days", "30", "Portal Link Valid (Days)", "Days before member portal link expires"),
    ]
    for key, value, label, desc in defaults:
        if not LibrarySetting.query.filter_by(key=key).first():
            db.session.add(
                LibrarySetting(key=key, value=value, label=label, description=desc)
            )
    db.session.commit()


def seed_default_categories():
    from models.category import Category

    categories = [
        ("Fiction", "Novels and stories", "A1"),
        ("Non-Fiction", "Biographies, history", "A2"),
        ("Technology", "Programming, IT books", "B1"),
        ("Fantasy", "Fantasy and sci-fi", "A3"),
        ("Self-Help", "Personal development", "C1"),
        ("Romance", "Romance novels", "A4"),
        ("Dystopian", "Dystopian fiction", "A5"),
    ]
    for name, desc, shelf in categories:
        if not Category.query.filter_by(name=name).first():
            db.session.add(Category(name=name, description=desc, shelf_section=shelf))
    db.session.commit()
