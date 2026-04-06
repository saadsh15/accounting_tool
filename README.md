# Accountant MVP

An intelligent accounting web application that automates bookkeeping by extracting and categorizing transaction data from uploaded bank statements using OCR.

## Features
- **Multi-tenant Architecture:** Supports multiple organizations and users.
- **Statement Uploads:** Upload bank statements in PDF or image formats.
- **OCR Processing:** Automatically extracts dates, descriptions, and amounts from statements using Tesseract OCR.
- **Auto-Categorization:** Rule-based engine to categorize transactions automatically.
- **Financial Dashboard:** View income, expenses, and transaction history at a glance.

## Tech Stack
- **Backend:** Python, Django
- **Database:** SQLite (Default for MVP, configurable to PostgreSQL)
- **OCR:** pytesseract, pdfplumber, Tesseract OCR
- **Frontend:** Tailwind CSS, Chart.js

## Installation

### Prerequisites
- Python 3.10+
- Tesseract OCR (`sudo apt-get install tesseract-ocr` on Ubuntu/Debian or `brew install tesseract` on macOS)

### Setup
1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd accountant
   ```
2. Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run migrations:
   ```bash
   python manage.py migrate
   ```
5. Create a superuser:
   ```bash
   python manage.py createsuperuser
   ```
6. Start the development server:
   ```bash
   python manage.py runserver
   ```
7. Open `http://127.0.0.1:8000` in your browser.
