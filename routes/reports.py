from flask import Blueprint, make_response, render_template, request
from sqlalchemy import func

from models import db
from models.book import Book
from models.category import Category
from models.member import Member
from models.reservation import Reservation
from models.transaction import Transaction
from utils.helpers import get_fine_per_day, get_low_stock_threshold, utcnow_naive
from utils.database import export_csv

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


@reports_bp.route("/")
def reports_home():
    now = utcnow_naive()
    issued_count = Transaction.query.filter_by(return_date=None).count()
    overdue_count = Transaction.query.filter(
        Transaction.return_date.is_(None), Transaction.due_date < now
    ).count()
    available_copies = db.session.query(func.coalesce(func.sum(Book.available_qty), 0)).scalar() or 0
    issued_copies = db.session.query(func.coalesce(func.sum(Book.total_qty - Book.available_qty), 0)).scalar() or 0
    pending_fines = (
        db.session.query(func.coalesce(func.sum(Transaction.fine_amount), 0))
        .filter(Transaction.fine_paid.is_(False), Transaction.fine_amount > 0)
        .scalar() or 0
    )
    pending_reservations = Reservation.query.filter_by(status="Pending").count()
    return render_template(
        "reports/index.html",
        issued_count=issued_count,
        overdue_count=overdue_count,
        available_copies=available_copies,
        issued_copies=issued_copies,
        pending_fines=pending_fines,
        pending_reservations=pending_reservations,
    )


@reports_bp.route("/current-status")
def current_status():
    now = utcnow_naive()
    fine_rate = get_fine_per_day()

    active_txns = (
        Transaction.query.filter_by(return_date=None)
        .order_by(Transaction.due_date)
        .all()
    )

    issued_rows = []
    overdue_rows = []
    for txn in active_txns:
        due = txn.due_date.replace(tzinfo=None)
        days_left = (due - now).days
        issued_rows.append({"transaction": txn, "days_left": days_left})
        if days_left < 0:
            overdue_rows.append(
                {
                    "transaction": txn,
                    "days_overdue": abs(days_left),
                    "estimated_fine": abs(days_left) * fine_rate,
                }
            )

    remaining_books = (
        Book.query.filter(Book.available_qty > 0)
        .order_by(Book.category, Book.title)
        .all()
    )
    partially_issued = (
        Book.query.filter(Book.available_qty < Book.total_qty)
        .order_by(Book.title)
        .all()
    )
    pending_fines = (
        Transaction.query.filter(
            Transaction.fine_paid.is_(False), Transaction.fine_amount > 0
        )
        .order_by(Transaction.return_date.desc())
        .all()
    )
    pending_reservations = (
        Reservation.query.filter_by(status="Pending")
        .order_by(Reservation.reserved_date.desc())
        .all()
    )
    members_with_books = (
        Member.query.join(Transaction)
        .filter(Transaction.return_date.is_(None))
        .distinct()
        .order_by(Member.name)
        .all()
    )

    stats = {
        "issued_count": len(issued_rows),
        "overdue_count": len(overdue_rows),
        "remaining_titles": len(remaining_books),
        "remaining_copies": sum(b.available_qty for b in remaining_books),
        "pending_fines_total": sum(f.fine_amount for f in pending_fines),
        "pending_reservations": len(pending_reservations),
        "members_with_books": len(members_with_books),
    }

    return render_template(
        "reports/current_status.html",
        issued_rows=issued_rows,
        overdue_rows=overdue_rows,
        remaining_books=remaining_books,
        partially_issued=partially_issued,
        pending_fines=pending_fines,
        pending_reservations=pending_reservations,
        members_with_books=members_with_books,
        stats=stats,
        fine_rate=fine_rate,
        now=now,
    )


@reports_bp.route("/current-status/export")
def export_current_status():
    now = utcnow_naive()
    fine_rate = get_fine_per_day()
    active_txns = (
        Transaction.query.filter_by(return_date=None)
        .order_by(Transaction.due_date)
        .all()
    )
    rows = []
    for txn in active_txns:
        due = txn.due_date.replace(tzinfo=None)
        days_left = (due - now).days
        status = "Overdue" if days_left < 0 else ("Due Today" if days_left == 0 else "Issued")
        rows.append([
            txn.book.rfid_tag,
            txn.book.title,
            txn.member.name,
            txn.member.rfid_card,
            txn.member.phone,
            txn.issue_date.strftime("%d-%m-%Y"),
            txn.due_date.strftime("%d-%m-%Y"),
            days_left,
            status,
            abs(days_left) * fine_rate if days_left < 0 else 0,
        ])
    csv_data, _ = export_csv(
        [
            "Book RFID", "Book Title", "Member", "Member Card", "Phone",
            "Issue Date", "Due Date", "Days Left", "Status", "Est. Fine",
        ],
        rows,
        "current_not_returned.csv",
    )
    response = make_response(csv_data)
    response.headers["Content-Type"] = "text/csv"
    response.headers["Content-Disposition"] = "attachment; filename=current_not_returned.csv"
    return response


@reports_bp.route("/search-books")
def search_books():
    query = request.args.get("q", "").strip()
    books = Book.query
    if query:
        like = f"%{query}%"
        books = books.filter(
            db.or_(
                Book.title.ilike(like),
                Book.author.ilike(like),
                Book.category.ilike(like),
                Book.rfid_tag.ilike(like),
            )
        )
    books = books.order_by(Book.title).all()
    return render_template("reports/search_books.html", books=books, query=query)


@reports_bp.route("/search-members")
def search_members():
    query = request.args.get("q", "").strip()
    members = Member.query
    if query:
        like = f"%{query}%"
        members = members.filter(
            db.or_(
                Member.name.ilike(like),
                Member.rfid_card.ilike(like),
                Member.email.ilike(like),
                db.cast(Member.id, db.String).ilike(like),
            )
        )
    members = members.order_by(Member.name).all()
    return render_template("reports/search_members.html", members=members, query=query)


@reports_bp.route("/issued-books")
def issued_books():
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    transactions = (
        Transaction.query.filter_by(return_date=None)
        .order_by(Transaction.issue_date.desc())
        .all()
    )
    issued_rows = []
    for txn in transactions:
        due = txn.due_date.replace(tzinfo=None)
        days_left = (due - now).days
        issued_rows.append({"transaction": txn, "days_left": days_left})
    return render_template("reports/issued_books.html", issued_rows=issued_rows)


@reports_bp.route("/overdue-books")
def overdue_books():
    now = utcnow_naive()
    transactions = (
        Transaction.query.filter(
            Transaction.return_date.is_(None),
            Transaction.due_date < now,
        )
        .order_by(Transaction.due_date)
        .all()
    )
    fine_rate = get_fine_per_day()
    overdue_rows = []
    for txn in transactions:
        due = txn.due_date.replace(tzinfo=None)
        days_overdue = (now - due).days
        overdue_rows.append(
            {
                "transaction": txn,
                "days_overdue": days_overdue,
                "estimated_fine": days_overdue * fine_rate,
            }
        )
    return render_template("reports/overdue_books.html", overdue_rows=overdue_rows)


@reports_bp.route("/fine-summary")
def fine_summary():
    paid_total = (
        db.session.query(func.coalesce(func.sum(Transaction.fine_amount), 0))
        .filter(Transaction.fine_paid.is_(True), Transaction.fine_amount > 0)
        .scalar()
    )
    pending_total = (
        db.session.query(func.coalesce(func.sum(Transaction.fine_amount), 0))
        .filter(Transaction.fine_paid.is_(False), Transaction.fine_amount > 0)
        .scalar()
    )
    pending_fines = (
        Transaction.query.filter(Transaction.fine_paid.is_(False), Transaction.fine_amount > 0)
        .order_by(Transaction.return_date.desc())
        .all()
    )
    paid_fines = (
        Transaction.query.filter(Transaction.fine_paid.is_(True), Transaction.fine_amount > 0)
        .order_by(Transaction.return_date.desc())
        .all()
    )
    return render_template(
        "reports/fine_summary.html",
        paid_total=paid_total,
        pending_total=pending_total,
        pending_fines=pending_fines,
        paid_fines=paid_fines,
    )


@reports_bp.route("/most-borrowed")
def most_borrowed():
    results = (
        db.session.query(
            Book,
            func.count(Transaction.id).label("borrow_count"),
        )
        .join(Transaction, Book.id == Transaction.book_id)
        .group_by(Book.id)
        .order_by(func.count(Transaction.id).desc())
        .limit(10)
        .all()
    )
    return render_template("reports/most_borrowed.html", results=results)


@reports_bp.route("/category-wise")
def category_wise():
    results = (
        db.session.query(
            Book.category,
            func.count(Book.id).label("book_count"),
            func.sum(Book.total_qty).label("total_copies"),
            func.sum(Book.available_qty).label("available_copies"),
        )
        .group_by(Book.category)
        .order_by(func.count(Book.id).desc())
        .all()
    )
    return render_template("reports/category_wise.html", results=results)


@reports_bp.route("/inventory")
def inventory_report():
    threshold = get_low_stock_threshold()
    all_books = Book.query.order_by(Book.category, Book.title).all()
    low_stock = [b for b in all_books if b.available_qty <= threshold and b.available_qty > 0]
    out_of_stock = [b for b in all_books if b.available_qty == 0]
    currently_issued_books = [b for b in all_books if b.available_qty < b.total_qty]
    total_available = sum(b.available_qty for b in all_books)
    total_issued = sum(b.total_qty - b.available_qty for b in all_books)
    return render_template(
        "reports/inventory.html",
        all_books=all_books,
        low_stock=low_stock,
        out_of_stock=out_of_stock,
        currently_issued_books=currently_issued_books,
        total_available=total_available,
        total_issued=total_issued,
        threshold=threshold,
    )


@reports_bp.route("/member-activity")
def member_activity():
    results = (
        db.session.query(
            Member,
            func.count(Transaction.id).label("txn_count"),
        )
        .outerjoin(Transaction, Member.id == Transaction.member_id)
        .group_by(Member.id)
        .order_by(func.count(Transaction.id).desc())
        .all()
    )
    return render_template("reports/member_activity.html", results=results)


@reports_bp.route("/daily-transactions")
def daily_transactions():
    results = (
        db.session.query(
            func.date(Transaction.issue_date).label("day"),
            func.count(Transaction.id).label("issue_count"),
        )
        .group_by(func.date(Transaction.issue_date))
        .order_by(func.date(Transaction.issue_date).desc())
        .limit(30)
        .all()
    )
    return render_template("reports/daily_transactions.html", results=results)


@reports_bp.route("/reservations")
def reservations_report():
    pending_list = (
        Reservation.query.filter_by(status="Pending")
        .order_by(Reservation.reserved_date.desc())
        .all()
    )
    other_reservations = (
        Reservation.query.filter(Reservation.status != "Pending")
        .order_by(Reservation.reserved_date.desc())
        .all()
    )
    pending = len(pending_list)
    fulfilled = Reservation.query.filter_by(status="Fulfilled").count()
    cancelled = Reservation.query.filter_by(status="Cancelled").count()
    return render_template(
        "reports/reservations.html",
        pending_list=pending_list,
        other_reservations=other_reservations,
        pending=pending,
        fulfilled=fulfilled,
        cancelled=cancelled,
    )
