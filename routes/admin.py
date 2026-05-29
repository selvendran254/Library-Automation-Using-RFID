from flask import Blueprint, Response, flash, jsonify, redirect, render_template, request, url_for

from models import db
from models.activity_log import ActivityLog
from models.book import Book
from models.member import Member
from models.member_message import MemberPortalThread
from models.transaction import Transaction
from utils.database import export_csv
from utils.helpers import log_activity
from utils.portal_chat import (
    append_admin_message,
    build_thread_summaries,
    mark_thread_read_for_admin,
    serialize_thread_messages,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _admin_thread_summaries(limit=50):
    threads = (
        MemberPortalThread.query.order_by(MemberPortalThread.updated_at.desc())
        .limit(limit)
        .all()
    )
    summaries = []
    for thread in threads:
        last_msg = thread.messages[-1] if thread.messages else None
        summaries.append({
            "id": thread.id,
            "member_id": thread.member_id,
            "member_name": thread.member.name if thread.member else "Member",
            "subject": thread.subject,
            "kind": thread.kind,
            "updated_at": thread.updated_at,
            "admin_unread": thread.admin_unread,
            "last_preview": (last_msg.body[:80] + "…") if last_msg and len(last_msg.body) > 80 else (last_msg.body if last_msg else ""),
            "last_sender": last_msg.sender if last_msg else None,
            "status": thread.damage_report.status if thread.damage_report else None,
        })
    return summaries


@admin_bp.route("/portal-messages")
def portal_messages():
    threads = _admin_thread_summaries()
    unread = sum(1 for t in threads if t["admin_unread"])
    selected_id = request.args.get("thread", type=int)
    return render_template(
        "admin/portal_messages.html",
        threads=threads,
        unread_count=unread,
        selected_thread_id=selected_id,
    )


@admin_bp.route("/portal-messages/api/threads/<int:thread_id>")
def portal_messages_get_thread(thread_id):
    thread = MemberPortalThread.query.get_or_404(thread_id)
    mark_thread_read_for_admin(thread)
    return jsonify({
        "id": thread.id,
        "subject": thread.subject,
        "member_name": thread.member.name if thread.member else "Member",
        "member_id": thread.member_id,
        "status": thread.damage_report.status if thread.damage_report else None,
        "messages": serialize_thread_messages(thread),
    })


@admin_bp.route("/portal-messages/api/threads/<int:thread_id>/reply", methods=["POST"])
def portal_messages_reply(thread_id):
    thread = MemberPortalThread.query.get_or_404(thread_id)
    body = (request.json or {}).get("body", "").strip() if request.is_json else request.form.get("body", "").strip()
    if not body:
        if request.is_json:
            return jsonify({"error": "Please enter a message."}), 400
        flash("Please enter a message.", "danger")
        return redirect(url_for("admin.portal_messages", thread=thread_id))

    append_admin_message(thread, body)
    log_activity(
        "MESSAGE",
        "Member",
        thread.member_id,
        f"Admin replied in portal thread #{thread.id}",
    )

    if request.is_json:
        return jsonify({"ok": True, "messages": serialize_thread_messages(thread)})
    flash("Reply sent.", "success")
    return redirect(url_for("admin.portal_messages", thread=thread_id))


@admin_bp.route("/activity-log")
def activity_log():
    logs = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(200).all()
    return render_template("admin/activity_log.html", logs=logs)


@admin_bp.route("/search")
def global_search():
    q = request.args.get("q", "").strip()
    books, members, transactions = [], [], []
    if q:
        like = f"%{q}%"
        books = Book.query.filter(
            db.or_(
                Book.title.ilike(like),
                Book.author.ilike(like),
                Book.rfid_tag.ilike(like),
                Book.isbn.ilike(like),
            )
        ).limit(20).all()
        members = Member.query.filter(
            db.or_(
                Member.name.ilike(like),
                Member.rfid_card.ilike(like),
                Member.email.ilike(like),
            )
        ).limit(20).all()
        transactions = (
            Transaction.query.join(Book).join(Member)
            .filter(db.or_(Book.title.ilike(like), Member.name.ilike(like)))
            .limit(20).all()
        )
    return render_template(
        "admin/search.html",
        q=q,
        books=books,
        members=members,
        transactions=transactions,
    )


@admin_bp.route("/export/books")
def export_books():
    books = Book.query.all()
    rows = [
        [b.id, b.rfid_tag, b.isbn or "", b.title, b.author, b.category,
         b.total_qty, b.available_qty, b.shelf_location or ""]
        for b in books
    ]
    csv_data, _ = export_csv(
        ["ID", "RFID", "ISBN", "Title", "Author", "Category", "Total", "Available", "Shelf"],
        rows, "books.csv",
    )
    return Response(csv_data, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment;filename=books.csv"})


@admin_bp.route("/export/members")
def export_members():
    members = Member.query.all()
    rows = [
        [m.id, m.rfid_card, m.name, m.email, m.phone, m.membership_type,
         m.status, m.join_date, m.expiry_date or ""]
        for m in members
    ]
    csv_data, _ = export_csv(
        ["ID", "RFID Card", "Name", "Email", "Phone", "Type", "Status", "Join", "Expiry"],
        rows, "members.csv",
    )
    return Response(csv_data, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment;filename=members.csv"})


@admin_bp.route("/export/transactions")
def export_transactions():
    txns = Transaction.query.all()
    rows = [
        [t.id, t.book.title, t.member.name, t.issue_date, t.due_date,
         t.return_date or "", t.fine_amount, t.fine_paid, t.status]
        for t in txns
    ]
    csv_data, _ = export_csv(
        ["ID", "Book", "Member", "Issue", "Due", "Return", "Fine", "Paid", "Status"],
        rows, "transactions.csv",
    )
    return Response(csv_data, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment;filename=transactions.csv"})
