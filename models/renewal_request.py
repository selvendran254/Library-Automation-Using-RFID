from datetime import datetime, timezone

from models import db


class MembershipRenewalRequest(db.Model):
    __tablename__ = "membership_renewal_requests"

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("members.id"), nullable=False, index=True)
    months = db.Column(db.Integer, nullable=False, default=12)
    status = db.Column(db.String(20), nullable=False, default="Pending")
    member_notes = db.Column(db.String(300), nullable=True)
    admin_notes = db.Column(db.String(300), nullable=True)
    requested_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    reviewed_at = db.Column(db.DateTime, nullable=True)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("staff_users.id"), nullable=True)

    member = db.relationship("Member", backref="renewal_requests")
    reviewed_by = db.relationship("StaffUser")

    def __repr__(self):
        return f"<MembershipRenewalRequest {self.id} member={self.member_id}>"
