from flask import Blueprint, jsonify, render_template, request

from models import db
from models.book import Book
from models.member import Member
from models.transaction import Transaction
from utils.helpers import utcnow_naive

tools_bp = Blueprint("tools", __name__, url_prefix="/tools")


@tools_bp.route("/lookup")
def quick_lookup():
    q = request.args.get("q", "").strip()
    book, member, active_txn = None, None, None
    if q:
        book = Book.query.filter(
            db.or_(Book.rfid_tag.ilike(q), Book.isbn.ilike(f"%{q}%"), Book.title.ilike(f"%{q}%"))
        ).first()
        member = Member.query.filter(
            db.or_(Member.rfid_card.ilike(q), Member.phone.ilike(f"%{q}%"), Member.name.ilike(f"%{q}%"))
        ).first()
        if book:
            active_txn = (
                Transaction.query.filter_by(book_id=book.id, return_date=None)
                .order_by(Transaction.issue_date.desc()).first()
            )
        if member and not book:
            active_txn = member.transactions.filter_by(return_date=None).first()
    return render_template("tools/lookup.html", q=q, book=book, member=member, active_txn=active_txn)


@tools_bp.route("/api/scan/<tag>")
def api_scan(tag):
    book = Book.query.filter_by(rfid_tag=tag).first()
    if book:
        txn = Transaction.query.filter_by(book_id=book.id, return_date=None).first()
        return jsonify({
            "type": "book", "rfid": book.rfid_tag, "title": book.title,
            "author": book.author, "available": book.available_qty,
            "status": book.book_status,
            "issued_to": txn.member.name if txn else None,
            "due_date": txn.due_date.strftime("%d-%m-%Y") if txn else None,
        })
    member = Member.query.filter_by(rfid_card=tag).first()
    if member:
        active = member.transactions.filter_by(return_date=None).count()
        return jsonify({
            "type": "member", "card": member.rfid_card, "name": member.name,
            "phone": member.phone, "membership_type": member.membership_type,
            "status": member.status, "active_books": active,
            "pending_fine": member.pending_fine,
        })
    return jsonify({"type": "unknown", "message": "Tag not found"})


@tools_bp.route("/help")
def help_guide():
    return render_template("tools/help.html")
