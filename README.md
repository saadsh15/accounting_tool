# Accountant MVP

An intelligent accounting web application that automates bookkeeping by extracting and categorizing transaction data from uploaded bank statements using OCR.

## Features
- **Multi-tenant Architecture:** Supports multiple organizations and users.
- **Statement Uploads:** Upload bank statements in PDF or image formats.
- **OCR Processing:** Automatically extracts dates, descriptions, and amounts from statements using Tesseract OCR.
- **Background Processing:** Extraction runs on a Celery worker, so slow OCR and LLM calls never block the web request.
- **Auto-Categorization:** Rule-based engine plus an LLM fallback (DeepSeek or a local Ollama).
- **Financial Dashboard:** View income, expenses, and transaction history at a glance.

## Tech Stack
- **Backend:** Python, Django
- **Queue:** Celery + Redis
- **Database:** SQLite (default), configurable to PostgreSQL via `DATABASE_URL`
- **OCR:** pytesseract, pdfplumber, Tesseract OCR
- **Frontend:** Tailwind CSS, Chart.js

## Installation

### Prerequisites
- Python 3.12 (Django 5.0 supports 3.10–3.12; it does **not** run on 3.13+)
- System packages listed in `packages.txt` — these are not pip-installable:
  ```bash
  sudo apt-get install -y $(grep -vE '^\s*#|^\s*$' packages.txt)   # tesseract-ocr, redis-server
  ```
  On macOS: `brew install tesseract redis`

### Setup
1. Clone the repository and enter it:
   ```bash
   git clone <repository-url>
   cd accounting_tool
   ```
2. Create and activate a virtual environment:
   ```bash
   python3.12 -m venv venv
   source venv/bin/activate
   ```
3. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Create a `.env` file (at minimum `SECRET_KEY`; see Configuration below).
5. Run migrations and create a superuser:
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```
6. Start Redis, the Celery worker, and the web server — **all three**:
   ```bash
   redis-server                          # or: sudo systemctl start redis
   celery -A config worker --loglevel=info
   python manage.py runserver
   ```
   Without the worker, uploaded statements stay in the `pending` state forever.
7. Open `http://127.0.0.1:8000` in your browser.

## Configuration

Settings are read from `.env` (see `config/settings.py`).

| Variable | Default | Notes |
| --- | --- | --- |
| `SECRET_KEY` | *(required)* | No default; the app will not boot without it. |
| `DEBUG` | `False` | |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Set to your domain in production. |
| `DATABASE_URL` | SQLite in project root | e.g. `postgres://user:pass@host/db` |
| `MEDIA_ROOT` | `<project>/media` | **Must be persistent storage.** Uploaded statements are read back by the worker. |
| `CELERY_BROKER_URL` | `redis://127.0.0.1:6379/0` | |
| `AI_PROVIDER` | `ollama` | `ollama` (local) or `deepseek` (hosted). |
| `OLLAMA_URL` / `OLLAMA_MODEL` | `127.0.0.1:11434` / `phi3` | |
| `DEEPSEEK_API_KEY` | — | Required when `AI_PROVIDER=deepseek`. |
| `DELETE_ROOT_PASSWORD` | `root` | Shared secret gating destructive deletes. **Change this.** |

If the AI provider is unreachable, extraction degrades gracefully: transactions are still
saved from the regex parser and categorized as `Miscellaneous` rather than being discarded.

## Deployment (VPS)

Run **two** services, not one:

- **Web:** `gunicorn config.wsgi` behind nginx.
- **Worker:** `celery -A config worker` — statement extraction runs here. Uploads are
  never processed if this isn't running.

Both need the same `.env` and the same `MEDIA_ROOT`. If you harden the systemd units with
`PrivateTmp=yes`, keep `MEDIA_ROOT` outside `/tmp` (e.g. `/var/lib/accounting/media`),
otherwise uploaded statements are wiped on every restart.

## Tests

```bash
python manage.py test
```
