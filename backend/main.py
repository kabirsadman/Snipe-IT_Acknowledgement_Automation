import csv
import io
import smtplib
import sqlite3
import ssl
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr, HttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent
TEST_ASSET_TAG = "TEST-LAP-002"
TEST_EMAIL = "ssami@idlc.com"
TEST_URL = "http://192.168.111.128/account/accept/2"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")
    database_path: str = str(BASE_DIR / "acknowledgements.sqlite3")
    demo_mode: bool = True
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_starttls: bool = True

settings = Settings()

@contextmanager
def database():
    path = Path(settings.database_path)
    if not path.is_absolute():
        path = BASE_DIR / path
    connection = sqlite3.connect(path, timeout=15)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

def initialize_database():
    with database() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
            asset_tag TEXT NOT NULL, model TEXT NOT NULL, serial TEXT NOT NULL,
            email TEXT NOT NULL, url TEXT NOT NULL, action TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT ''
        );
        CREATE UNIQUE INDEX IF NOT EXISTS one_send_per_asset_email
        ON events(asset_tag, email COLLATE NOCASE)
        WHERE action IN ('SENDING', 'SEND_REQUESTED', 'DELIVERY_UNKNOWN');
        """)
        # A process interruption during SMTP must not silently enable duplicate sending.
        db.execute("UPDATE events SET action='DELIVERY_UNKNOWN', detail='Server interrupted during send; verify delivery manually.' WHERE action='SENDING'")

@asynccontextmanager
async def lifespan(app):
    initialize_database()
    yield

app = FastAPI(title="Asset Acknowledgement API", lifespan=lifespan)

class Asset(BaseModel):
    asset_tag: str = Field(min_length=1, max_length=100, pattern=r"^[^\r\n]+$")
    model: str = Field(min_length=1, max_length=200)
    serial: str = Field(min_length=1, max_length=100)
    email: EmailStr
    url: HttpUrl

def validate_asset(asset):
    data = asset.model_dump(mode="json")
    for key in ("asset_tag", "model", "serial"):
        data[key] = data[key].strip()
        if not data[key]:
            raise HTTPException(422, f"{key} cannot be blank.")
    data["email"] = data["email"].lower()
    if settings.demo_mode and (data["asset_tag"] != TEST_ASSET_TAG or data["email"] != TEST_EMAIL or data["url"] != TEST_URL):
        raise HTTPException(403, "Demo mode only permits TEST-LAP-002 and the approved test email/link.")
    return data

def compose(data):
    subject = f"TEST - IT Asset Acknowledgement - {data['asset_tag']}" if settings.demo_mode else f"IT Asset Acknowledgement - {data['asset_tag']}"
    notice = "This is a test notification. No physical laptop has been delivered.\n\n" if settings.demo_mode else ""
    body = (f"Dear Employee,\n\nAn IT asset has been assigned to your Snipe-IT account.\n\n"
            f"Asset Tag: {data['asset_tag']}\nModel: {data['model']}\nSerial Number: {data['serial']}\n\n"
            f"Acknowledgement Link:\n{data['url']}\n\n"
            "Please log in to Snipe-IT and select 'I Accept' or 'I Decline'.\n\n"
            f"{notice}Regards,\nIT Asset Management Team\n")
    return {"to": data["email"], "subject": subject, "body": body}

def log_event(db, data, action):
    cursor = db.execute("INSERT INTO events(created_at,asset_tag,model,serial,email,url,action) VALUES (?,?,?,?,?,?,?)",
        (datetime.now(timezone.utc).isoformat(), data['asset_tag'], data['model'], data['serial'], data['email'], data['url'], action))
    return cursor.lastrowid

@app.get("/api/config")
def config():
    return {"demo_mode": settings.demo_mode, "sending_enabled": bool(settings.smtp_host and settings.smtp_from),
            "defaults": {"asset_tag": TEST_ASSET_TAG, "model": "Test Laptop Model", "serial": "TEST-SERIAL-002", "email": TEST_EMAIL, "url": TEST_URL}}

@app.post("/api/preview")
def preview(asset: Asset):
    data = validate_asset(asset)
    with database() as db:
        log_event(db, data, "PREVIEWED")
    return compose(data)

@app.post("/api/send")
def send(asset: Asset):
    data = validate_asset(asset)
    if not settings.smtp_host or not settings.smtp_from:
        raise HTTPException(503, "Configure SMTP_HOST and SMTP_FROM in backend/.env before sending.")
    try:
        with database() as db:
            event_id = log_event(db, data, "SENDING")
    except sqlite3.IntegrityError:
        raise HTTPException(409, "A send request already exists for this asset and employee. Check history before resending.")
    content = compose(data)
    message = EmailMessage()
    message['From'] = settings.smtp_from
    message['To'] = content['to']
    message['Subject'] = content['subject']
    message.set_content(content['body'])
    submitted = False
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            if settings.smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
            submitted = True
    except Exception:
        # SMTP disconnects can happen after acceptance. Block retries until verified.
        with database() as db:
            db.execute("UPDATE events SET action=?, detail=? WHERE id=?",
                ('SEND_REQUESTED' if submitted else 'DELIVERY_UNKNOWN',
                 'SMTP connection ended; check the mailbox before retrying.', event_id))
        raise HTTPException(502, "SMTP connection failed. Delivery may be uncertain; check history and the mailbox before retrying.")
    with database() as db:
        db.execute("UPDATE events SET action='SEND_REQUESTED' WHERE id=?", (event_id,))
    return {"message": "Mail server accepted the send request. This does not confirm delivery or asset acceptance."}

@app.get("/api/history")
def history():
    with database() as db:
        return [dict(row) for row in db.execute("SELECT * FROM events ORDER BY id DESC LIMIT 500")]

@app.get("/api/history/export")
def export():
    with database() as db:
        rows = db.execute("SELECT * FROM events ORDER BY id DESC").fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['id','created_at','asset_tag','model','serial','email','url','action','detail'])
    for row in rows:
        writer.writerow(["'" + value if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')) else value for value in row])
    return Response(output.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="acknowledgements.csv"'})

# A built React frontend is served on the same origin as the API.
from fastapi.staticfiles import StaticFiles
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
