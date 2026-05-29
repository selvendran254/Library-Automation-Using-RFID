from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

from models.activity_log import ActivityLog  # noqa: E402, F401
from models.book import Book  # noqa: E402, F401
from models.book_request import BookRequest  # noqa: E402, F401
from models.category import Category  # noqa: E402, F401
from models.member import Member  # noqa: E402, F401
from models.notice import Notice  # noqa: E402, F401
from models.reservation import Reservation  # noqa: E402, F401
from models.settings import LibrarySetting  # noqa: E402, F401
from models.sms_log import SmsLog  # noqa: E402, F401
from models.damage_report import BookDamageReport  # noqa: E402, F401
from models.member_message import (  # noqa: E402, F401
    MemberPortalChatMessage,
    MemberPortalMessage,
    MemberPortalThread,
)
from models.renewal_request import MembershipRenewalRequest  # noqa: E402, F401
from models.staff_user import StaffUser  # noqa: E402, F401
from models.login_otp import LoginOtp  # noqa: E402, F401
from models.transaction import Transaction  # noqa: E402, F401
