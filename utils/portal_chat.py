from models import db
from models.damage_report import BookDamageReport
from models.member_message import (
    MemberPortalChatMessage,
    MemberPortalMessage,
    MemberPortalThread,
)
from utils.helpers import utcnow_naive


def _touch_thread(thread):
    thread.updated_at = utcnow_naive()


def get_or_create_damage_thread(report):
    thread = MemberPortalThread.query.filter_by(damage_report_id=report.id).first()
    if thread:
        return thread

    book_title = report.book.title if report.book else "Book"
    thread = MemberPortalThread(
        member_id=report.member_id,
        subject=f"{book_title} · {report.damage_type}",
        kind="damage",
        damage_report_id=report.id,
        updated_at=report.created_at or utcnow_naive(),
        admin_unread=True,
    )
    db.session.add(thread)
    db.session.flush()

    intro = report.description or f"I reported damage: {report.damage_type}"
    db.session.add(
        MemberPortalChatMessage(
            thread_id=thread.id,
            sender="member",
            body=intro,
            created_at=report.created_at or utcnow_naive(),
        )
    )
    db.session.commit()
    return thread


def create_direct_thread(member_id, subject, admin_body):
    now = utcnow_naive()
    thread = MemberPortalThread(
        member_id=member_id,
        subject=subject or "Message from Library",
        kind="direct",
        updated_at=now,
        member_unread=True,
    )
    db.session.add(thread)
    db.session.flush()
    db.session.add(
        MemberPortalChatMessage(
            thread_id=thread.id,
            sender="admin",
            body=admin_body,
            created_at=now,
        )
    )
    db.session.commit()
    return thread


def append_admin_message(thread, body, sync_damage_report=True):
    now = utcnow_naive()
    db.session.add(
        MemberPortalChatMessage(
            thread_id=thread.id,
            sender="admin",
            body=body,
            created_at=now,
        )
    )
    thread.updated_at = now
    thread.member_unread = True
    thread.admin_unread = False

    if sync_damage_report and thread.damage_report_id:
        report = BookDamageReport.query.get(thread.damage_report_id)
        if report:
            report.member_message = body
            report.member_message_at = now
            report.member_message_read = False

    db.session.commit()
    return now


def append_member_message(thread, body):
    now = utcnow_naive()
    db.session.add(
        MemberPortalChatMessage(
            thread_id=thread.id,
            sender="member",
            body=body,
            created_at=now,
        )
    )
    thread.updated_at = now
    thread.admin_unread = True
    thread.member_unread = False
    db.session.commit()
    return now


def mark_thread_read_for_member(thread):
    if thread.member_unread:
        thread.member_unread = False
        if thread.damage_report_id:
            report = BookDamageReport.query.get(thread.damage_report_id)
            if report:
                report.member_message_read = True
        db.session.commit()


def mark_thread_read_for_admin(thread):
    if thread.admin_unread:
        thread.admin_unread = False
        db.session.commit()


def build_thread_summaries(member, limit=20):
    threads = (
        MemberPortalThread.query.filter_by(member_id=member.id)
        .order_by(MemberPortalThread.updated_at.desc())
        .limit(limit)
        .all()
    )
    summaries = []
    for thread in threads:
        last_msg = (
            MemberPortalChatMessage.query.filter_by(thread_id=thread.id)
            .order_by(MemberPortalChatMessage.created_at.desc())
            .first()
        )
        summaries.append({
            "id": thread.id,
            "subject": thread.subject,
            "kind": thread.kind,
            "updated_at": thread.updated_at,
            "member_unread": thread.member_unread,
            "last_preview": (last_msg.body[:80] + "…") if last_msg and len(last_msg.body) > 80 else (last_msg.body if last_msg else ""),
            "last_sender": last_msg.sender if last_msg else None,
            "status": thread.damage_report.status if thread.damage_report else None,
        })
    return summaries


def serialize_thread_messages(thread):
    return [
        {
            "id": msg.id,
            "sender": msg.sender,
            "body": msg.body,
            "at": msg.created_at.strftime("%d %b %Y, %I:%M %p") if msg.created_at else "",
        }
        for msg in thread.messages
    ]


def migrate_legacy_portal_messages():
    """One-time style migration for old single-shot messages and damage replies."""
    for old in MemberPortalMessage.query.order_by(MemberPortalMessage.created_at).all():
        exists = (
            MemberPortalThread.query.filter_by(
                member_id=old.member_id,
                subject=old.subject or "Message from Library",
                kind="direct",
            )
            .join(MemberPortalChatMessage)
            .filter(
                MemberPortalChatMessage.sender == "admin",
                MemberPortalChatMessage.body == old.message,
            )
            .first()
        )
        if exists:
            continue
        create_direct_thread(old.member_id, old.subject, old.message)

    for report in BookDamageReport.query.order_by(BookDamageReport.created_at).all():
        if MemberPortalThread.query.filter_by(damage_report_id=report.id).first():
            continue
        thread = get_or_create_damage_thread(report)
        if report.member_message:
            db.session.add(
                MemberPortalChatMessage(
                    thread_id=thread.id,
                    sender="admin",
                    body=report.member_message,
                    created_at=report.member_message_at or report.created_at or utcnow_naive(),
                )
            )
            thread.member_unread = not report.member_message_read
            db.session.commit()
