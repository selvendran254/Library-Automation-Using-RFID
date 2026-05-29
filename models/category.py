from models import db


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(255), nullable=True)
    shelf_section = db.Column(db.String(50), nullable=True)

    def __repr__(self):
        return f"<Category {self.name}>"
