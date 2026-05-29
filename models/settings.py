from models import db


class LibrarySetting(db.Model):
    __tablename__ = "library_settings"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(255), nullable=False)
    label = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255), nullable=True)

    @staticmethod
    def get(key, default=None):
        setting = LibrarySetting.query.filter_by(key=key).first()
        return setting.value if setting else default

    @staticmethod
    def get_int(key, default=0):
        val = LibrarySetting.get(key, default)
        try:
            return int(val)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def get_float(key, default=0.0):
        val = LibrarySetting.get(key, default)
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def set_value(key, value):
        setting = LibrarySetting.query.filter_by(key=key).first()
        if setting:
            setting.value = str(value)
        db.session.commit()
