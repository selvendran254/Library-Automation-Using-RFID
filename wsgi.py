"""WSGI entrypoint for production servers (Gunicorn, uWSGI)."""
from app import app

application = app
