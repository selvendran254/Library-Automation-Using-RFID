from datetime import timedelta

from functools import wraps

from flask import (
    Blueprint,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from models import db
from models.book import Book
from models.book_request import BookRequest
from models.damage_report import BookDamageReport
from models.member_message import MemberPortalThread
from models.member import Member
from models.notice import Notice
from models.renewal_request import MembershipRenewalRequest
from models.reservation import Reservation
from models.sms_log import SmsLog
from models.transaction import Transaction
from utils.auth import staff_login_required
from utils.helpers import (
    generate_portal_token,
    get_fine_per_day,
    get_loan_days,
    get_max_books,
    get_max_renewals,
    get_renewal_days,
    get_reservation_hold_days,
    log_activity,
    portal_token_valid,
    revoke_portal_token,
    utcnow_naive,
)
from utils.i18n import get_lang, t
from utils.otp_service import issue_otp, normalize_otp_code, normalize_phone, phones_match, verify_otp as verify_otp_code
from utils.sms_service import notify_portal_link
from utils.upload_helpers import save_damage_photo
from utils.portal_chat import (
    append_member_message,
    build_thread_summaries,
    get_or_create_damage_thread,
    mark_thread_read_for_member,
    serialize_thread_messages,
)

member_portal_bp = Blueprint("member_portal", __name__, url_prefix="/portal")

OTP_SESSION_PHONE = "member_otp_phone"
OTP_SESSION_PURPOSE = "member_otp_purpose"

DAMAGE_TYPES = [
    "Cut / Torn Pages",
    "Cover Damage",
    "Water Damage",
    "Missing Pages",
    "Writing / Marks",
    "Other",
]


@member_portal_bp.context_processor
def inject_portal_member():
    member_id = session.get("member_id")
    if member_id:
        member = Member.query.get(member_id)
        if member:
            now = utcnow_naive()
            membership_days_left = None
            if member.expiry_date:
                membership_days_left = (member.expiry_date - now.date()).days
            max_books = get_max_books(member)
            active_count = member.active_books_count
            active_txns = member.transactions.filter_by(return_date=None).all()
            overdue_count = sum(1 for t in active_txns if t.is_overdue)
            pending_reservations = sum(
                1 for r in member.reservations if r.status == "Pending"
            )
            pending_requests = sum(
                1 for r in member.book_requests if r.status == "Pending"
            )
            unread_messages = sum(
                1 for t in member.portal_threads if t.member_unread
            )
            return {
                "portal_member": member,
                "portal_unread_messages": unread_messages,
                "portal_max_books": max_books,
                "portal_membership_days_left": membership_days_left,
                "portal_borrow_slots_left": max(0, max_books - active_count),
                "portal_fine_per_day": get_fine_per_day(),
                "portal_loan_days": get_loan_days(),
                "portal_max_renewals": get_max_renewals(),
                "portal_renewal_days": get_renewal_days(),
                "portal_pending_fine": member.pending_fine,
                "portal_overdue_count": overdue_count,
                "portal_total_borrowed": member.transactions.count(),
                "portal_total_returned": member.transactions.filter(
                    Transaction.return_date.isnot(None)
                ).count(),
                "portal_pending_reservations": pending_reservations,
                "portal_pending_requests": pending_requests,
                "portal_current_books": member.current_books,
            }
    return {}


@member_portal_bp.context_processor
def inject_portal_i18n():
    lang = get_lang(session)
    return {"portal_lang": lang, "t": lambda key: t(key, lang)}


def member_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        member_id = session.get("member_id")
        if not member_id:
            flash("Please login to view your library account.", "warning")
            return redirect(url_for("member_portal.login_page"))
        member = Member.query.get(member_id)
        if not member or member.status == "Suspended":
            session.pop("member_id", None)
            flash("Access denied. Contact the library.", "danger")
            return redirect(url_for("member_portal.login_page"))
        g.member = member
        return f(*args, **kwargs)

    return decorated


def _portal_access_url(token, external=False):
    return url_for("member_portal.access", token=token, _external=external)


def _build_portal_inbox(member, limit=50):
    """Thread summaries for the dashboard Messages list."""
    return build_thread_summaries(member, limit=limit)


def _member_portal_context(member):
    now = utcnow_naive()
    active = member.transactions.filter_by(return_date=None).order_by(Transaction.due_date).all()
    history = (
        Transaction.query.filter_by(member_id=member.id)
        .order_by(Transaction.issue_date.desc())
        .limit(50)
        .all()
    )
    overdue_books = [t for t in active if t.is_overdue]
    upcoming_due = [
        t for t in active
        if not t.is_overdue and (t.due_date.date() - now.date()).days <= 3
    ]
    reservations = sorted(
        [r for r in member.reservations if r.status == "Pending"],
        key=lambda r: r.reserved_date,
        reverse=True,
    )
    book_requests = sorted(member.book_requests, key=lambda r: r.request_date, reverse=True)
    pending_requests = [r for r in book_requests if r.status == "Pending"]
    unpaid_fines = [
        t for t in member.transactions
        if t.return_date and t.fine_amount > 0 and not t.fine_paid
    ]
    recent_sms = (
        SmsLog.query.filter_by(member_id=member.id)
        .order_by(SmsLog.sent_at.desc())
        .limit(5)
        .all()
    )
    notices = Notice.query.filter_by(is_active=True).order_by(Notice.created_at.desc()).limit(5).all()
    damage_reports = (
        BookDamageReport.query.filter_by(member_id=member.id)
        .order_by(BookDamageReport.created_at.desc())
        .limit(10)
        .all()
    )
    unread_admin_messages = MemberPortalThread.query.filter_by(
        member_id=member.id, member_unread=True
    ).count()
    portal_inbox = _build_portal_inbox(member)
    portal_inbox_preview = portal_inbox[:4]
    max_books = get_max_books(member)
    total_borrowed = member.transactions.count()
    total_returned = member.transactions.filter(Transaction.return_date.isnot(None)).count()
    membership_days_left = None
    if member.expiry_date:
        membership_days_left = (member.expiry_date - now.date()).days

    fine_per_day = get_fine_per_day()
    for txn in active:
        if txn.is_overdue:
            txn.estimated_fine = (now.date() - txn.due_date.date()).days * fine_per_day
            txn.days_overdue = (now.date() - txn.due_date.date()).days
        else:
            txn.estimated_fine = 0
            txn.days_overdue = 0

    return {
        "member": member,
        "active": active,
        "history": history,
        "overdue_books": overdue_books,
        "upcoming_due": upcoming_due,
        "reservations": reservations,
        "book_requests": book_requests,
        "pending_requests": pending_requests,
        "unpaid_fines": unpaid_fines,
        "recent_sms": recent_sms,
        "notices": notices,
        "damage_reports": damage_reports,
        "portal_inbox": portal_inbox,
        "portal_inbox_preview": portal_inbox_preview,
        "unread_admin_messages": unread_admin_messages,
        "damage_types": DAMAGE_TYPES,
        "max_books": max_books,
        "max_renewals": get_max_renewals(),
        "renewal_days": get_renewal_days(),
        "loan_days": get_loan_days(),
        "fine_per_day": fine_per_day,
        "borrow_slots_left": max(0, max_books - member.active_books_count),
        "total_borrowed": total_borrowed,
        "total_returned": total_returned,
        "membership_days_left": membership_days_left,
        "now": now,
    }


@member_portal_bp.route("/admin")
@staff_login_required
def admin_home():
    members = Member.query.order_by(Member.name).all()
    selected_id = request.args.get("member_id", type=int)
    selected = Member.query.get(selected_id) if selected_id else None
    portal_url = None
    if selected and portal_token_valid(selected):
        portal_url = _portal_access_url(selected.portal_token, external=True)
    return render_template(
        "portal/admin.html",
        members=members,
        selected=selected,
        portal_url=portal_url,
    )


@member_portal_bp.route("/admin/generate/<int:member_id>", methods=["POST"])
@staff_login_required
def admin_generate_link(member_id):
    member = Member.query.get_or_404(member_id)
    token = generate_portal_token(member)
    portal_url = _portal_access_url(token, external=True)
    log_activity(
        "PORTAL",
        "Member",
        member.id,
        f"Portal access link generated for '{member.name}'",
    )
    flash(f"Portal link generated for {member.name}. Valid until {member.portal_token_expires.strftime('%d-%m-%Y')}.", "success")
    return redirect(url_for("member_portal.admin_home", member_id=member.id, link=portal_url))


@member_portal_bp.route("/admin/revoke/<int:member_id>", methods=["POST"])
@staff_login_required
def admin_revoke_link(member_id):
    member = Member.query.get_or_404(member_id)
    revoke_portal_token(member)
    log_activity("PORTAL", "Member", member.id, f"Portal access revoked for '{member.name}'")
    flash(f"Portal access revoked for {member.name}.", "warning")
    return redirect(url_for("member_portal.admin_home", member_id=member.id))


@member_portal_bp.route("/admin/send-sms/<int:member_id>", methods=["POST"])
@staff_login_required
def admin_send_sms(member_id):
    member = Member.query.get_or_404(member_id)
    if not portal_token_valid(member):
        token = generate_portal_token(member)
    else:
        token = member.portal_token
    portal_url = _portal_access_url(token, external=True)
    notify_portal_link(member, portal_url)
    flash(f"Portal link sent via SMS to {member.phone}.", "success")
    return redirect(url_for("member_portal.admin_home", member_id=member.id, link=portal_url))


@member_portal_bp.route("/login")
def login_page():
    if session.get("member_id"):
        return redirect(url_for("member_portal.dashboard"))
    return render_template("portal/login.html")


@member_portal_bp.route("/send-otp", methods=["POST"])
def send_otp():
    phone = request.form.get("phone", "").strip()
    if not phone:
        flash("Please enter your mobile number.", "danger")
        return redirect(url_for("member_portal.login_page"))

    members = Member.query.filter_by(status="Active").all()
    member = next((m for m in members if phones_match(m.phone, phone)), None)
    if not member:
        flash("No active member account found for this number.", "danger")
        return redirect(url_for("member_portal.login_page"))

    otp, code, err = issue_otp(phone, "member_login", "member", member.id, "member login")
    if err:
        flash(err, "danger")
        return redirect(url_for("member_portal.login_page"))

    session[OTP_SESSION_PHONE] = normalize_phone(phone)
    session[OTP_SESSION_PURPOSE] = "member_login"
    flash(f"OTP sent to {normalize_phone(phone)}. Check your SMS.", "success")
    return redirect(url_for("member_portal.verify_otp_page"))


@member_portal_bp.route("/verify-otp", methods=["GET", "POST"])
def verify_otp_page():
    if session.get("member_id"):
        return redirect(url_for("member_portal.dashboard"))

    phone = session.get(OTP_SESSION_PHONE)
    purpose = session.get(OTP_SESSION_PURPOSE)
    if not phone or purpose != "member_login":
        flash("Please enter your mobile number first.", "warning")
        return redirect(url_for("member_portal.login_page"))

    if request.method == "POST":
        code = normalize_otp_code(request.form.get("otp", ""))
        if len(code) != 6:
            flash("Please enter the 6-digit OTP from your SMS.", "danger")
            return render_template("auth/verify_otp.html", phone=phone, user_type="member")

        otp, err = verify_otp_code(phone, purpose, code)
        if err:
            flash("Invalid OTP. Please check the SMS and try again." if "Invalid" in err else err, "danger")
            return render_template("auth/verify_otp.html", phone=phone, user_type="member")

        member = Member.query.get(otp.user_id)
        if not member or member.status == "Suspended":
            flash("Account not found or suspended.", "danger")
            return redirect(url_for("member_portal.login_page"))

        session["member_id"] = member.id
        session.pop(OTP_SESSION_PHONE, None)
        session.pop(OTP_SESSION_PURPOSE, None)
        member.portal_last_login = utcnow_naive()
        db.session.commit()
        log_activity("PORTAL_LOGIN", "Member", member.id, f"Member OTP login '{member.name}'", user_label=member.name)
        flash(f"Welcome, {member.name}!", "success")
        return redirect(url_for("member_portal.dashboard"))

    return render_template("auth/verify_otp.html", phone=phone, user_type="member")


@member_portal_bp.route("/access/<token>", methods=["GET", "POST"])
def access(token):
    member = Member.query.filter_by(portal_token=token).first()
    if not member or not portal_token_valid(member):
        flash("This link is invalid or has expired. Please contact the library for a new link.", "danger")
        return render_template("portal/login.html")

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if email != member.email.strip().lower():
            flash("Email does not match our records. Please use your registered email.", "danger")
            return render_template("portal/access.html", member=member, token=token)

        session["member_id"] = member.id
        member.portal_last_login = utcnow_naive()
        db.session.commit()
        log_activity(
            "PORTAL_LOGIN",
            "Member",
            member.id,
            f"Member '{member.name}' logged into portal",
            user_label=member.name,
        )
        flash(f"Welcome, {member.name}!", "success")
        return redirect(url_for("member_portal.dashboard"))

    return render_template("portal/access.html", member=member, token=token)


@member_portal_bp.route("/messages")
@member_required
def messages_page():
    ctx = _member_portal_context(g.member)
    return render_template("portal/messages.html", **ctx)


@member_portal_bp.route("/")
@member_required
def dashboard():
    ctx = _member_portal_context(g.member)
    return render_template("portal/dashboard.html", **ctx)


@member_portal_bp.route("/api/threads/<int:thread_id>")
@member_required
def get_thread(thread_id):
    thread = MemberPortalThread.query.filter_by(
        id=thread_id, member_id=g.member.id
    ).first_or_404()
    mark_thread_read_for_member(thread)
    return jsonify({
        "id": thread.id,
        "subject": thread.subject,
        "kind": thread.kind,
        "status": thread.damage_report.status if thread.damage_report else None,
        "messages": serialize_thread_messages(thread),
    })


@member_portal_bp.route("/api/threads/<int:thread_id>/reply", methods=["POST"])
@member_required
def reply_to_thread(thread_id):
    thread = MemberPortalThread.query.filter_by(
        id=thread_id, member_id=g.member.id
    ).first_or_404()
    body = (request.json or {}).get("body", "").strip() if request.is_json else request.form.get("body", "").strip()
    if not body:
        if request.is_json:
            return jsonify({"error": "Please type a message."}), 400
        flash("Please type a message.", "danger")
        return redirect(url_for("member_portal.dashboard"))

    append_member_message(thread, body)
    log_activity(
        "PORTAL_REPLY",
        "Member",
        g.member.id,
        f"Member '{g.member.name}' replied in portal thread #{thread.id}",
        user_label=g.member.name,
    )

    if request.is_json:
        return jsonify({
            "ok": True,
            "messages": serialize_thread_messages(thread),
        })
    flash("Message sent.", "success")
    return redirect(request.referrer or url_for("member_portal.messages_page"))


@member_portal_bp.route("/request-book", methods=["GET", "POST"])
@member_required
def request_book():
    if request.method == "POST":
        title = request.form.get("book_title", "").strip()
        if not title:
            flash("Please enter a book title.", "danger")
            return redirect(url_for("member_portal.request_book"))
        req = BookRequest(
            member_id=g.member.id,
            book_title=title,
            author=request.form.get("author", "").strip() or None,
            notes=request.form.get("notes", "").strip() or None,
        )
        db.session.add(req)
        db.session.commit()
        log_activity("REQUEST", "BookRequest", req.id, f"Portal book request: {title}", user_label=g.member.name)
        flash("Book request submitted. Library staff will review it.", "success")
        return redirect(url_for("member_portal.dashboard"))
    return render_template("portal/request_book.html", member=g.member)


@member_portal_bp.route("/reserve", methods=["GET", "POST"])
@member_required
def reserve_book():
    books = Book.query.filter(Book.available_qty > 0, Book.book_status == "Active").order_by(Book.title).all()
    if request.method == "POST":
        book_id = request.form.get("book_id", type=int)
        book = Book.query.get(book_id)
        if not book or book.available_qty <= 0:
            flash("Please select an available book.", "danger")
            return redirect(url_for("member_portal.reserve_book"))
        existing = Reservation.query.filter_by(
            book_id=book.id, member_id=g.member.id, status="Pending"
        ).first()
        if existing:
            flash("You already have a pending reservation for this book.", "warning")
            return redirect(url_for("member_portal.dashboard"))
        now = utcnow_naive()
        reservation = Reservation(
            book_id=book.id,
            member_id=g.member.id,
            reserved_date=now,
            expiry_date=now + timedelta(days=get_reservation_hold_days()),
            notes=request.form.get("notes", "").strip() or "Via member portal",
        )
        db.session.add(reservation)
        db.session.commit()
        log_activity("RESERVE", "Book", book.id, f"Portal reservation by {g.member.name}", user_label=g.member.name)
        flash(f"Reserved '{book.title}'. Visit library to collect.", "success")
        return redirect(url_for("member_portal.dashboard"))
    return render_template("portal/reserve.html", member=g.member, books=books)


@member_portal_bp.route("/renew-membership", methods=["GET", "POST"])
@member_required
def renew_membership_request():
    pending = MembershipRenewalRequest.query.filter_by(
        member_id=g.member.id, status="Pending"
    ).first()
    if request.method == "POST":
        if pending:
            flash("You already have a pending renewal request.", "warning")
            return redirect(url_for("member_portal.dashboard"))
        months = int(request.form.get("months", 12))
        if months not in (6, 12, 24):
            months = 12
        req = MembershipRenewalRequest(
            member_id=g.member.id,
            months=months,
            member_notes=request.form.get("notes", "").strip() or None,
        )
        db.session.add(req)
        db.session.commit()
        log_activity("RENEW_REQ", "Member", g.member.id, f"Renewal request {months}mo", user_label=g.member.name)
        flash("Renewal request sent to library admin.", "success")
        return redirect(url_for("member_portal.dashboard"))
    return render_template("portal/renew_membership.html", member=g.member, pending=pending)


@member_portal_bp.route("/set-lang/<lang>")
def set_language(lang):
    if lang in ("en", "ta"):
        session["portal_lang"] = lang
    return redirect(request.referrer or url_for("member_portal.login_page"))


@member_portal_bp.route("/login-rfid", methods=["POST"])
def login_rfid():
    rfid = request.form.get("rfid_card", "").strip()
    member = Member.query.filter_by(rfid_card=rfid).first()
    if not member or member.status == "Suspended":
        flash("Invalid or suspended member card.", "danger")
        return redirect(url_for("member_portal.login_page"))
    session["member_id"] = member.id
    member.portal_last_login = utcnow_naive()
    db.session.commit()
    log_activity("PORTAL_LOGIN", "Member", member.id, f"RFID login by {member.name}", user_label=member.name)
    flash(f"Welcome, {member.name}!", "success")
    return redirect(url_for("member_portal.dashboard"))


@member_portal_bp.route("/history")
@member_required
def history():
    ctx = _member_portal_context(g.member)
    return render_template("portal/history.html", **ctx)


@member_portal_bp.route("/report-damage", methods=["GET", "POST"])
@member_required
def report_damage():
    member = g.member
    active = member.transactions.filter_by(return_date=None).order_by(Transaction.due_date).all()
    selected_txn_id = request.args.get("transaction_id", type=int) or request.form.get("transaction_id", type=int)

    if request.method == "POST":
        txn_id = request.form.get("transaction_id", type=int)
        damage_type = request.form.get("damage_type", "").strip()
        description = request.form.get("description", "").strip()
        photo = request.files.get("photo")

        txn = Transaction.query.filter_by(id=txn_id, member_id=member.id, return_date=None).first()
        if not txn:
            flash("Please select a valid book from your current issues.", "danger")
            return redirect(url_for("member_portal.report_damage"))

        if damage_type not in DAMAGE_TYPES:
            flash("Please select a damage type.", "danger")
            return redirect(url_for("member_portal.report_damage", transaction_id=txn_id))

        filename, error = save_damage_photo(photo)
        if error:
            flash(error, "danger")
            return redirect(url_for("member_portal.report_damage", transaction_id=txn_id))

        report = BookDamageReport(
            member_id=member.id,
            book_id=txn.book_id,
            transaction_id=txn.id,
            damage_type=damage_type,
            description=description or None,
            photo_filename=filename,
        )
        db.session.add(report)
        db.session.commit()
        get_or_create_damage_thread(report)
        log_activity(
            "DAMAGE_REPORT",
            "Book",
            txn.book_id,
            f"Member '{member.name}' reported damage on '{txn.book.title}' ({damage_type})",
            user_label=member.name,
        )
        flash("Damage report submitted. Library staff will review your photo.", "success")
        return redirect(url_for("member_portal.dashboard"))

    return render_template(
        "portal/report_damage.html",
        member=member,
        active=active,
        damage_types=DAMAGE_TYPES,
        selected_txn_id=selected_txn_id,
    )


@member_portal_bp.route("/logout", methods=["POST"])
def logout():
    session.pop("member_id", None)
    flash("You have been logged out.", "info")
    return redirect(url_for("member_portal.login_page"))
