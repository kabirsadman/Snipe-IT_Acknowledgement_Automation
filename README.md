# Asset Acknowledgement Web

A separate rewrite of `Helpdesk/asset_acknowledgement_gui.py` using FastAPI, React, TypeScript, Tailwind CSS v4, and SQLite. The desktop source is unchanged.

## Run on this PC

Dependencies and a production frontend build are prepared in this project. Start the application:

```bash
cd /home/sami/Documents/Codes/Asset-Acknowledgement-Web
./start.sh
```

Open **http://127.0.0.1:8000**. API documentation: **http://127.0.0.1:8000/docs**. Stop with Ctrl+C.

A project-local Node 22 runtime is under `.tools/node` because Node/npm were not available on the system PATH. It does not change your system installation. Python dependencies live in `.venv`.

To reinstall dependencies and rebuild:

```bash
./setup.sh
```

On a fresh machine install Python 3.11+ with venv/pip support and Node.js 22 LTS with npm first. Generated environments, Node runtime, database, secrets, and build output are ignored by Git. The frontend dependency lockfile is included.

## Features

- Validated asset form with the original test values.
- Server-generated preview of the exact email content.
- Explicit confirmation before sending; sending disabled until SMTP is configured.
- Persistent SQLite activity history with search and CSV export.
- Database uniqueness protection against repeated sends for the same asset tag and employee email (case insensitive).
- Responsive layout, loading/error states, and separate preview/send status.
- Snipe-IT continues handling employee acceptance and rejection; this app does not retrieve those decisions.

## Configure email

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env` with your organization's SMTP relay settings and restart the backend. Use an authorized sender in `SMTP_FROM`. Set `SMTP_USERNAME` and `SMTP_PASSWORD` only if your relay requires login. STARTTLS is on by default; set `SMTP_STARTTLS=false` only when your approved relay configuration requires it. This implementation uses SMTP and does not implement Microsoft Graph or SMTP OAuth. Do not commit `.env`.

`DEMO_MODE=true` preserves the original restrictions: `TEST-LAP-002`, `ssami@idlc.com`, and `http://192.168.111.128/account/accept/2`. Set `DEMO_MODE=false` deliberately to allow other assets and recipients; the test notice is then removed.

Send requests are recorded as `SEND_REQUESTED` when SMTP accepts the message. This does not confirm delivery or asset acceptance. Transport errors and interrupted sends are conservatively marked `DELIVERY_UNKNOWN`, blocking automatic retries. Verify the mailbox and relay logs before an administrator changes such a record in SQLite. There is no automated retry or resend endpoint.

## Development

Terminal 1, from the project root:

```bash
.venv/bin/uvicorn main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

Terminal 2, from the project root:

```bash
export PATH="$PWD/.tools/node/bin:$PATH"
cd frontend
npm run dev
```

Open the URL printed by Vite, normally http://127.0.0.1:5173. Vite proxies `/api` to FastAPI, keeping browser requests on the same origin. Build changes with `npm run build`; restart the backend when serving a new build.

Run backend tests from the project root:

```bash
.venv/bin/python -m pytest backend/tests -q
```

Tests use temporary SQLite databases and mocked SMTP; no real email is sent.

## Files and storage

- `backend/main.py`: FastAPI routes, validation, SMTP transport, and SQLite persistence.
- `backend/tests/test_api.py`: integration tests.
- `backend/requirements.txt`: dependency ranges; `requirements.lock.txt`: installed Python versions for this Python 3.14/Linux environment.
- `frontend/src/main.tsx`: React interface.
- `frontend/src/index.css`: Tailwind import and theme.
- `backend/acknowledgements.sqlite3`: created automatically on first start. Back up this file while the app is stopped.

CSV logs from the old desktop application are not imported automatically. History in this app begins with an empty database.

## Deployment scope

This version is a local application bound to `127.0.0.1`. Authentication and staff authorization are not included. Before sharing it on a company network, add organizational login, permissions, HTTPS, and an appropriate deployment configuration. Run a single backend worker: startup recovery assumes only one app process owns the SQLite send workflow. Employees need access to the company network/VPN to open the private Snipe-IT link.
