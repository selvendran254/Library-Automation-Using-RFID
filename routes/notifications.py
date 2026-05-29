from datetime import timedelta

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from models import db
from models.sms_log import SmsLog
from models.transaction import Transaction
from utils.helpers import utcnow_naive
from utils.sms_service import check_and_send_due_alerts, get_due_reminder_days, send_manual_reminder

notifications_bp = Blueprint("notifications", __name__, url_prefix="/notifications")


@notifications_bp.route("/")
def sms_inbox():
    msg_type = request.args.get("type", "")
    query = SmsLog.query
    if msg_type:
        query = query.filter_by(message_type=msg_type)
    logs = query.order_by(SmsLog.sent_at.desc()).limit(200).all()
    return render_template("notifications/sms_log.html", logs=logs, type_filter=msg_type)


@notifications_bp.route("/alerts")
def due_alerts():
    now = utcnow_naive()
    reminder_days = get_due_reminder_days()
    overdue = (
        Transaction.query.filter(
            Transaction.return_date.is_(None), Transaction.due_date < now
        )
        .order_by(Transaction.due_date)
        .all()
    )
    due_soon = (
        Transaction.query.filter(
            Transaction.return_date.is_(None),
            Transaction.due_date >= now,
            Transaction.due_date <= now + timedelta(days=reminder_days),
        )
        .order_by(Transaction.due_date)
        .all()
    )
    recent_sms = SmsLog.query.order_by(SmsLog.sent_at.desc()).limit(10).all()
    return render_template(
        "notifications/alerts.html",
        overdue=overdue,
        due_soon=due_soon,
        recent_sms=recent_sms,
        reminder_days=reminder_days,
    )


@notifications_bp.route("/check-alerts", methods=["POST"])
def run_alert_check():
    result = check_and_send_due_alerts()
    total = result["due_soon"] + result["overdue"]
    if total:
        flash(
            f"SMS alerts sent: {result['due_soon']} due-soon, {result['overdue']} overdue.",
            "success",
        )
    else:
        flash("No new alerts to send. All members already notified today.", "info")
    return redirect(url_for("notifications.due_alerts"))


@notifications_bp.route("/send-reminder/<int:transaction_id>", methods=["POST"])
def send_reminder(transaction_id):
    sms, msg = send_manual_reminder(transaction_id)
    if sms:
        flash(f"SMS sent to {sms.phone}. {msg}", "success")
    else:
        flash(msg, "warning")
    return redirect(request.referrer or url_for("notifications.due_alerts"))


@notifications_bp.route("/bulk-overdue-sms", methods=["POST"])
def bulk_overdue_sms():
    from models.transaction import Transaction
    from utils.sms_service import notify_overdue

    now = utcnow_naive()
    overdue = Transaction.query.filter(
        Transaction.return_date.is_(None), Transaction.due_date < now
    ).all()
    sent = 0
    for txn in overdue:
        sms = notify_overdue(txn)
        if sms:
            sent += 1
    db.session.commit()
    flash(f"Overdue SMS sent to {sent} member(s).", "success")
    return redirect(url_for("notifications.due_alerts"))


@notifications_bp.route("/api/sms/simulate/<int:sms_id>")
def simulate_sms_delivery(sms_id):
    sms = SmsLog.query.get_or_404(sms_id)
    return jsonify({
        "success": True,
        "phone": sms.phone,
        "type": sms.message_type,
        "message": sms.message,
        "sent_at": sms.sent_at.strftime("%d-%m-%Y %H:%M"),
        "status": sms.status,
    })
