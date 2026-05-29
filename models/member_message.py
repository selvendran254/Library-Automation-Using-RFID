from datetime import datetime, timezone

from models import db


class MemberPortalThread(db.Model):
    __tablename__ = "member_portal_threads"

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("members.id"), nullable=False, index=True)
    subject = db.Column(db.String(150), nullable=False)
    kind = db.Column(db.String(20), nullable=False, default="direct")
    damage_report_id = db.Column(
        db.Integer, db.ForeignKey("book_damage_reports.id"), nullable=True, unique=True
    )
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    member_unread = db.Column(db.Boolean, nullable=False, default=False)
    admin_unread = db.Column(db.Boolean, nullable=False, default=False)

    member = db.relationship("Member", backref="portal_threads")
    damage_report = db.relationship(
        "BookDamageReport",
        backref=db.backref("portal_thread", uselist=False),
    )
    messages = db.relationship(
        "MemberPortalChatMessage",
        backref="thread",
        order_by="MemberPortalChatMessage.created_at",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<MemberPortalThread {self.id} {self.subject}>"


class MemberPortalChatMessage(db.Model):
    __tablename__ = "member_portal_chat_messages"

    id = db.Column(db.Integer, primary_key=True)
    thread_id = db.Column(
        db.Integer, db.ForeignKey("member_portal_threads.id"), nullable=False, index=True
    )
    sender = db.Column(db.String(10), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<MemberPortalChatMessage {self.id} {self.sender}>"


class MemberPortalMessage(db.Model):
    """Legacy one-shot admin messages (migrated into threads on upgrade)."""

    __tablename__ = "member_portal_messages"

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("members.id"), nullable=False, index=True)
    subject = db.Column(db.String(150), nullable=True)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    member = db.relationship("Member", backref="portal_messages")

    def __repr__(self):
        return f"<MemberPortalMessage {self.id} to member {self.member_id}>"
