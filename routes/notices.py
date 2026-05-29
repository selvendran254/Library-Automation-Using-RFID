from flask import Blueprint, flash, redirect, render_template, request, url_for

from models import db
from models.notice import Notice
from utils.helpers import log_activity

notices_bp = Blueprint("notices", __name__, url_prefix="/notices")


@notices_bp.route("/")
def list_notices():
    notices = Notice.query.order_by(Notice.created_at.desc()).all()
    active = [n for n in notices if n.is_active]
    return render_template("notices/list.html", notices=notices, active_notices=active)


@notices_bp.route("/add", methods=["GET", "POST"])
def add_notice():
    if request.method == "POST":
        notice = Notice(
            title=request.form.get("title", "").strip(),
            message=request.form.get("message", "").strip(),
            priority=request.form.get("priority", "Normal"),
            is_active=request.form.get("is_active") == "on",
        )
        db.session.add(notice)
        db.session.commit()
        log_activity("CREATE", "Notice", notice.id, f"Notice '{notice.title}' posted")
        flash("Notice posted successfully.", "success")
        return redirect(url_for("notices.list_notices"))
    return render_template("notices/form.html", notice=None)


@notices_bp.route("/edit/<int:notice_id>", methods=["GET", "POST"])
def edit_notice(notice_id):
    notice = Notice.query.get_or_404(notice_id)
    if request.method == "POST":
        notice.title = request.form.get("title", "").strip()
        notice.message = request.form.get("message", "").strip()
        notice.priority = request.form.get("priority", "Normal")
        notice.is_active = request.form.get("is_active") == "on"
        db.session.commit()
        flash("Notice updated.", "success")
        return redirect(url_for("notices.list_notices"))
    return render_template("notices/form.html", notice=notice)


@notices_bp.route("/delete/<int:notice_id>", methods=["POST"])
def delete_notice(notice_id):
    notice = Notice.query.get_or_404(notice_id)
    db.session.delete(notice)
    db.session.commit()
    flash("Notice deleted.", "info")
    return redirect(url_for("notices.list_notices"))
