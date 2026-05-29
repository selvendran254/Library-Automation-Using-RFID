import os
import uuid
from pathlib import Path

from flask import current_app
from werkzeug.utils import secure_filename

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def get_upload_folder():
    folder = current_app.config.get("UPLOAD_FOLDER")
    if folder:
        return Path(folder)
    return Path(current_app.root_path) / "static" / "uploads" / "damage_reports"


def ensure_upload_folder():
    folder = get_upload_folder()
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def allowed_image(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def save_damage_photo(file_storage):
    if not file_storage or not file_storage.filename:
        return None, "Please upload a photo of the damage."

    if not allowed_image(file_storage.filename):
        return None, "Only image files are allowed (PNG, JPG, WEBP, GIF)."

    file_storage.seek(0, os.SEEK_END)
    size = file_storage.tell()
    file_storage.seek(0)
    if size > MAX_UPLOAD_BYTES:
        return None, "Photo is too large. Maximum size is 5 MB."

    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    folder = ensure_upload_folder()
    file_storage.save(folder / filename)
    return filename, None
