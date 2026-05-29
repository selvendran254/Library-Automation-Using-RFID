# Library RFID Automation System

Flask + PostgreSQL library management with RFID issue/return, member portal, SMS alerts, and admin dashboard.

## Features

- **Staff admin:** books, members, issue/return, fines, reservations, reports, damage reports, settings
- **RFID:** HID keyboard wedge or USB serial reader
- **Member portal:** dashboard, history, chat with admin, book requests, reservations, renewal requests
- **Security:** staff login, CSRF protection, role-based sessions
- **SMS:** simulated (default), Twilio, or MSG91
- **Email:** optional SMTP notifications

## Quick Start

### 1. PostgreSQL

```bash
docker run -d --name library-rfid-pg \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=library_rfid \
  -p 5433:5432 postgres:16
```

### 2. Python setup

```bash
cd library_rfid
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env — set DATABASE_URL and SECRET_KEY
```

### 3. Run (development)

```bash
export DATABASE_URL=postgresql://postgres:postgres@localhost:5433/library_rfid
python app.py
```

Open: http://127.0.0.1:5000

**Staff login:** `admin` / `admin123` (change immediately)

**Member portal:** http://127.0.0.1:5000/portal/ — RFID card login or magic link from admin

## Production

```bash
export FLASK_DEBUG=0
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
gunicorn -w 4 -b 0.0.0.0:8000 wsgi:application
```

Use nginx/Caddy for HTTPS in front of Gunicorn.

## Database Migrations

```bash
flask db init          # first time only
flask db migrate -m "description"
flask db upgrade
```

Legacy databases also auto-upgrade via `upgrade_database()` on startup.

## Tests

```bash
pytest tests/ -v
```

## Project Structure

```
library_rfid/
├── app.py              # App factory + dashboard
├── wsgi.py             # Production entry
├── models/             # SQLAlchemy models
├── routes/             # Flask blueprints
├── templates/          # Jinja2 HTML
├── static/             # CSS, JS, uploads
├── utils/              # RFID, SMS, auth, helpers
└── tests/              # pytest suite
```

## Environment Variables

See `.env.example` for full list.

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Flask session secret (required in production) |
| `DATABASE_URL` | PostgreSQL connection string |
| `SMS_PROVIDER` | `simulated`, `twilio`, or `msg91` |
| `DEFAULT_ADMIN_PASSWORD` | Initial admin password (first run) |

## Default Sample Data

On first run with empty DB: 10 books, 5 members, sample transactions and notices are seeded.

## License

Internal / educational use.
