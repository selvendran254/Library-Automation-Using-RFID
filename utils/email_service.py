import smtplib
from email.message import EmailMessage

from flask import current_app

from models.settings import LibrarySetting
from utils.helpers import log_activity


def is_email_enabled():
    return LibrarySetting.get("email_enabled", "0") == "1"


def send_email(to_address, subject, body):
    if not is_email_enabled() or not to_address:
        return False, "Email disabled or missing address"

    host = LibrarySetting.get("email_smtp_host", current_app.config.get("SMTP_HOST", ""))
    port = LibrarySetting.get_int("email_smtp_port", current_app.config.get("SMTP_PORT", 587))
    username = LibrarySetting.get("email_smtp_user", current_app.config.get("SMTP_USER", ""))
    password = LibrarySetting.get("email_smtp_password", current_app.config.get("SMTP_PASSWORD", ""))
    from_addr = LibrarySetting.get("email_from", current_app.config.get("EMAIL_FROM", username))
    use_tls = LibrarySetting.get("email_use_tls", "1") == "1"

    if not host or not from_addr:
        return False, "SMTP not configured"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_address
    msg.set_content(body)

    try:
        with smtplib.SMTP(host, port, timeout=15) as server:
            if use_tls:
                server.starttls()
            if username and password:
                server.login(username, password)
            server.send_message(msg)
        log_activity("EMAIL", "Email", 0, f"Email sent to {to_address}: {subject}")
        return True, "Email sent"
    except Exception as exc:
        return False, str(exc)


def notify_member_email(member, subject, body):
    if not member.email:
        return False, "Member has no email"
    return send_email(member.email, subject, body)
