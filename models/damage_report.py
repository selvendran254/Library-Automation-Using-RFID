from datetime import datetime, timezone

from models import db


class BookDamageReport(db.Model):
    __tablename__ = "book_damage_reports"

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("members.id"), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey("books.id"), nullable=False)
    transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.id"), nullable=True)
    damage_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=True)
    photo_filename = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="Pending")
    admin_notes = db.Column(db.Text, nullable=True)
    member_message = db.Column(db.Text, nullable=True)
    member_message_at = db.Column(db.DateTime, nullable=True)
    member_message_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    reviewed_at = db.Column(db.DateTime, nullable=True)

    member = db.relationship("Member", backref="damage_reports")
    book = db.relationship("Book", backref="damage_reports")
    transaction = db.relationship("Transaction", backref="damage_reports")

    @property
    def photo_path(self):
        return f"uploads/damage_reports/{self.photo_filename}"

    def __repr__(self):
        return f"<BookDamageReport {self.id} {self.damage_type}>"
