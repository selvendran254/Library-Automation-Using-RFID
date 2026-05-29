import random
from datetime import timedelta

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from models import db
from models.book import Book
from models.member import Member
from models.sms_log import SmsLog
from models.transaction import Transaction
from utils.helpers import (
    can_member_borrow,
    get_fine_per_day,
    get_loan_days,
    get_max_books,
    get_max_renewals,
    get_renewal_days,
    log_activity,
    utcnow_naive,
)
from utils.sms_service import notify_book_issued, notify_book_returned, notify_renewal

transactions_bp = Blueprint("transactions", __name__, url_prefix="/transactions")


def _generate_receipt():
    return f"RCP-{utcnow_naive().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"


@transactions_bp.route("/")
def list_transactions():
    status = request.args.get("status", "")
    query = Transaction.query
    now = utcnow_naive()
    if status == "issued":
        query = query.filter_by(return_date=None)
    elif status == "overdue":
        query = query.filter(Transaction.return_date.is_(None), Transaction.due_date < now)
    elif status == "returned":
        query = query.filter(Transaction.return_date.isnot(None))
    transactions = query.order_by(Transaction.issue_date.desc()).all()
    return render_template(
        "transactions/list.html", transactions=transactions, status_filter=status
    )


@transactions_bp.route("/issue", methods=["GET", "POST"])
def issue_book():
    if request.method == "POST":
        member_card = request.form.get("member_card", "").strip()
        book_tag = request.form.get("book_tag", "").strip()

        member = Member.query.filter_by(rfid_card=member_card).first()
        if not member:
            flash("Invalid member RFID card.", "danger")
            return render_template("transactions/issue.html")

        ok, msg = can_member_borrow(member)
        if not ok:
            flash(msg, "danger")
            return render_template("transactions/issue.html")

        book = Book.query.filter_by(rfid_tag=book_tag).first()
        if not book:
            flash("Invalid book RFID tag.", "danger")
            return render_template("transactions/issue.html")

        if book.available_qty <= 0:
            flash("No copies available. Try creating a reservation.", "danger")
            return render_template("transactions/issue.html")

        now = utcnow_naive()
        due_date = now + timedelta(days=get_loan_days())
        receipt = _generate_receipt()

        transaction = Transaction(
            book_id=book.id,
            member_id=member.id,
            issue_date=now,
            due_date=due_date,
            receipt_no=receipt,
        )
        book.available_qty -= 1
        db.session.add(transaction)
        db.session.flush()
        notify_book_issued(transaction)
        log_activity("ISSUE", "Transaction", transaction.id,
                     f"'{book.title}' issued to {member.name}")
        db.session.commit()
        sms = SmsLog.query.filter_by(transaction_id=transaction.id, message_type="ISSUE").first()
        sms_note = f" SMS sent to {member.phone}." if sms else ""
        flash(
            f"Book '{book.title}' issued to {member.name}. Due: {due_date.strftime('%d-%m-%Y')}. Receipt: {receipt}.{sms_note}",
            "success",
        )
        return redirect(url_for("transactions.receipt", transaction_id=transaction.id))

    return render_template("transactions/issue.html")


@transactions_bp.route("/bulk-issue", methods=["GET", "POST"])
def bulk_issue():
    if request.method == "POST":
        member_card = request.form.get("member_card", "").strip()
        book_tags = request.form.getlist("book_tags")

        member = Member.query.filter_by(rfid_card=member_card).first()
        if not member:
            flash("Invalid member card.", "danger")
            return render_template("transactions/bulk_issue.html")

        ok, msg = can_member_borrow(member)
        if not ok:
            flash(msg, "danger")
            return render_template("transactions/bulk_issue.html")

        issued = []
        now = utcnow_naive()
        due_date = now + timedelta(days=get_loan_days())

        for tag in book_tags:
            if member.active_books_count + len(issued) >= get_max_books(member):
                break
            book = Book.query.filter_by(rfid_tag=tag.strip()).first()
            if book and book.available_qty > 0:
                txn = Transaction(
                    book_id=book.id, member_id=member.id,
                    issue_date=now, due_date=due_date,
                    receipt_no=_generate_receipt(),
                )
                book.available_qty -= 1
                db.session.add(txn)
                issued.append(book.title)

        if issued:
            db.session.commit()
            flash(f"Issued {len(issued)} books to {member.name}: {', '.join(issued)}", "success")
        else:
            flash("No books could be issued.", "warning")
        return redirect(url_for("transactions.list_transactions"))

    available_books = Book.query.filter(Book.available_qty > 0).order_by(Book.title).all()
    return render_template("transactions/bulk_issue.html", available_books=available_books)


@transactions_bp.route("/return", methods=["GET", "POST"])
def return_book():
    if request.method == "POST":
        book_tag = request.form.get("book_tag", "").strip()
        book = Book.query.filter_by(rfid_tag=book_tag).first()
        if not book:
            flash("Invalid book RFID tag.", "danger")
            return render_template("transactions/return.html")

        transaction = (
            Transaction.query.filter_by(book_id=book.id, return_date=None)
            .order_by(Transaction.issue_date.desc())
            .first()
        )
        if not transaction:
            flash("No active issue found for this book.", "danger")
            return render_template("transactions/return.html")

        now = utcnow_naive()
        transaction.return_date = now
        transaction.fine_amount = transaction.calculate_fine(get_fine_per_day())
        book.available_qty += 1
        member = transaction.member
        notify_book_returned(transaction)
        log_activity("RETURN", "Transaction", transaction.id,
                     f"'{book.title}' returned by {member.name}")
        db.session.commit()
        sms = SmsLog.query.filter(
            SmsLog.transaction_id == transaction.id,
            SmsLog.message_type.in_(["RETURN", "RETURN_FINE"]),
        ).order_by(SmsLog.sent_at.desc()).first()
        sms_note = f" SMS confirmation sent to {member.phone}." if sms else ""
        if transaction.fine_amount > 0:
            flash(f"Book returned by {member.name}. Fine: ₹{transaction.fine_amount:.0f}.{sms_note}", "warning")
        else:
            flash(f"Book returned successfully from {member.name}.{sms_note}", "success")
        return redirect(url_for("transactions.receipt", transaction_id=transaction.id))

    return render_template("transactions/return.html")


@transactions_bp.route("/renew/<int:transaction_id>", methods=["POST"])
def renew_book(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    if transaction.return_date:
        flash("Cannot renew a returned book.", "danger")
        return redirect(url_for("transactions.list_transactions"))

    if transaction.renewal_count >= get_max_renewals():
        flash(f"Maximum renewals ({get_max_renewals()}) reached.", "danger")
        return redirect(url_for("transactions.list_transactions"))

    transaction.due_date = transaction.due_date + timedelta(days=get_renewal_days())
    transaction.renewal_count += 1
    notify_renewal(transaction)
    log_activity("RENEW", "Transaction", transaction.id,
                 f"Book renewed. New due: {transaction.due_date.strftime('%d-%m-%Y')}")
    db.session.commit()
    sms = SmsLog.query.filter_by(transaction_id=transaction.id, message_type="RENEW").order_by(SmsLog.sent_at.desc()).first()
    sms_note = f" SMS sent to {transaction.member.phone}." if sms else ""
    flash(f"Book renewed. New due date: {transaction.due_date.strftime('%d-%m-%Y')}.{sms_note}", "success")
    return redirect(url_for("transactions.list_transactions"))


@transactions_bp.route("/receipt/<int:transaction_id>")
def receipt(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    return render_template("transactions/receipt.html", transaction=transaction)


@transactions_bp.route("/fines")
def list_fines():
    status = request.args.get("status", "")
    query = Transaction.query.filter(
        Transaction.fine_amount > 0, Transaction.return_date.isnot(None)
    )
    if status == "paid":
        query = query.filter_by(fine_paid=True)
    elif status == "pending":
        query = query.filter_by(fine_paid=False)
    fines = query.order_by(Transaction.return_date.desc()).all()
    return render_template("transactions/fines.html", fines=fines, status_filter=status)


@transactions_bp.route("/fines/<int:transaction_id>/pay", methods=["POST"])
def pay_fine(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    if transaction.fine_amount <= 0:
        flash("No fine to pay.", "info")
    elif transaction.fine_paid:
        flash("Fine already paid.", "info")
    else:
        transaction.fine_paid = True
        db.session.commit()
        log_activity("PAY_FINE", "Transaction", transaction.id,
                     f"Fine ₹{transaction.fine_amount:.0f} paid")
        flash(f"Fine of ₹{transaction.fine_amount:.0f} marked as paid.", "success")
    return redirect(url_for("transactions.list_fines"))


@transactions_bp.route("/fines/pay-all/<int:member_id>", methods=["POST"])
def pay_all_fines(member_id):
    member = Member.query.get_or_404(member_id)
    unpaid = member.transactions.filter(
        Transaction.fine_paid.is_(False), Transaction.fine_amount > 0
    ).all()
    total = sum(t.fine_amount for t in unpaid)
    for t in unpaid:
        t.fine_paid = True
    db.session.commit()
    flash(f"All fines (₹{total:.0f}) for {member.name} marked as paid.", "success")
    return redirect(url_for("members.member_detail", member_id=member.id))


@transactions_bp.route("/api/rfid/random/<scan_type>")
def random_rfid(scan_type):
    return jsonify({
        "success": False,
        "message": "Mock scan disabled. Use real USB RFID reader.",
    }), 403


@transactions_bp.route("/api/rfid/validate", methods=["POST"])
def validate_rfid():
    data = request.get_json() or {}
    scan_type = data.get("type")
    tag = (data.get("tag") or "").strip()

    if scan_type == "member":
        member = Member.query.filter_by(rfid_card=tag).first()
        if member and member.status == "Active":
            ok, msg = can_member_borrow(member)
            if not ok:
                return jsonify({"valid": False, "message": msg})
            return jsonify({
                "valid": True, "name": member.name, "id": member.id,
                "active_books": member.active_books_count,
            })
        return jsonify({"valid": False, "message": "Invalid or inactive member card"})

    if scan_type == "book":
        book = Book.query.filter_by(rfid_tag=tag).first()
        if book:
            return jsonify({
                "valid": True, "title": book.title,
                "available": book.available_qty, "id": book.id,
            })
        return jsonify({"valid": False, "message": "Invalid book tag"})

    if scan_type == "book-return":
        book = Book.query.filter_by(rfid_tag=tag).first()
        if not book:
            return jsonify({"valid": False, "message": "Invalid book tag"})
        txn = (
            Transaction.query.filter_by(book_id=book.id, return_date=None)
            .order_by(Transaction.issue_date.desc()).first()
        )
        if txn:
            return jsonify({
                "valid": True, "title": book.title,
                "member": txn.member.name, "member_id": txn.member.id,
            })
        return jsonify({"valid": False, "message": "No active issue for this book"})

    return jsonify({"valid": False, "message": "Invalid scan type"})
