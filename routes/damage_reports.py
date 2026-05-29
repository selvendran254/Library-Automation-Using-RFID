from flask import Blueprint, flash, redirect, render_template, request, url_for

from models import db
from models.damage_report import BookDamageReport
from utils.helpers import log_activity, utcnow_naive
from utils.portal_chat import append_admin_message, get_or_create_damage_thread
from utils.sms_service import notify_damage_reply

damage_reports_bp = Blueprint("damage_reports", __name__, url_prefix="/admin/damage-reports")


def _apply_member_message(report, message, send_sms=False):
    message = message.strip()
    if not message:
        return False, "Please enter a message for the member."

    report.member_message = message
    report.member_message_at = utcnow_naive()
    report.member_message_read = False
    thread = get_or_create_damage_thread(report)
    append_admin_message(thread, message, sync_damage_report=False)
    db.session.commit()

    if send_sms:
        notify_damage_reply(report.member, report.book.title, message)

    log_activity(
        "MESSAGE",
        "DamageReport",
        report.id,
        f"Admin sent message to '{report.member.name}' for damage report #{report.id}",
    )
    return True, "Message sent to member. They will see it on their portal dashboard."


@damage_reports_bp.route("/")
def list_reports():
    status = request.args.get("status", "")
    query = BookDamageReport.query
    if status:
        query = query.filter_by(status=status)
    reports = query.order_by(BookDamageReport.created_at.desc()).all()
    pending_count = BookDamageReport.query.filter_by(status="Pending").count()
    return render_template(
        "admin/damage_reports.html",
        reports=reports,
        status_filter=status,
        pending_count=pending_count,
    )


@damage_reports_bp.route("/<int:report_id>")
def report_detail(report_id):
    report = BookDamageReport.query.get_or_404(report_id)
    return render_template("admin/damage_detail.html", report=report)


@damage_reports_bp.route("/<int:report_id>/message", methods=["POST"])
def send_member_message(report_id):
    report = BookDamageReport.query.get_or_404(report_id)
    message = request.form.get("member_message", "")
    send_sms = request.form.get("send_sms") == "1"
    ok, result = _apply_member_message(report, message, send_sms=send_sms)
    flash(result, "success" if ok else "danger")
    return redirect(url_for("damage_reports.report_detail", report_id=report.id))


@damage_reports_bp.route("/<int:report_id>/resolve", methods=["POST"])
def resolve_report(report_id):
    report = BookDamageReport.query.get_or_404(report_id)
    action = request.form.get("action", "Resolved")
    notes = request.form.get("admin_notes", "").strip()
    member_message = request.form.get("member_message", "").strip()
    send_sms = request.form.get("send_sms") == "1"

    report.status = action if action in ("Reviewed", "Resolved") else "Resolved"
    report.admin_notes = notes or report.admin_notes
    report.reviewed_at = utcnow_naive()

    if member_message:
        report.member_message = member_message
        report.member_message_at = utcnow_naive()
        report.member_message_read = False
        thread = get_or_create_damage_thread(report)
        append_admin_message(thread, member_message, sync_damage_report=False)
        if send_sms:
            notify_damage_reply(report.member, report.book.title, member_message)

    db.session.commit()
    log_activity(
        "UPDATE",
        "DamageReport",
        report.id,
        f"Damage report #{report.id} marked as {report.status}",
    )
    if member_message:
        flash(f"Report marked as {report.status} and message sent to member.", "success")
    else:
        flash(f"Report marked as {report.status}.", "success")
    return redirect(url_for("damage_reports.report_detail", report_id=report.id))
