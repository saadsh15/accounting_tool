# Accountant MVP

An intelligent accounting web application that automates bookkeeping by extracting and categorizing transaction data from uploaded bank statements using OCR.

## Features
- **Multi-tenant Architecture:** Supports multiple organizations and users.
- **Statement Uploads:** Upload bank statements in PDF or image formats.
- **OCR Processing:** Automatically extracts dates, descriptions, and amounts from statements using Tesseract OCR.
- **Background Processing:** Extraction runs as a queued job, so slow OCR and LLM calls never block the web request.
- **Auto-Categorization:** Rule-based engine plus an LLM fallback (Ollama, DeepSeek, or any frontier model via OpenRouter).
- **Financial Dashboard:** View income, expenses, and transaction history at a glance.

## Tech Stack
- **Backend:** Python, Django
- **Queue:** QStash (HTTP jobs — serverless has no long-lived worker)
- **Storage:** S3 / Cloudflare R2 via django-storages
- **Database:** SQLite (default), configurable to PostgreSQL via `DATABASE_URL`
- **OCR:** pytesseract, pdfplumber, Tesseract OCR
- **Frontend:** Tailwind CSS, Chart.js

## Installation

### Prerequisites
- Python 3.12 (Django 5.0 supports 3.10–3.12; it does **not** run on 3.13+)
- Tesseract, only if you want to OCR *image* statements locally (`sudo apt-get install tesseract-ocr`,
  or `brew install tesseract`). Text-based PDFs need no OCR, and on Vercel — where no binary can be
  installed — images fall back to the OCR.space API.

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
6. Start the server:
   ```bash
   python manage.py runserver
   ```
   With no `QSTASH_TOKEN` set, statements are processed inline in the upload request —
   no queue or worker to run locally.
7. Open `http://127.0.0.1:8000` in your browser.

## Configuration

Settings are read from `.env` (see `config/settings.py`).

| Variable | Default | Notes |
| --- | --- | --- |
| `SECRET_KEY` | *(required)* | No default; the app will not boot without it. |
| `DEBUG` | `False` | |
| `ALLOWED_HOSTS` | `.vercel.app,localhost,127.0.0.1` | Set to your domain in production. |
| `DATABASE_URL` | SQLite in project root | e.g. `postgres://user:pass@host/db` |
| `MEDIA_ROOT` | `<project>/media` | Local dev only. In production use object storage (see Deployment). |
| `QSTASH_TOKEN` | — | Unset means jobs run inline. See Deployment. |
| `AI_PROVIDER` | `ollama` | Server-wide default: `ollama`, `deepseek` or `openrouter`. Organizations can override it in the UI. |
| `AI_MODEL` / `AI_API_KEY` / `AI_BASE_URL` | — | Defaults for hosted providers. |
| `OLLAMA_URL` / `OLLAMA_MODEL` | `127.0.0.1:11434` / `phi3` | |
| `DEEPSEEK_API_KEY` | — | Legacy alias for `AI_API_KEY`. |
| `SITE_URL` | `http://127.0.0.1:8000` | Public origin. QStash calls back to it, and it is sent to OpenRouter as the attribution header. |
| `DELETE_ROOT_PASSWORD` | `root` | Shared secret gating destructive deletes. **Change this.** |

## Choosing a model

Each organization picks its own provider under **AI Settings** (per-org, not per-user).
Organizations that never touch it fall back to the server's `.env` defaults.

| Provider | Notes |
| --- | --- |
| **Ollama** | Local only — it cannot run on Vercel. No key, no per-call cost. |
| **DeepSeek** | Hosted. Needs a DeepSeek key. |
| **OpenRouter** | One key, every frontier model — Claude, GPT, Gemini, Llama, Grok, Mistral. |

DeepSeek and OpenRouter both speak the OpenAI `/chat/completions` shape, so they share a
single transport; adding another hosted provider is a new entry in `accounting/providers.py`,
not new request code.

The OpenRouter model dropdown is **fetched live** from its public catalog (cached for an
hour) rather than hardcoded, so newly released models appear without a deploy. **Save & Test
Connection** round-trips a real prompt so a bad key or a mistyped model surfaces immediately
instead of failing later inside a background job.

API keys are stored per-organization in the database and are **write-only in the UI**: only a
masked tail is ever rendered back, and submitting a blank field leaves the stored key
untouched. They are not yet encrypted at rest — treat DB access as equivalent to key access.

If the AI provider is unreachable, extraction degrades gracefully: transactions are still
saved from the regex parser and categorized as `Miscellaneous` rather than being discarded.

## Deployment (Vercel)

Serverless has no long-lived worker, so statement extraction is queued over HTTP:

1. Upload writes the statement to **object storage** and publishes a job to **QStash**.
2. QStash calls `POST /accounting/jobs/process-statement/` back, in a *new* invocation.
3. That invocation does the OCR + LLM work and updates the statement's status.
4. The dashboard polls and refreshes when the queue drains.

**Object storage is not optional.** Vercel's `/tmp` is per-invocation, so the job would
never find a file left on local disk. Set `AWS_STORAGE_BUCKET_NAME` (S3 or Cloudflare R2)
in production. With no bucket set, uploads fall back to the local filesystem, which is
correct for development only.

Required environment variables on Vercel:

| Variable | Notes |
| --- | --- |
| `SITE_URL` | Your real deployment URL. QStash calls back to it, so `localhost` will not work. |
| `QSTASH_TOKEN` | From the Upstash console. |
| `QSTASH_CURRENT_SIGNING_KEY`, `QSTASH_NEXT_SIGNING_KEY` | Used to verify the webhook. The endpoint is public, so **without these it refuses every callback** rather than trusting it. |
| `AWS_STORAGE_BUCKET_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | Object storage. |
| `AWS_S3_ENDPOINT_URL` | Cloudflare R2 only. |

With no `QSTASH_TOKEN`, the job runs inline in the upload request. That keeps local
development working with no external services, but it is **not** suitable for production:
it is exactly the synchronous design that exceeds the serverless function timeout.

Note that Tesseract cannot be installed on Vercel, so image statements are OCR'd through
the OCR.space API. Text-based PDFs never need OCR at all.

## Tests

```bash
python manage.py test
```
