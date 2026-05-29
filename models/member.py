from datetime import datetime, timezone

from models import db
from models.transaction import Transaction


class Member(db.Model):
    __tablename__ = "members"

    id = db.Column(db.Integer, primary_key=True)
    rfid_card = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    address = db.Column(db.String(300), nullable=True)
    membership_type = db.Column(db.String(50), nullable=False, default="Standard")
    status = db.Column(db.String(20), nullable=False, default="Active")
    join_date = db.Column(db.Date, default=lambda: datetime.now(timezone.utc).date())
    expiry_date = db.Column(db.Date, nullable=True)
    max_books_override = db.Column(db.Integer, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    portal_token = db.Column(db.String(64), unique=True, nullable=True, index=True)
    portal_token_expires = db.Column(db.DateTime, nullable=True)
    portal_last_login = db.Column(db.DateTime, nullable=True)

    transactions = db.relationship("Transaction", back_populates="member", lazy="dynamic")

    def __repr__(self):
        return f"<Member {self.name}>"

    @property
    def pending_fine(self):
        return sum(
            txn.fine_amount
            for txn in self.transactions
            if txn.return_date and txn.fine_amount > 0 and not txn.fine_paid
        )

    @property
    def active_books_count(self):
        return self.transactions.filter_by(return_date=None).count()

    @property
    def current_books(self):
        """Active (not yet returned) book issues for this member."""
        return (
            self.transactions.filter_by(return_date=None)
            .order_by(Transaction.issue_date.desc())
            .all()
        )

    @property
    def current_book_titles(self):
        return [t.book.title for t in self.current_books if t.book]

    @property
    def is_expired(self):
        if not self.expiry_date:
            return False
        return self.expiry_date < datetime.now(timezone.utc).date()
