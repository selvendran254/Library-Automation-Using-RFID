from datetime import datetime, timezone

from models import db


class Transaction(db.Model):
    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey("books.id"), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey("members.id"), nullable=False)
    issue_date = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    due_date = db.Column(db.DateTime, nullable=False)
    return_date = db.Column(db.DateTime, nullable=True)
    fine_amount = db.Column(db.Float, nullable=False, default=0.0)
    fine_paid = db.Column(db.Boolean, nullable=False, default=False)
    renewal_count = db.Column(db.Integer, nullable=False, default=0)
    receipt_no = db.Column(db.String(30), nullable=True)
    notes = db.Column(db.String(255), nullable=True)

    book = db.relationship("Book", back_populates="transactions")
    member = db.relationship("Member", back_populates="transactions")

    def __repr__(self):
        return f"<Transaction {self.id}>"

    @property
    def is_overdue(self):
        if self.return_date:
            return False
        return datetime.now(timezone.utc).replace(tzinfo=None) > self.due_date.replace(tzinfo=None)

    @property
    def status(self):
        if self.return_date:
            return "Returned"
        if self.is_overdue:
            return "Overdue"
        return "Issued"

    def calculate_fine(self, fine_per_day=2):
        if not self.return_date:
            return 0.0
        end_date = self.return_date.replace(tzinfo=None)
        due = self.due_date.replace(tzinfo=None)
        if end_date <= due:
            return 0.0
        overdue_days = (end_date - due).days
        return overdue_days * fine_per_day
