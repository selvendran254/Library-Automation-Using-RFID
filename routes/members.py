from datetime import timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for

from models import db
from models.member import Member
from models.member_message import MemberPortalThread
from models.renewal_request import MembershipRenewalRequest
from utils.portal_chat import append_admin_message, create_direct_thread
from models.transaction import Transaction
from utils.helpers import get_max_books, generate_portal_token, log_activity, portal_token_valid, revoke_portal_token, utcnow_naive
from utils.sms_service import notify_portal_link

members_bp = Blueprint("members", __name__, url_prefix="/members")


@members_bp.route("/")
def list_members():
    status = request.args.get("status", "")
    mtype = request.args.get("type", "")
    query = Member.query
    if status:
        query = query.filter_by(status=status)
    if mtype:
        query = query.filter_by(membership_type=mtype)
    members = query.order_by(Member.name).all()
    return render_template(
        "members/list.html",
        members=members,
        status_filter=status,
        type_filter=mtype,
    )


@members_bp.route("/<int:member_id>")
def member_detail(member_id):
    member = Member.query.get_or_404(member_id)
    active = member.transactions.filter_by(return_date=None).all()
    history = (
        Transaction.query.filter_by(member_id=member.id)
        .order_by(Transaction.issue_date.desc())
        .limit(30)
        .all()
    )
    reservations = [r for r in member.reservations if r.status == "Pending"]
    portal_url = None
    if portal_token_valid(member):
        portal_url = url_for("member_portal.access", token=member.portal_token, _external=True)
    display_link = request.args.get("link") or portal_url
    portal_threads = (
        MemberPortalThread.query.filter_by(member_id=member.id)
        .order_by(MemberPortalThread.updated_at.desc())
        .limit(10)
        .all()
    )
    return render_template(
        "members/detail.html",
        member=member,
        active=active,
        history=history,
        reservations=reservations,
        max_books=get_max_books(member),
        portal_url=portal_url,
        display_link=display_link,
        portal_threads=portal_threads,
    )


@members_bp.route("/add", methods=["GET", "POST"])
def add_member():
    if request.method == "POST":
        rfid_card = request.form.get("rfid_card", "").strip()
        if Member.query.filter_by(rfid_card=rfid_card).first():
            flash("RFID card already exists.", "danger")
            return render_template("members/form.html", member=None)

        expiry = request.form.get("expiry_date") or None
        member = Member(
            rfid_card=rfid_card,
            name=request.form.get("name", "").strip(),
            email=request.form.get("email", "").strip(),
            phone=request.form.get("phone", "").strip(),
            address=request.form.get("address", "").strip() or None,
            membership_type=request.form.get("membership_type", "Standard"),
            status=request.form.get("status", "Active"),
            expiry_date=expiry,
            notes=request.form.get("notes", "").strip() or None,
        )
        override = request.form.get("max_books_override", "").strip()
        if override:
            member.max_books_override = int(override)
        db.session.add(member)
        db.session.commit()
        log_activity("CREATE", "Member", member.id, f"Member '{member.name}' added")
        flash("Member added successfully.", "success")
        return redirect(url_for("members.list_members"))

    return render_template("members/form.html", member=None)


@members_bp.route("/edit/<int:member_id>", methods=["GET", "POST"])
def edit_member(member_id):
    member = Member.query.get_or_404(member_id)

    if request.method == "POST":
        rfid_card = request.form.get("rfid_card", "").strip()
        existing = Member.query.filter_by(rfid_card=rfid_card).first()
        if existing and existing.id != member.id:
            flash("RFID card already exists.", "danger")
            return render_template("members/form.html", member=member)

        member.rfid_card = rfid_card
        member.name = request.form.get("name", "").strip()
        member.email = request.form.get("email", "").strip()
        member.phone = request.form.get("phone", "").strip()
        member.address = request.form.get("address", "").strip() or None
        member.membership_type = request.form.get("membership_type", "Standard")
        member.status = request.form.get("status", "Active")
        member.expiry_date = request.form.get("expiry_date") or None
        member.notes = request.form.get("notes", "").strip() or None
        override = request.form.get("max_books_override", "").strip()
        member.max_books_override = int(override) if override else None
        db.session.commit()
        log_activity("UPDATE", "Member", member.id, f"Member '{member.name}' updated")
        flash("Member updated successfully.", "success")
        return redirect(url_for("members.list_members"))

    return render_template("members/form.html", member=member)


@members_bp.route("/delete/<int:member_id>", methods=["POST"])
def delete_member(member_id):
    member = Member.query.get_or_404(member_id)
    active_issues = member.transactions.filter_by(return_date=None).count()
    if active_issues > 0:
        flash("Cannot delete member with active book issues.", "danger")
        return redirect(url_for("members.list_members"))

    db.session.delete(member)
    db.session.commit()
    flash("Member deleted successfully.", "success")
    return redirect(url_for("members.list_members"))


@members_bp.route("/<int:member_id>/card")
def print_card(member_id):
    member = Member.query.get_or_404(member_id)
    from utils.helpers import get_max_books
    return render_template("members/library_card.html", member=member, max_books=get_max_books(member))


@members_bp.route("/<int:member_id>/renew", methods=["POST"])
def renew_membership(member_id):
    member = Member.query.get_or_404(member_id)
    months = int(request.form.get("months", 12))
    base = member.expiry_date or utcnow_naive().date()
    member.expiry_date = base + timedelta(days=months * 30)
    member.status = "Active"
    db.session.commit()
    log_activity("RENEW", "Member", member.id, f"Membership renewed for {months} months")
    flash(f"Membership renewed until {member.expiry_date.strftime('%d-%m-%Y')}.", "success")
    return redirect(url_for("members.member_detail", member_id=member.id))


@members_bp.route("/<int:member_id>/suspend", methods=["POST"])
def suspend_member(member_id):
    member = Member.query.get_or_404(member_id)
    member.status = "Suspended"
    reason = request.form.get("reason", "Policy violation")
    member.notes = (member.notes or "") + f"\n[Suspended: {reason}]"
    db.session.commit()
    log_activity("SUSPEND", "Member", member.id, f"Member suspended: {reason}")
    flash(f"Member {member.name} suspended.", "warning")
    return redirect(url_for("members.member_detail", member_id=member.id))


@members_bp.route("/<int:member_id>/portal-link", methods=["POST"])
def generate_portal_link(member_id):
    member = Member.query.get_or_404(member_id)
    token = generate_portal_token(member)
    portal_url = url_for("member_portal.access", token=token, _external=True)
    log_activity("PORTAL", "Member", member.id, f"Portal link generated for '{member.name}'")
    flash(f"Portal link created. Valid until {member.portal_token_expires.strftime('%d-%m-%Y')}.", "success")
    return redirect(url_for("members.member_detail", member_id=member.id, link=portal_url))


@members_bp.route("/<int:member_id>/portal-revoke", methods=["POST"])
def revoke_portal_link(member_id):
    member = Member.query.get_or_404(member_id)
    revoke_portal_token(member)
    log_activity("PORTAL", "Member", member.id, f"Portal access revoked for '{member.name}'")
    flash("Portal access revoked.", "warning")
    return redirect(url_for("members.member_detail", member_id=member.id))


@members_bp.route("/<int:member_id>/portal-sms", methods=["POST"])
def send_portal_sms(member_id):
    member = Member.query.get_or_404(member_id)
    if not portal_token_valid(member):
        token = generate_portal_token(member)
    else:
        token = member.portal_token
    portal_url = url_for("member_portal.access", token=token, _external=True)
    notify_portal_link(member, portal_url)
    flash(f"Portal link sent to {member.phone} via SMS.", "success")
    return redirect(url_for("members.member_detail", member_id=member.id, link=portal_url))


@members_bp.route("/<int:member_id>/portal-message", methods=["POST"])
def send_portal_message(member_id):
    member = Member.query.get_or_404(member_id)
    subject = request.form.get("subject", "").strip() or "Message from Library"
    message = request.form.get("message", "").strip()
    if not message:
        flash("Please enter a message for the member.", "danger")
        return redirect(url_for("members.member_detail", member_id=member.id))

    create_direct_thread(member.id, subject, message)
    log_activity(
        "MESSAGE",
        "Member",
        member.id,
        f"Admin sent portal message to '{member.name}'",
    )
    flash(f"Message sent to {member.name}. They can open it and chat in their portal.", "success")
    return redirect(url_for("members.member_detail", member_id=member.id))


@members_bp.route("/<int:member_id>/portal-thread/<int:thread_id>/reply", methods=["POST"])
def reply_portal_thread(member_id, thread_id):
    member = Member.query.get_or_404(member_id)
    thread = MemberPortalThread.query.filter_by(id=thread_id, member_id=member.id).first_or_404()
    message = request.form.get("message", "").strip()
    if not message:
        flash("Please enter a reply.", "danger")
        return redirect(url_for("members.member_detail", member_id=member.id))

    append_admin_message(thread, message)
    log_activity(
        "MESSAGE",
        "Member",
        member.id,
        f"Admin replied in portal thread #{thread.id} to '{member.name}'",
    )
    flash("Reply sent to member portal.", "success")
    return redirect(url_for("admin.portal_messages", thread=thread_id))


@members_bp.route("/renewal-requests")
def list_renewal_requests():
    status = request.args.get("status", "Pending")
    query = MembershipRenewalRequest.query
    if status:
        query = query.filter_by(status=status)
    requests_list = query.order_by(MembershipRenewalRequest.requested_at.desc()).all()
    return render_template(
        "members/renewal_requests.html",
        requests_list=requests_list,
        status_filter=status,
    )


@members_bp.route("/renewal-requests/<int:req_id>/approve", methods=["POST"])
def approve_renewal_request(req_id):
    from flask import g

    req = MembershipRenewalRequest.query.get_or_404(req_id)
    member = req.member
    base = member.expiry_date or utcnow_naive().date()
    member.expiry_date = base + timedelta(days=req.months * 30)
    member.status = "Active"
    req.status = "Approved"
    req.reviewed_at = utcnow_naive()
    if getattr(g, "staff_user", None):
        req.reviewed_by_id = g.staff_user.id
    db.session.commit()
    log_activity("RENEW", "Member", member.id, f"Portal renewal approved ({req.months} months)")
    flash(f"Membership renewed for {member.name} until {member.expiry_date.strftime('%d-%m-%Y')}.", "success")
    return redirect(url_for("members.list_renewal_requests"))


@members_bp.route("/renewal-requests/<int:req_id>/reject", methods=["POST"])
def reject_renewal_request(req_id):
    from flask import g

    req = MembershipRenewalRequest.query.get_or_404(req_id)
    req.status = "Rejected"
    req.admin_notes = request.form.get("admin_notes", "").strip() or req.admin_notes
    req.reviewed_at = utcnow_naive()
    if getattr(g, "staff_user", None):
        req.reviewed_by_id = g.staff_user.id
    db.session.commit()
    flash("Renewal request rejected.", "info")
    return redirect(url_for("members.list_renewal_requests"))
