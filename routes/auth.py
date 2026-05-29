from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from models import db
from models.staff_user import StaffUser
from utils.auth import admin_role_required, get_current_staff, login_staff, logout_staff, staff_login_required
from utils.helpers import log_activity, utcnow_naive
from utils.database import seed_default_staff
from utils.otp_service import normalize_phone, phones_match

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if get_current_staff():
        return redirect(url_for("dashboard"))

    seed_default_staff()

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Please enter username and password.", "danger")
            return render_template("auth/login.html")

        staff = StaffUser.query.filter_by(username=username).first()
        if not staff or not staff.is_active or not staff.check_password(password):
            flash("Invalid username or password.", "danger")
            return render_template("auth/login.html")

        login_staff(staff)
        staff.last_login = utcnow_naive()
        db.session.commit()
        log_activity("LOGIN", "StaffUser", staff.id, f"Staff login '{staff.username}'", user_label=staff.full_name)
        flash(f"Welcome, {staff.full_name}!", "success")

        next_url = request.args.get("next")
        if next_url and next_url.startswith("/") and not next_url.startswith("//"):
            return redirect(next_url)
        return redirect(url_for("dashboard"))

    return render_template("auth/login.html")


@auth_bp.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    flash("Staff login uses username and password.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/staff/create", methods=["GET", "POST"])
@admin_role_required
def create_staff():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        full_name = request.form.get("full_name", "").strip()
        phone = normalize_phone(request.form.get("phone", "").strip())
        role = request.form.get("role", "librarian")
        password = request.form.get("password", "").strip() or "staff123"

        if not username or not full_name or len(phone) != 10:
            flash("Username, full name, and valid 10-digit phone are required.", "danger")
            return render_template("auth/create_staff.html")

        if StaffUser.query.filter_by(username=username).first():
            flash("Username already exists.", "danger")
            return render_template("auth/create_staff.html")

        existing_phone = StaffUser.query.filter(StaffUser.phone.isnot(None)).all()
        if any(phones_match(s.phone, phone) for s in existing_phone):
            flash("Phone number already used by another staff account.", "danger")
            return render_template("auth/create_staff.html")

        staff = StaffUser(username=username, full_name=full_name, phone=phone, role=role)
        staff.set_password(password)
        db.session.add(staff)
        db.session.commit()
        log_activity("CREATE", "StaffUser", staff.id, f"Staff account created for {full_name}")
        flash(f"Staff account created for {full_name}. Login: {username} / {password}", "success")
        return redirect(url_for("auth.create_staff"))

    staff_list = StaffUser.query.order_by(StaffUser.full_name).all()
    return render_template("auth/create_staff.html", staff_list=staff_list)


@auth_bp.route("/logout", methods=["POST"])
@staff_login_required
def logout():
    staff = g.staff_user
    log_activity("LOGOUT", "StaffUser", staff.id, f"Staff '{staff.username}' logged out", user_label=staff.full_name)
    logout_staff()
    flash("Logged out successfully.", "info")
    return redirect(url_for("auth.login"))
