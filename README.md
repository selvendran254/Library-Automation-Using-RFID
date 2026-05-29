# Library Automation Using RFID

Complete library RFID system — **Flask web application** (PostgreSQL) plus **Arduino hardware** prototype.

## Web Application (Flask)

Flask + PostgreSQL library management with RFID issue/return, member portal, SMS alerts, and admin dashboard.

### Features

- **Staff admin:** books, members, issue/return, fines, reservations, reports, damage reports, settings
- **RFID:** HID keyboard wedge or USB serial reader
- **Member portal:** dashboard, history, chat with admin, book requests, reservations, renewal requests
- **Security:** staff username/password login, CSRF protection, role-based sessions
- **SMS:** Fast2SMS, MSG91, Twilio, or simulated mode
- **Email:** optional SMTP notifications

### Quick Start

#### 1. PostgreSQL

```bash
docker run -d --name library-rfid-pg \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=library_rfid \
  -p 5433:5432 postgres:16
```

#### 2. Python setup

```bash
cd library_rfid
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env — set DATABASE_URL and SECRET_KEY
```

#### 3. Run (development)

```bash
export DATABASE_URL=postgresql://postgres:postgres@localhost:5433/library_rfid
python app.py
```

Open: http://127.0.0.1:5000

**Staff login:** `admin` / `admin123` (change immediately)

**Member portal:** http://127.0.0.1:5000/portal/

### Production

```bash
export FLASK_DEBUG=0
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
gunicorn -w 4 -b 0.0.0.0:8000 wsgi:application
```

### Tests

```bash
pytest tests/ -v
```

### Project Structure

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

See `.env.example` for environment variables.

---

## Arduino Hardware Prototype

Automates book issue/return using RFID tags and an MFRC522 RFID reader with Arduino.

### Features

- Scan RFID tag of books and users
- Real-time serial logging of issue/return events
- Store book/user details in CSV or external DB
- LCD-based status display
- Buzzer alert for invalid tag scan

### Hardware

- Arduino Uno / Nano
- MFRC522 RFID Module
- LCD 16x2 (I2C recommended)
- Buzzer + LED indicators
- RFID tags/cards

See `library_rfid.ino`, `BUILD.md`, and `wiring_diagram.png` in this repo.

---

## License

Internal / educational use.
