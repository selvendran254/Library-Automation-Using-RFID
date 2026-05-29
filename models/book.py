from datetime import datetime, timezone

from models import db


class Book(db.Model):
    __tablename__ = "books"

    id = db.Column(db.Integer, primary_key=True)
    rfid_tag = db.Column(db.String(50), unique=True, nullable=False, index=True)
    isbn = db.Column(db.String(20), nullable=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(150), nullable=False)
    publisher = db.Column(db.String(150), nullable=True)
    category = db.Column(db.String(100), nullable=False)
    shelf_location = db.Column(db.String(50), nullable=True)
    description = db.Column(db.Text, nullable=True)
    total_qty = db.Column(db.Integer, nullable=False, default=1)
    available_qty = db.Column(db.Integer, nullable=False, default=1)
    book_status = db.Column(db.String(20), nullable=False, default="Active")
    added_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    transactions = db.relationship("Transaction", back_populates="book", lazy="dynamic")

    def __repr__(self):
        return f"<Book {self.title}>"

    @property
    def issued_count(self):
        return self.total_qty - self.available_qty

    @property
    def is_low_stock(self):
        from utils.helpers import get_low_stock_threshold

        return self.available_qty <= get_low_stock_threshold()

    @property
    def pending_reservations(self):
        return self.reservations.filter_by(status="Pending").count()
