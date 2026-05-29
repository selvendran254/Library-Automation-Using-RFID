from datetime import datetime, timedelta, timezone

from flask import Flask, g, jsonify, redirect, render_template, request, session, url_for
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import func

from config import Config
from models import db
from models.book import Book
from models.member import Member
from models.reservation import Reservation
from models.staff_user import StaffUser
from models.transaction import Transaction
from routes.auth import auth_bp
from routes.damage_reports import damage_reports_bp
from routes.admin import admin_bp
from routes.books import books_bp
from routes.member_portal import member_portal_bp
from routes.members import members_bp
from routes.notifications import notifications_bp
from routes.reports import reports_bp
from routes.reservations import reservations_bp
from routes.settings import settings_bp
from routes.notices import notices_bp
from routes.requests import requests_bp
from routes.rfid import rfid_bp
from routes.tools import tools_bp
from routes.transactions import transactions_bp
from utils.database import upgrade_database
from utils.auth import STAFF_SESSION_KEY, should_require_staff_login
from utils.helpers import get_low_stock_threshold, seed_default_categories, seed_default_settings, utcnow_naive
from utils.upload_helpers import ensure_upload_folder
from utils.rfid_reader import RfidHardwareService
from utils.sms_service import check_and_send_due_alerts
from models.sms_log import SmsLog
from models.notice import Notice
from models.book_request import BookRequest
from models.damage_report import BookDamageReport
from models.activity_log import ActivityLog


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    Migrate(app, db)
    csrf = CSRFProtect(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(books_bp)
    app.register_blueprint(members_bp)
    app.register_blueprint(member_portal_bp)
    app.register_blueprint(transactions_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(reservations_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(damage_reports_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(notices_bp)
    app.register_blueprint(requests_bp)
    app.register_blueprint(tools_bp)
    app.register_blueprint(rfid_bp)

    @app.context_processor
    def inject_globals():
        from models.settings import LibrarySetting
        from models.member_message import MemberPortalThread
        from utils.auth import get_current_staff

        mode = LibrarySetting.get("rfid_mode", "hid")
        portal_admin_unread = MemberPortalThread.query.filter_by(admin_unread=True).count()
        staff = get_current_staff()
        return {
            "rfid_mode": mode,
            "portal_admin_unread": portal_admin_unread,
            "current_staff": staff,
        }

    @app.before_request
    def enforce_staff_login():
        if not should_require_staff_login():
            return
        staff_id = session.get(STAFF_SESSION_KEY)
        if not staff_id:
            if request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json":
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("auth.login", next=request.url))
        staff = StaffUser.query.get(staff_id)
        if not staff or not staff.is_active:
            session.pop(STAFF_SESSION_KEY, None)
            return redirect(url_for("auth.login"))
        g.staff_user = staff

    @app.before_request
    def ensure_rfid_running():
        if RfidHardwareService.get_mode() == "serial" and not RfidHardwareService.is_running():
            RfidHardwareService.start()

    @app.route("/")
    def dashboard():
        alert_result = check_and_send_due_alerts()
        now = utcnow_naive()
        total_books = db.session.query(db.func.sum(Book.total_qty)).scalar() or 0
        available_books = db.session.query(db.func.sum(Book.available_qty)).scalar() or 0
        total_members = Member.query.count()
        active_members = Member.query.filter_by(status="Active").count()
        issued_books = Transaction.query.filter_by(return_date=None).count()
        overdue_count = Transaction.query.filter(
            Transaction.return_date.is_(None), Transaction.due_date < now
        ).count()
        pending_fines = (
            db.session.query(db.func.coalesce(db.func.sum(Transaction.fine_amount), 0))
            .filter(Transaction.fine_paid.is_(False), Transaction.fine_amount > 0)
            .scalar() or 0
        )
        pending_reservations = Reservation.query.filter_by(status="Pending").count()
        threshold = get_low_stock_threshold()
        low_stock_books = Book.query.filter(Book.available_qty <= threshold).count()

        recent_transactions = (
            Transaction.query.order_by(Transaction.issue_date.desc()).limit(8).all()
        )
        upcoming_due = (
            Transaction.query.filter(
                Transaction.return_date.is_(None),
                Transaction.due_date >= now,
                Transaction.due_date <= now + timedelta(days=3),
            )
            .order_by(Transaction.due_date)
            .limit(5)
            .all()
        )
        overdue_list = (
            Transaction.query.filter(
                Transaction.return_date.is_(None), Transaction.due_date < now
            )
            .order_by(Transaction.due_date)
            .limit(5)
            .all()
        )

        category_stats = (
            db.session.query(Book.category, func.count(Book.id))
            .group_by(Book.category)
            .all()
        )
        if db.engine.dialect.name == "postgresql":
            month_label = func.to_char(Transaction.issue_date, "Mon")
        else:
            month_label = func.strftime("%b", Transaction.issue_date)
        monthly_issues = (
            db.session.query(month_label.label("month"), func.count(Transaction.id))
            .group_by(month_label)
            .limit(6)
            .all()
        )

        pending_requests = BookRequest.query.filter_by(status="Pending").count()
        active_notices = Notice.query.filter_by(is_active=True).order_by(Notice.created_at.desc()).limit(3).all()

        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        issues_today = Transaction.query.filter(Transaction.issue_date >= today_start).count()
        returns_today = Transaction.query.filter(
            Transaction.return_date.isnot(None),
            Transaction.return_date >= today_start,
        ).count()
        lost_damaged = Book.query.filter(Book.book_status.in_(["Lost", "Damaged"])).count()
        expired_members = Member.query.filter(
            Member.expiry_date.isnot(None),
            Member.expiry_date < now.date(),
        ).count()
        expiring_soon = (
            Member.query.filter(
                Member.status == "Active",
                Member.expiry_date.isnot(None),
                Member.expiry_date >= now.date(),
                Member.expiry_date <= now.date() + timedelta(days=30),
            )
            .order_by(Member.expiry_date)
            .limit(5)
            .all()
        )
        recent_activity = (
            ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(10).all()
        )
        popular_books = (
            db.session.query(Book, func.count(Transaction.id).label("issue_count"))
            .join(Transaction, Book.id == Transaction.book_id)
            .group_by(Book.id)
            .order_by(func.count(Transaction.id).desc())
            .limit(5)
            .all()
        )
        low_stock_list = (
            Book.query.filter(Book.available_qty <= threshold)
            .order_by(Book.available_qty, Book.title)
            .limit(5)
            .all()
        )
        pending_requests_list = (
            BookRequest.query.filter_by(status="Pending")
            .order_by(BookRequest.request_date.desc())
            .limit(5)
            .all()
        )
        pending_damage_reports = BookDamageReport.query.filter_by(status="Pending").count()
        recent_damage_reports = (
            BookDamageReport.query.order_by(BookDamageReport.created_at.desc()).limit(6).all()
        )

        week_labels = []
        week_issues = []
        week_returns = []
        for i in range(6, -1, -1):
            day = (now - timedelta(days=i)).date()
            week_labels.append(day.strftime("%d %b"))
            day_start = datetime.combine(day, datetime.min.time())
            day_end = day_start + timedelta(days=1)
            week_issues.append(
                Transaction.query.filter(
                    Transaction.issue_date >= day_start,
                    Transaction.issue_date < day_end,
                ).count()
            )
            week_returns.append(
                Transaction.query.filter(
                    Transaction.return_date.isnot(None),
                    Transaction.return_date >= day_start,
                    Transaction.return_date < day_end,
                ).count()
            )

        rfid_status = RfidHardwareService.check_connection()

        return render_template(
            "dashboard.html",
            total_books=total_books,
            available_books=available_books,
            total_members=total_members,
            active_members=active_members,
            issued_books=issued_books,
            overdue_count=overdue_count,
            pending_fines=pending_fines,
            pending_reservations=pending_reservations,
            low_stock_books=low_stock_books,
            recent_transactions=recent_transactions,
            upcoming_due=upcoming_due,
            overdue_list=overdue_list,
            category_stats=category_stats,
            monthly_issues=monthly_issues,
            sms_sent_today=SmsLog.query.filter(db.func.date(SmsLog.sent_at) == now.date()).count(),
            alert_result=alert_result,
            pending_requests=pending_requests,
            active_notices=active_notices,
            issues_today=issues_today,
            returns_today=returns_today,
            lost_damaged=lost_damaged,
            expired_members=expired_members,
            expiring_soon=expiring_soon,
            recent_activity=recent_activity,
            popular_books=popular_books,
            low_stock_list=low_stock_list,
            pending_requests_list=pending_requests_list,
            pending_damage_reports=pending_damage_reports,
            recent_damage_reports=recent_damage_reports,
            week_labels=week_labels,
            week_issues=week_issues,
            week_returns=week_returns,
            rfid_status=rfid_status,
            now=now,
        )

    @app.route("/api/dashboard/chart-data")
    def chart_data():
        category_stats = (
            db.session.query(Book.category, func.count(Book.id))
            .group_by(Book.category)
            .all()
        )
        status_counts = {
            "available": db.session.query(func.sum(Book.available_qty)).scalar() or 0,
            "issued": Transaction.query.filter_by(return_date=None).count(),
        }
        return jsonify({
            "categories": {"labels": [c[0] for c in category_stats], "data": [c[1] for c in category_stats]},
            "status": status_counts,
        })

    csrf.exempt(chart_data)

    from routes.member_portal import get_thread, reply_to_thread
    from routes.admin import portal_messages_get_thread, portal_messages_reply
    from routes.transactions import validate_rfid

    csrf.exempt(get_thread)
    csrf.exempt(reply_to_thread)
    csrf.exempt(portal_messages_get_thread)
    csrf.exempt(portal_messages_reply)
    csrf.exempt(validate_rfid)

    return app


def seed_sample_data():
    if Book.query.first():
        return

    seed_default_settings()
    seed_default_categories()

    books = [
        ("BOOK-001", "9780743273565", "The Great Gatsby", "F. Scott Fitzgerald", "Scribner", "Fiction", "A1-01", 3),
        ("BOOK-002", "9780061120084", "To Kill a Mockingbird", "Harper Lee", "Harper", "Fiction", "A1-02", 2),
        ("BOOK-003", "9780451524935", "1984", "George Orwell", "Signet", "Dystopian", "A5-01", 4),
        ("BOOK-004", "9780141439518", "Pride and Prejudice", "Jane Austen", "Penguin", "Romance", "A4-01", 2),
        ("BOOK-005", "9780316769488", "The Catcher in the Rye", "J.D. Salinger", "Little Brown", "Fiction", "A1-03", 1),
        ("BOOK-006", "9780062316097", "Sapiens", "Yuval Noah Harari", "Harper", "Non-Fiction", "A2-01", 3),
        ("BOOK-007", "9780132350884", "Clean Code", "Robert C. Martin", "Prentice Hall", "Technology", "B1-01", 2),
        ("BOOK-008", "9780262046305", "Introduction to Algorithms", "CLRS", "MIT Press", "Technology", "B1-02", 1),
        ("BOOK-009", "9780547928227", "The Hobbit", "J.R.R. Tolkien", "Houghton", "Fantasy", "A3-01", 3),
        ("BOOK-010", "9780735211292", "Atomic Habits", "James Clear", "Avery", "Self-Help", "C1-01", 2),
    ]

    for tag, isbn, title, author, pub, category, shelf, qty in books:
        db.session.add(Book(
            rfid_tag=tag, isbn=isbn, title=title, author=author,
            publisher=pub, category=category, shelf_location=shelf,
            total_qty=qty, available_qty=qty,
        ))

    members = [
        ("MEM-CARD-001", "Alice Johnson", "alice@email.com", "9876543210", "Premium", "123 Main St"),
        ("MEM-CARD-002", "Bob Smith", "bob@email.com", "9876543211", "Standard", "456 Oak Ave"),
        ("MEM-CARD-003", "Carol Williams", "carol@email.com", "9876543212", "Premium", "789 Pine Rd"),
        ("MEM-CARD-004", "David Brown", "david@email.com", "9876543213", "Standard", "321 Elm St"),
        ("MEM-CARD-005", "Eva Davis", "eva@email.com", "9876543214", "Student", "654 Maple Dr"),
    ]

    expiry = datetime.now(timezone.utc).date() + timedelta(days=365)
    for card, name, email, phone, mtype, addr in members:
        db.session.add(Member(
            rfid_card=card, name=name, email=email, phone=phone,
            membership_type=mtype, address=addr, expiry_date=expiry,
        ))

    db.session.commit()

    alice = Member.query.filter_by(rfid_card="MEM-CARD-001").first()
    bob = Member.query.filter_by(rfid_card="MEM-CARD-002").first()
    book1 = Book.query.filter_by(rfid_tag="BOOK-001").first()
    book3 = Book.query.filter_by(rfid_tag="BOOK-003").first()
    book5 = Book.query.filter_by(rfid_tag="BOOK-005").first()

    now = utcnow_naive()
    issue1 = Transaction(
        book_id=book1.id, member_id=alice.id,
        issue_date=now - timedelta(days=20), due_date=now - timedelta(days=6),
        receipt_no="RCP-DEMO-001",
    )
    issue2 = Transaction(
        book_id=book3.id, member_id=bob.id,
        issue_date=now - timedelta(days=5), due_date=now + timedelta(days=9),
        receipt_no="RCP-DEMO-002",
    )
    issue3 = Transaction(
        book_id=book5.id, member_id=alice.id,
        issue_date=now - timedelta(days=30), due_date=now - timedelta(days=16),
        return_date=now - timedelta(days=10), fine_amount=12.0, fine_paid=False,
        receipt_no="RCP-DEMO-003",
    )

    book1.available_qty -= 1
    book3.available_qty -= 1

    db.session.add_all([issue1, issue2, issue3])

    db.session.commit()


def seed_sample_notices():
    if Notice.query.first():
        return
    notices = [
        ("Library Timing", "Library open: Mon-Sat 9AM-7PM, Sunday 10AM-4PM. Return books on time!", "High"),
        ("New Books Arrived", "50+ new Technology and Fiction books added this week!", "Normal"),
        ("Fine Reminder", "Overdue fine: Rs.2 per day. Clear fines to continue borrowing.", "High"),
    ]
    for title, msg, pri in notices:
        db.session.add(Notice(title=title, message=msg, priority=pri))
    db.session.commit()


app = create_app()

if __name__ == "__main__":
    with app.app_context():
        upgrade_database()
        ensure_upload_folder()
        seed_default_settings()
        seed_default_categories()
        seed_sample_data()
        seed_sample_notices()
        if RfidHardwareService.get_mode() == "serial":
            ok, msg = RfidHardwareService.start()
            if ok:
                print(f"RFID Reader: {msg}")
    debug = app.config.get("DEBUG", True)
    app.run(debug=debug, host="0.0.0.0", port=5000)
