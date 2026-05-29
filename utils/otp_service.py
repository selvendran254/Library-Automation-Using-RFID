import random
import re
from datetime import timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from flask import current_app

from models import db
from models.sms_log import SmsLog
from utils.helpers import log_activity, utcnow_naive
from utils.sms_service import _dispatch_sms, _format_phone, is_sms_enabled


OTP_EXPIRY_MINUTES = 5
OTP_LENGTH = 6


def normalize_phone(phone):
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if len(digits) == 10:
        return digits
    if len(digits) == 12 and digits.startswith("91"):
        return digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        return digits[1:]
    return digits


def normalize_otp_code(raw):
    digits = re.sub(r"\D", "", raw or "")
    if not digits:
        return ""
    if len(digits) > 6:
        digits = digits[-6:]
    return digits.zfill(6)


def phones_match(stored, entered):
    return normalize_phone(stored) == normalize_phone(entered)


def staff_login_candidates(raw):
    """Turn free-form login input into values to try (phone and/or username)."""
    raw = (raw or "").strip()
    if not raw:
        return []

    candidates = []
    for part in re.split(r"\s+or\s+", raw, flags=re.IGNORECASE):
        part = part.strip().strip(",.")
        if part:
            candidates.append(part)

    phone = normalize_phone(raw)
    if len(phone) == 10 and phone not in {normalize_phone(c) for c in candidates}:
        candidates.insert(0, phone)

    seen = set()
    ordered = []
    for candidate in candidates:
        key = candidate.lower()
        if key not in seen:
            seen.add(key)
            ordered.append(candidate)
    return ordered


def find_staff_for_login(login_id):
    from models.staff_user import StaffUser

    for candidate in staff_login_candidates(login_id):
        phone_norm = normalize_phone(candidate)
        if len(phone_norm) == 10:
            active_staff = StaffUser.query.filter(
                StaffUser.is_active.is_(True),
                StaffUser.phone.isnot(None),
            ).all()
            staff = next((s for s in active_staff if phones_match(s.phone, candidate)), None)
            if staff:
                return staff, staff.phone

        username = candidate.strip().lower()
        if re.fullmatch(r"[a-z0-9_-]+", username):
            staff = StaffUser.query.filter_by(username=username, is_active=True).first()
            if staff and staff.phone:
                return staff, staff.phone

    return None, None


def generate_otp_code():
    try:
        if current_app.config.get("TESTING"):
            return "123456"
    except RuntimeError:
        pass
    return str(random.randint(100000, 999999))


def create_otp(phone, purpose, user_type, user_id):
    from models.login_otp import LoginOtp

    phone_norm = normalize_phone(phone)
    LoginOtp.query.filter_by(phone=phone_norm, purpose=purpose, is_used=False).update({"is_used": True})
    code = generate_otp_code()
    otp = LoginOtp(
        phone=phone_norm,
        purpose=purpose,
        user_type=user_type,
        user_id=user_id,
        otp_hash=generate_password_hash(code),
        expires_at=utcnow_naive() + timedelta(minutes=OTP_EXPIRY_MINUTES),
    )
    db.session.add(otp)
    db.session.flush()
    return otp, code


def send_otp_sms(phone, code, purpose_label="login"):
    from utils.sms_service import _dispatch_otp_sms

    formatted = _format_phone(normalize_phone(phone))
    message = f"Library RFID: Your {purpose_label} OTP is {code}. Valid for {OTP_EXPIRY_MINUTES} minutes. Do not share."
    ok, provider = _dispatch_otp_sms(formatted, code, message)
    sms = SmsLog(
        phone=formatted,
        message_type="OTP",
        message=message,
        status="Sent" if ok else f"Failed ({provider})",
    )
    db.session.add(sms)
    log_activity("OTP", "Phone", 0, f"OTP sent to {formatted} ({purpose_label})")
    return ok, message if not ok else None


def issue_otp(phone, purpose, user_type, user_id, purpose_label="login"):
    testing = current_app.config.get("TESTING")
    if not is_sms_enabled() and not testing:
        return None, None, "SMS is disabled. Enable SMS in library settings."
    otp, code = create_otp(phone, purpose, user_type, user_id)
    if not testing:
        ok, err = send_otp_sms(phone, code, purpose_label)
        if not ok:
            db.session.rollback()
            return None, None, err or "Could not send OTP to your phone. Check Fast2SMS API key in Settings."
    db.session.commit()
    return otp, code, None


def verify_otp(phone, purpose, code):
    from models.login_otp import LoginOtp

    phone_norm = normalize_phone(phone)
    otp = (
        LoginOtp.query.filter_by(phone=phone_norm, purpose=purpose, is_used=False)
        .order_by(LoginOtp.created_at.desc())
        .first()
    )
    if not otp:
        return None, "No OTP found. Please request a new one."
    if otp.expires_at < utcnow_naive():
        return None, "OTP expired. Please request a new one."
    if otp.attempts >= 5:
        return None, "Too many attempts. Request a new OTP."

    code_norm = normalize_otp_code(code)
    if len(code_norm) != 6:
        return None, "Please enter the 6-digit OTP from your SMS."

    if not check_password_hash(otp.otp_hash, code_norm):
        otp.attempts += 1
        db.session.commit()
        return None, "Invalid OTP. Please try again."
    otp.is_used = True
    otp.verified_at = utcnow_naive()
    db.session.commit()
    return otp, None
