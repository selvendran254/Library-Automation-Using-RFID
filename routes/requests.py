from flask import Blueprint, flash, redirect, render_template, request, url_for

from models import db
from models.book_request import BookRequest
from models.member import Member
from utils.helpers import log_activity

requests_bp = Blueprint("book_requests", __name__, url_prefix="/requests")


@requests_bp.route("/")
def list_requests():
    status = request.args.get("status", "")
    query = BookRequest.query
    if status:
        query = query.filter_by(status=status)
    requests_list = query.order_by(BookRequest.request_date.desc()).all()
    pending_count = BookRequest.query.filter_by(status="Pending").count()
    return render_template(
        "requests/list.html",
        requests_list=requests_list,
        status_filter=status,
        pending_count=pending_count,
    )


@requests_bp.route("/add", methods=["GET", "POST"])
def add_request():
    members = Member.query.filter_by(status="Active").order_by(Member.name).all()
    if request.method == "POST":
        req = BookRequest(
            member_id=int(request.form.get("member_id")),
            book_title=request.form.get("book_title", "").strip(),
            author=request.form.get("author", "").strip() or None,
            notes=request.form.get("notes", "").strip() or None,
        )
        db.session.add(req)
        db.session.commit()
        log_activity("REQUEST", "BookRequest", req.id, f"Book request: {req.book_title}")
        flash("Book request submitted.", "success")
        return redirect(url_for("book_requests.list_requests"))
    return render_template("requests/form.html", members=members)


@requests_bp.route("/<int:req_id>/approve", methods=["POST"])
def approve_request(req_id):
    req = BookRequest.query.get_or_404(req_id)
    req.status = "Approved"
    db.session.commit()
    flash(f"Request for '{req.book_title}' approved.", "success")
    return redirect(url_for("book_requests.list_requests"))


@requests_bp.route("/<int:req_id>/reject", methods=["POST"])
def reject_request(req_id):
    req = BookRequest.query.get_or_404(req_id)
    req.status = "Rejected"
    db.session.commit()
    flash("Request rejected.", "info")
    return redirect(url_for("book_requests.list_requests"))


@requests_bp.route("/<int:req_id>/fulfill", methods=["POST"])
def fulfill_request(req_id):
    req = BookRequest.query.get_or_404(req_id)
    req.status = "Fulfilled"
    db.session.commit()
    flash("Request marked as fulfilled.", "success")
    return redirect(url_for("book_requests.list_requests"))
