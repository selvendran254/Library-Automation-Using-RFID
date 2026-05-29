from functools import wraps

from flask import flash, g, redirect, request, session, url_for

from models.staff_user import StaffUser

STAFF_SESSION_KEY = "staff_user_id"

STAFF_PUBLIC_ENDPOINTS = {
    "auth.login",
    "static",
}

STAFF_PUBLIC_PATH_PREFIXES = (
    "/auth/login",
    "/auth/verify-otp",
    "/static/",
    "/portal/login",
    "/portal/access/",
    "/portal/verify-otp",
    "/portal/send-otp",
)


def is_member_portal_path(path):
    if not path.startswith("/portal"):
        return False
    if path.startswith("/portal/admin"):
        return False
    return True


def staff_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get(STAFF_SESSION_KEY):
            flash("Please login to continue.", "warning")
            return redirect(url_for("auth.login", next=request.url))
        staff = StaffUser.query.get(session[STAFF_SESSION_KEY])
        if not staff or not staff.is_active:
            session.pop(STAFF_SESSION_KEY, None)
            flash("Session expired. Please login again.", "danger")
            return redirect(url_for("auth.login"))
        g.staff_user = staff
        return view(*args, **kwargs)

    return wrapped


def admin_role_required(view):
    @wraps(view)
    @staff_login_required
    def wrapped(*args, **kwargs):
        if not g.staff_user.is_admin:
            flash("Admin access required.", "danger")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)

    return wrapped


def get_current_staff():
    staff_id = session.get(STAFF_SESSION_KEY)
    if not staff_id:
        return None
    return StaffUser.query.get(staff_id)


def login_staff(staff):
    session[STAFF_SESSION_KEY] = staff.id
    session.permanent = True


def logout_staff():
    session.pop(STAFF_SESSION_KEY, None)


def path_is_staff_public(path):
    return any(path.startswith(prefix) for prefix in STAFF_PUBLIC_PATH_PREFIXES)


def should_require_staff_login():
    if request.method == "OPTIONS":
        return False
    if is_member_portal_path(request.path):
        return False
    if path_is_staff_public(request.path):
        return False
    endpoint = request.endpoint or ""
    if endpoint in STAFF_PUBLIC_ENDPOINTS:
        return False
    if endpoint.startswith("member_portal.") and not endpoint.startswith("member_portal.admin"):
        return False
    return True
