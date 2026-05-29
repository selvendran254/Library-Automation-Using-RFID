"""SMS notification service — simulated, Twilio, or MSG91 delivery."""

import os

import requests

from flask import current_app

from models import db
from models.settings import LibrarySetting
from models.sms_log import SmsLog
from utils.helpers import get_fine_per_day, log_activity, utcnow_naive


def is_sms_enabled():
    return LibrarySetting.get("sms_enabled", "1") == "1"


def get_sms_provider():
    return LibrarySetting.get("sms_provider", current_app.config.get("SMS_PROVIDER", "fast2sms"))


def _get_fast2sms_api_key():
    return (
        LibrarySetting.get("fast2sms_api_key", "")
        or current_app.config.get("FAST2SMS_API_KEY")
        or os.environ.get("FAST2SMS_API_KEY", "")
    )


def _get_msg91_auth_key():
    return (
        LibrarySetting.get("msg91_auth_key", "")
        or current_app.config.get("MSG91_AUTH_KEY")
        or os.environ.get("MSG91_AUTH_KEY", "")
    )


def get_due_reminder_days():
    return LibrarySetting.get_int("sms_due_reminder_days", 2)


def _format_phone(phone):
    phone = (phone or "").strip()
    if len(phone) == 10:
        return f"+91{phone}"
    if phone.startswith("+"):
        return phone
    if phone.startswith("91") and len(phone) == 12:
        return f"+{phone}"
    return phone


def _dispatch_sms(phone, message):
    provider = get_sms_provider()
    if provider == "simulated":
        return True, "Simulated"

    if provider == "fast2sms":
        return _send_fast2sms_text(phone, message)

    if provider == "twilio":
        sid = current_app.config.get("TWILIO_ACCOUNT_SID") or os.environ.get("TWILIO_ACCOUNT_SID")
        token = current_app.config.get("TWILIO_AUTH_TOKEN") or os.environ.get("TWILIO_AUTH_TOKEN")
        from_num = current_app.config.get("TWILIO_FROM_NUMBER") or os.environ.get("TWILIO_FROM_NUMBER")
        if not all([sid, token, from_num]):
            return False, "Twilio not configured"
        try:
            resp = requests.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                auth=(sid, token),
                data={"To": phone, "From": from_num, "Body": message},
                timeout=15,
            )
            if resp.ok:
                return True, "Twilio"
            return False, resp.text[:200]
        except Exception as exc:
            return False, str(exc)

    if provider == "msg91":
        auth_key = _get_msg91_auth_key()
        sender = current_app.config.get("MSG91_SENDER_ID", "LIBRFID")
        route = current_app.config.get("MSG91_ROUTE", "4")
        if not auth_key:
            return False, "MSG91 not configured"
        mobile = phone.lstrip("+")
        if mobile.startswith("91"):
            mobile = mobile[2:]
        try:
            resp = requests.post(
                "https://api.msg91.com/api/sendhttp.php",
                params={
                    "authkey": auth_key,
                    "mobiles": mobile,
                    "message": message,
                    "sender": sender,
                    "route": route,
                    "country": "91",
                },
                timeout=15,
            )
            if resp.ok and resp.text.strip().isdigit():
                return True, "MSG91"
            return False, resp.text[:200]
        except Exception as exc:
            return False, str(exc)

    return True, "Simulated"


def _mobile_digits(phone):
    mobile = (phone or "").lstrip("+")
    if mobile.startswith("91") and len(mobile) > 10:
        mobile = mobile[2:]
    return mobile


def _send_fast2sms_text(phone, message):
    api_key = _get_fast2sms_api_key()
    if not api_key:
        return False, "Fast2SMS not configured"
    mobile = _mobile_digits(phone)
    try:
        resp = requests.post(
            "https://www.fast2sms.com/dev/bulkV2",
            headers={"authorization": api_key, "Content-Type": "application/json"},
            json={
                "route": "q",
                "message": message,
                "language": "english",
                "numbers": mobile,
            },
            timeout=15,
        )
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if resp.ok and data.get("return") is True:
            return True, "Fast2SMS"
        return False, (data.get("message") or resp.text)[:200]
    except Exception as exc:
        return False, str(exc)


def _send_fast2sms_otp(phone, code):
    api_key = _get_fast2sms_api_key()
    if not api_key:
        return False, "Fast2SMS not configured"
    mobile = _mobile_digits(phone)
    try:
        resp = requests.post(
            "https://www.fast2sms.com/dev/bulkV2",
            headers={"authorization": api_key, "Content-Type": "application/json"},
            json={
                "route": "otp",
                "variables_values": code,
                "numbers": mobile,
            },
            timeout=15,
        )
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if resp.ok and data.get("return") is True:
            return True, "Fast2SMS OTP"
        return False, (data.get("message") or resp.text)[:200]
    except Exception as exc:
        return False, str(exc)


def _dispatch_otp_sms(phone, code, message):
    provider = get_sms_provider()
    if provider == "simulated":
        return True, "Simulated"
    if provider == "fast2sms":
        return _send_fast2sms_otp(phone, code)
    if provider == "msg91":
        auth_key = _get_msg91_auth_key()
        sender = current_app.config.get("MSG91_SENDER_ID", "LIBRFID")
        route = current_app.config.get("MSG91_ROUTE", "4")
        if not auth_key:
            return False, "MSG91 not configured"
        mobile = _mobile_digits(phone)
        try:
            resp = requests.post(
                "https://api.msg91.com/api/sendhttp.php",
                params={
                    "authkey": auth_key,
                    "mobiles": mobile,
                    "message": message,
                    "sender": sender,
                    "route": route,
                    "country": "91",
                },
                timeout=15,
            )
            if resp.ok and resp.text.strip().isdigit():
                return True, "MSG91"
            return False, resp.text[:200]
        except Exception as exc:
            return False, str(exc)
    return _dispatch_sms(phone, message)


def _already_sent_today(member_id, transaction_id, message_type):
    today = utcnow_naive().date()
    existing = SmsLog.query.filter(
        SmsLog.member_id == member_id,
        SmsLog.transaction_id == transaction_id,
        SmsLog.message_type == message_type,
        db.func.date(SmsLog.sent_at) == today,
    ).first()
    return existing is not None


def send_sms(member, message, message_type, transaction_id=None, force=False):
    if not is_sms_enabled():
        return None

    if not member.phone:
        return None

    if transaction_id and not force:
        if _already_sent_today(member.id, transaction_id, message_type):
            return SmsLog.query.filter_by(
                member_id=member.id,
                transaction_id=transaction_id,
                message_type=message_type,
            ).order_by(SmsLog.sent_at.desc()).first()

    phone = _format_phone(member.phone)
    ok, provider_info = _dispatch_sms(phone, message)
    status = "Sent" if ok else f"Failed ({provider_info})"

    sms = SmsLog(
        member_id=member.id,
        transaction_id=transaction_id,
        phone=phone,
        message_type=message_type,
        message=message,
        status=status,
    )
    db.session.add(sms)
    log_activity("SMS", "Member", member.id, f"SMS ({message_type}) {status} via {provider_info} to {phone}")
    return sms


def notify_book_issued(transaction):
    member = transaction.member
    book = transaction.book
    due = transaction.due_date.strftime("%d-%m-%Y")
    message = (
        f"Dear {member.name}, Library RFID: Book '{book.title}' issued successfully. "
        f"Due date: {due}. Please return on time to avoid fine Rs.{get_fine_per_day():.0f}/day. "
        f"Receipt: {transaction.receipt_no or transaction.id}."
    )
    return send_sms(member, message, "ISSUE", transaction.id, force=True)


def notify_book_returned(transaction):
    member = transaction.member
    book = transaction.book
    ret_date = transaction.return_date.strftime("%d-%m-%Y")
    if transaction.fine_amount > 0:
        message = (
            f"Dear {member.name}, Library RFID: Book '{book.title}' returned on {ret_date}. "
            f"Overdue fine: Rs.{transaction.fine_amount:.0f}. "
            f"Please pay at library. Thank you!"
        )
        msg_type = "RETURN_FINE"
    else:
        message = (
            f"Dear {member.name}, Library RFID: Book '{book.title}' returned successfully "
            f"on {ret_date}. Thank you for using our library!"
        )
        msg_type = "RETURN"
    return send_sms(member, message, msg_type, transaction.id, force=True)


def notify_due_soon(transaction):
    member = transaction.member
    book = transaction.book
    due = transaction.due_date.strftime("%d-%m-%Y")
    days_left = (transaction.due_date.replace(tzinfo=None) - utcnow_naive()).days
    message = (
        f"Dear {member.name}, Library RFID REMINDER: Book '{book.title}' is due on {due} "
        f"({days_left} day(s) left). Please return on time. - Library Team"
    )
    return send_sms(member, message, "DUE_SOON", transaction.id)


def notify_overdue(transaction):
    member = transaction.member
    book = transaction.book
    due = transaction.due_date.strftime("%d-%m-%Y")
    now = utcnow_naive()
    days_overdue = (now - transaction.due_date.replace(tzinfo=None)).days
    est_fine = days_overdue * get_fine_per_day()
    message = (
        f"Dear {member.name}, Library RFID ALERT: Book '{book.title}' is OVERDUE since {due}. "
        f"{days_overdue} day(s) late. Estimated fine: Rs.{est_fine:.0f}. "
        f"Please return immediately. - Library Team"
    )
    return send_sms(member, message, "OVERDUE", transaction.id)


def notify_renewal(transaction):
    member = transaction.member
    book = transaction.book
    due = transaction.due_date.strftime("%d-%m-%Y")
    message = (
        f"Dear {member.name}, Library RFID: Book '{book.title}' renewed. "
        f"New due date: {due}. Thank you!"
    )
    return send_sms(member, message, "RENEW", transaction.id, force=True)


def check_and_send_due_alerts():
    """Scan active issues and send due-soon / overdue SMS."""
    if not is_sms_enabled():
        return {"due_soon": 0, "overdue": 0}

    from models.transaction import Transaction

    now = utcnow_naive()
    reminder_days = get_due_reminder_days()
    due_soon_count = 0
    overdue_count = 0

    active = Transaction.query.filter_by(return_date=None).all()
    for txn in active:
        due = txn.due_date.replace(tzinfo=None)
        if due < now:
            if not _already_sent_today(txn.member_id, txn.id, "OVERDUE"):
                notify_overdue(txn)
                overdue_count += 1
        else:
            days_left = (due - now).days
            if 0 <= days_left <= reminder_days:
                if not _already_sent_today(txn.member_id, txn.id, "DUE_SOON"):
                    notify_due_soon(txn)
                    due_soon_count += 1

    if due_soon_count or overdue_count:
        db.session.commit()

    return {"due_soon": due_soon_count, "overdue": overdue_count}


def send_manual_reminder(transaction_id):
    from models.transaction import Transaction

    txn = Transaction.query.get_or_404(transaction_id)
    if txn.return_date:
        return None, "Book already returned."
    now = utcnow_naive()
    if txn.due_date.replace(tzinfo=None) < now:
        sms = notify_overdue(txn)
        if sms:
            sms.status = "Sent (Manual)"
        db.session.commit()
        return sms, "Overdue SMS sent."
    sms = notify_due_soon(txn)
    if sms:
        sms.status = "Sent (Manual)"
    db.session.commit()
    return sms, "Reminder SMS sent."


def notify_portal_link(member, portal_url):
    message = (
        f"Dear {member.name}, access your library account here: {portal_url} "
        f"Login with your registered email ({member.email})."
    )
    return send_sms(member, message, "PORTAL_LINK", force=True)


def notify_damage_reply(member, book_title, admin_message):
    preview = admin_message[:120] + ("..." if len(admin_message) > 120 else "")
    message = (
        f"Dear {member.name}, library update on your damage report for '{book_title}': "
        f"{preview} Login to your member portal for full details."
    )
    return send_sms(member, message, "DAMAGE_REPLY", force=True)
