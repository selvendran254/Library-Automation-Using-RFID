from datetime import datetime, timezone

from models import db


class BookRequest(db.Model):
    __tablename__ = "book_requests"

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("members.id"), nullable=False)
    book_title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(150), nullable=True)
    notes = db.Column(db.String(300), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="Pending")
    request_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    member = db.relationship("Member", backref="book_requests")

    def __repr__(self):
        return f"<BookRequest {self.book_title}>"
