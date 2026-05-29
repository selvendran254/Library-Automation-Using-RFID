from datetime import datetime, timezone

from models import db


class LoginOtp(db.Model):
    __tablename__ = "login_otps"

    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20), nullable=False, index=True)
    purpose = db.Column(db.String(30), nullable=False)
    user_type = db.Column(db.String(20), nullable=False)
    user_id = db.Column(db.Integer, nullable=False)
    otp_hash = db.Column(db.String(256), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    is_used = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    verified_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f"<LoginOtp {self.phone} {self.purpose}>"
