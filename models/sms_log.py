from datetime import datetime, timezone

from models import db


class SmsLog(db.Model):
    __tablename__ = "sms_logs"

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("members.id"), nullable=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.id"), nullable=True)
    phone = db.Column(db.String(20), nullable=False)
    message_type = db.Column(db.String(30), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="Sent")
    sent_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    member = db.relationship("Member", backref="sms_logs")
    transaction = db.relationship("Transaction", backref="sms_logs")

    def __repr__(self):
        return f"<SmsLog {self.message_type} to {self.phone}>"
