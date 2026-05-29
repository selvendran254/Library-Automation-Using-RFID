from flask import Blueprint, flash, redirect, render_template, request, url_for

from models import db
from models.book import Book
from models.category import Category
from models.transaction import Transaction
from utils.helpers import log_activity

books_bp = Blueprint("books", __name__, url_prefix="/books")


@books_bp.route("/")
def list_books():
    category = request.args.get("category", "")
    availability = request.args.get("availability", "")
    bstatus = request.args.get("bstatus", "")
    query = Book.query
    if category:
        query = query.filter_by(category=category)
    if bstatus:
        query = query.filter_by(book_status=bstatus)
    if availability == "available":
        query = query.filter(Book.available_qty > 0)
    elif availability == "issued":
        query = query.filter(Book.available_qty < Book.total_qty)
    elif availability == "low":
        from utils.helpers import get_low_stock_threshold
        query = query.filter(Book.available_qty <= get_low_stock_threshold())
    books = query.order_by(Book.title).all()
    categories = Category.query.order_by(Category.name).all()
    book_categories = db.session.query(Book.category).distinct().all()
    return render_template(
        "books/list.html",
        books=books,
        categories=categories,
        book_categories=[c[0] for c in book_categories],
        category_filter=category,
        availability_filter=availability,
        bstatus_filter=bstatus,
    )


@books_bp.route("/<int:book_id>")
def book_detail(book_id):
    book = Book.query.get_or_404(book_id)
    history = (
        Transaction.query.filter_by(book_id=book.id)
        .order_by(Transaction.issue_date.desc())
        .limit(20)
        .all()
    )
    reservations = sorted(book.reservations, key=lambda r: r.reserved_date, reverse=True)[:10]
    return render_template(
        "books/detail.html", book=book, history=history, reservations=reservations
    )


@books_bp.route("/add", methods=["GET", "POST"])
def add_book():
    categories = Category.query.order_by(Category.name).all()
    if request.method == "POST":
        rfid_tag = request.form.get("rfid_tag", "").strip()
        title = request.form.get("title", "").strip()
        author = request.form.get("author", "").strip()
        category = request.form.get("category", "").strip()
        total_qty = int(request.form.get("total_qty", 1))

        if Book.query.filter_by(rfid_tag=rfid_tag).first():
            flash("RFID tag already exists.", "danger")
            return render_template("books/form.html", book=None, categories=categories)

        book = Book(
            rfid_tag=rfid_tag,
            isbn=request.form.get("isbn", "").strip() or None,
            title=title,
            author=author,
            publisher=request.form.get("publisher", "").strip() or None,
            category=category,
            shelf_location=request.form.get("shelf_location", "").strip() or None,
            description=request.form.get("description", "").strip() or None,
            total_qty=total_qty,
            available_qty=total_qty,
            book_status=request.form.get("book_status", "Active"),
        )
        db.session.add(book)
        db.session.commit()
        log_activity("CREATE", "Book", book.id, f"Book '{title}' added")
        flash("Book added successfully.", "success")
        return redirect(url_for("books.list_books"))

    return render_template("books/form.html", book=None, categories=categories)


@books_bp.route("/edit/<int:book_id>", methods=["GET", "POST"])
def edit_book(book_id):
    book = Book.query.get_or_404(book_id)
    categories = Category.query.order_by(Category.name).all()

    if request.method == "POST":
        rfid_tag = request.form.get("rfid_tag", "").strip()
        existing = Book.query.filter_by(rfid_tag=rfid_tag).first()
        if existing and existing.id != book.id:
            flash("RFID tag already exists.", "danger")
            return render_template("books/form.html", book=book, categories=categories)

        issued = book.total_qty - book.available_qty
        total_qty = int(request.form.get("total_qty", 1))
        if total_qty < issued:
            flash(f"Total quantity cannot be less than issued copies ({issued}).", "danger")
            return render_template("books/form.html", book=book, categories=categories)

        book.rfid_tag = rfid_tag
        book.isbn = request.form.get("isbn", "").strip() or None
        book.title = request.form.get("title", "").strip()
        book.author = request.form.get("author", "").strip()
        book.publisher = request.form.get("publisher", "").strip() or None
        book.category = request.form.get("category", "").strip()
        book.shelf_location = request.form.get("shelf_location", "").strip() or None
        book.description = request.form.get("description", "").strip() or None
        book.book_status = request.form.get("book_status", "Active")
        book.total_qty = total_qty
        book.available_qty = total_qty - issued
        db.session.commit()
        log_activity("UPDATE", "Book", book.id, f"Book '{book.title}' updated")
        flash("Book updated successfully.", "success")
        return redirect(url_for("books.list_books"))

    return render_template("books/form.html", book=book, categories=categories)


@books_bp.route("/delete/<int:book_id>", methods=["POST"])
def delete_book(book_id):
    book = Book.query.get_or_404(book_id)
    if book.issued_count > 0:
        flash("Cannot delete book with active issues.", "danger")
        return redirect(url_for("books.list_books"))

    db.session.delete(book)
    db.session.commit()
    log_activity("DELETE", "Book", book_id, f"Book '{book.title}' deleted")
    flash("Book deleted successfully.", "success")
    return redirect(url_for("books.list_books"))
