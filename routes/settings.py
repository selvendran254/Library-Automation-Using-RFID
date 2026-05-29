from flask import Blueprint, flash, redirect, render_template, request, url_for

from models import db
from models.category import Category
from models.settings import LibrarySetting
from utils.helpers import log_activity, seed_default_categories, seed_default_settings

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")

SETTING_GROUPS = [
    {
        "id": "borrowing",
        "title": "Borrowing & Fines",
        "icon": "bi-journal-bookmark",
        "accent": "blue",
        "description": "Loan period, fines, renewals, and reservations",
        "keys": [
            "loan_period_days",
            "fine_per_day",
            "max_renewals",
            "renewal_days",
            "reservation_hold_days",
        ],
    },
    {
        "id": "membership",
        "title": "Membership Limits",
        "icon": "bi-people",
        "accent": "purple",
        "description": "How many books each member type can borrow",
        "keys": [
            "max_books_default",
            "max_books_standard",
            "max_books_premium",
            "max_books_student",
        ],
    },
    {
        "id": "notifications",
        "title": "SMS Alerts",
        "icon": "bi-bell",
        "accent": "green",
        "description": "Automatic reminders sent to member phones",
        "keys": ["sms_enabled", "sms_provider", "fast2sms_api_key", "msg91_auth_key", "sms_due_reminder_days"],
    },
    {
        "id": "portal",
        "title": "Member Portal",
        "icon": "bi-person-lines-fill",
        "accent": "teal",
        "description": "Shareable login links for members",
        "keys": ["portal_token_ttl_days"],
    },
    {
        "id": "inventory",
        "title": "Inventory",
        "icon": "bi-box-seam",
        "accent": "orange",
        "description": "Stock alerts and catalog rules",
        "keys": ["low_stock_threshold"],
    },
    {
        "id": "rfid",
        "title": "RFID Hardware",
        "icon": "bi-rfid",
        "accent": "red",
        "description": "Reader mode, serial port, and tag formatting",
        "keys": [
            "rfid_mode",
            "rfid_serial_port",
            "rfid_baud_rate",
            "rfid_tag_prefix",
            "rfid_tag_suffix",
            "rfid_usb_keyword",
        ],
    },
]

SETTING_ICONS = {
    "loan_period_days": "bi-calendar3",
    "fine_per_day": "bi-currency-rupee",
    "max_renewals": "bi-arrow-repeat",
    "renewal_days": "bi-calendar-plus",
    "reservation_hold_days": "bi-bookmark-star",
    "max_books_default": "bi-bookshelf",
    "max_books_standard": "bi-person",
    "max_books_premium": "bi-star",
    "max_books_student": "bi-mortarboard",
    "sms_enabled": "bi-phone",
    "sms_provider": "bi-send",
    "fast2sms_api_key": "bi-key",
    "msg91_auth_key": "bi-key-fill",
    "sms_due_reminder_days": "bi-alarm",
    "portal_token_ttl_days": "bi-link-45deg",
    "low_stock_threshold": "bi-exclamation-triangle",
    "rfid_mode": "bi-usb-plug",
    "rfid_serial_port": "bi-hdd",
    "rfid_baud_rate": "bi-speedometer2",
    "rfid_tag_prefix": "bi-scissors",
    "rfid_tag_suffix": "bi-scissors",
    "rfid_usb_keyword": "bi-search",
}

INPUT_META = {
    "loan_period_days": {"type": "number", "min": 1, "max": 90, "suffix": "days"},
    "fine_per_day": {"type": "number", "min": 0, "step": 0.5, "prefix": "₹"},
    "max_renewals": {"type": "number", "min": 0, "max": 10},
    "renewal_days": {"type": "number", "min": 1, "max": 30, "suffix": "days"},
    "reservation_hold_days": {"type": "number", "min": 1, "max": 14, "suffix": "days"},
    "max_books_default": {"type": "number", "min": 1, "max": 20, "suffix": "books"},
    "max_books_standard": {"type": "number", "min": 1, "max": 20, "suffix": "books"},
    "max_books_premium": {"type": "number", "min": 1, "max": 20, "suffix": "books"},
    "max_books_student": {"type": "number", "min": 1, "max": 20, "suffix": "books"},
    "low_stock_threshold": {"type": "number", "min": 0, "max": 50, "suffix": "copies"},
    "sms_due_reminder_days": {"type": "number", "min": 0, "max": 14, "suffix": "days before"},
    "sms_provider": {
        "type": "select",
        "options": [
            ("fast2sms", "Fast2SMS — real OTP to phone"),
            ("msg91", "MSG91"),
            ("twilio", "Twilio"),
            ("simulated", "Simulated (dev only, no SMS)"),
        ],
    },
    "fast2sms_api_key": {"type": "password", "placeholder": "Paste Fast2SMS API key"},
    "msg91_auth_key": {"type": "password", "placeholder": "Paste MSG91 auth key"},
    "portal_token_ttl_days": {"type": "number", "min": 1, "max": 365, "suffix": "days"},
    "rfid_baud_rate": {"type": "number", "min": 9600, "max": 115200, "step": 9600},
    "sms_enabled": {"type": "toggle"},
    "rfid_mode": {
        "type": "select",
        "options": [
            ("hid", "HID Keyboard Wedge"),
            ("serial", "Serial USB Reader"),
        ],
    },
}


def _group_settings(settings_list):
    by_key = {s.key: s for s in settings_list}
    groups = []
    used = set()
    for group in SETTING_GROUPS:
        items = [by_key[key] for key in group["keys"] if key in by_key]
        if not items:
            continue
        used.update(group["keys"])
        groups.append({**group, "settings": items})
    other = [s for s in settings_list if s.key not in used]
    if other:
        groups.append(
            {
                "id": "other",
                "title": "Other",
                "icon": "bi-sliders",
                "description": "Additional configuration",
                "settings": other,
            }
        )
    return groups


@settings_bp.route("/")
def settings_home():
    settings = LibrarySetting.query.order_by(LibrarySetting.id).all()
    categories = Category.query.order_by(Category.name).all()
    settings_map = {s.key: s.value for s in settings}
    return render_template(
        "settings/index.html",
        settings=settings,
        settings_map=settings_map,
        setting_groups=_group_settings(settings),
        input_meta=INPUT_META,
        setting_icons=SETTING_ICONS,
        categories=categories,
        category_count=len(categories),
    )


@settings_bp.route("/update", methods=["POST"])
def update_settings():
    for setting in LibrarySetting.query.all():
        new_val = request.form.get(setting.key)
        if new_val is not None:
            setting.value = new_val.strip()
    db.session.commit()
    log_activity("UPDATE", "Settings", None, "Library settings updated")
    flash("Settings saved successfully.", "success")
    return redirect(url_for("settings.settings_home"))


@settings_bp.route("/categories/add", methods=["POST"])
def add_category():
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    shelf = request.form.get("shelf_section", "").strip()
    if Category.query.filter_by(name=name).first():
        flash("Category already exists.", "danger")
    else:
        cat = Category(name=name, description=description, shelf_section=shelf)
        db.session.add(cat)
        db.session.commit()
        log_activity("CREATE", "Category", cat.id, f"Category '{name}' added")
        flash(f"Category '{name}' added.", "success")
    return redirect(url_for("settings.settings_home"))


@settings_bp.route("/categories/edit/<int:cat_id>", methods=["POST"])
def edit_category(cat_id):
    cat = Category.query.get_or_404(cat_id)
    cat.name = request.form.get("name", cat.name).strip()
    cat.description = request.form.get("description", "").strip()
    cat.shelf_section = request.form.get("shelf_section", "").strip()
    db.session.commit()
    flash("Category updated.", "success")
    return redirect(url_for("settings.settings_home"))


@settings_bp.route("/categories/delete/<int:cat_id>", methods=["POST"])
def delete_category(cat_id):
    cat = Category.query.get_or_404(cat_id)
    db.session.delete(cat)
    db.session.commit()
    flash("Category deleted.", "success")
    return redirect(url_for("settings.settings_home"))


@settings_bp.route("/init-defaults", methods=["POST"])
def init_defaults():
    seed_default_settings()
    seed_default_categories()
    flash("Default settings and categories loaded.", "success")
    return redirect(url_for("settings.settings_home"))
