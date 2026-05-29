from datetime import datetime, timezone

from models import db


class Reservation(db.Model):
    __tablename__ = "reservations"

    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey("books.id"), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey("members.id"), nullable=False)
    reserved_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    expiry_date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="Pending")
    notes = db.Column(db.String(255), nullable=True)

    book = db.relationship("Book", backref="reservations")
    member = db.relationship("Member", backref="reservations")

    def __repr__(self):
        return f"<Reservation {self.id}>"
