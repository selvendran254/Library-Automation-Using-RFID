from datetime import datetime, timedelta, timezone

from flask import Blueprint, flash, redirect, render_template, request, url_for

from models import db
from models.book import Book
from models.member import Member
from models.reservation import Reservation
from utils.helpers import get_reservation_hold_days, log_activity, utcnow_naive

reservations_bp = Blueprint("reservations", __name__, url_prefix="/reservations")


@reservations_bp.route("/")
def list_reservations():
    status_filter = request.args.get("status", "")
    query = Reservation.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    reservations = query.order_by(Reservation.reserved_date.desc()).all()
    return render_template(
        "reservations/list.html",
        reservations=reservations,
        status_filter=status_filter,
    )


@reservations_bp.route("/add", methods=["GET", "POST"])
def add_reservation():
    books = Book.query.order_by(Book.title).all()
    members = Member.query.filter_by(status="Active").order_by(Member.name).all()

    if request.method == "POST":
        book_id = int(request.form.get("book_id"))
        member_id = int(request.form.get("member_id"))
        notes = request.form.get("notes", "").strip()

        book = Book.query.get_or_404(book_id)
        member = Member.query.get_or_404(member_id)

        existing = Reservation.query.filter_by(
            book_id=book_id, member_id=member_id, status="Pending"
        ).first()
        if existing:
            flash("Member already has a pending reservation for this book.", "warning")
            return render_template("reservations/form.html", books=books, members=members)

        now = utcnow_naive()
        reservation = Reservation(
            book_id=book_id,
            member_id=member_id,
            reserved_date=now,
            expiry_date=now + timedelta(days=get_reservation_hold_days()),
            notes=notes,
        )
        db.session.add(reservation)
        db.session.commit()
        log_activity(
            "RESERVE", "Book", book.id,
            f"'{book.title}' reserved for {member.name}",
        )
        flash(f"Reservation created for '{book.title}'.", "success")
        return redirect(url_for("reservations.list_reservations"))

    return render_template("reservations/form.html", books=books, members=members)


@reservations_bp.route("/<int:res_id>/fulfill", methods=["POST"])
def fulfill_reservation(res_id):
    reservation = Reservation.query.get_or_404(res_id)
    reservation.status = "Fulfilled"
    db.session.commit()
    log_activity("FULFILL", "Reservation", res_id, "Reservation marked as fulfilled")
    flash("Reservation fulfilled.", "success")
    return redirect(url_for("reservations.list_reservations"))


@reservations_bp.route("/<int:res_id>/cancel", methods=["POST"])
def cancel_reservation(res_id):
    reservation = Reservation.query.get_or_404(res_id)
    reservation.status = "Cancelled"
    db.session.commit()
    flash("Reservation cancelled.", "info")
    return redirect(url_for("reservations.list_reservations"))
