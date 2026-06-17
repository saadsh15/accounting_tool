import pdfplumber
import pytesseract
from PIL import Image
import re
import requests
import json
from datetime import datetime
from django.conf import settings
from .models import Transaction, CategoryRule
from decimal import Decimal, InvalidOperation
from .ai_service import categorize_transaction_with_ai

def ocr_via_ocr_space(file_path):
    """
    Calls OCR.space API as a fallback when Tesseract is not available.
    Supports PDF and image files.
    """
    try:
        api_key = getattr(settings, 'OCR_SPACE_API_KEY', 'helloworld')
        if not api_key:
            api_key = 'helloworld'
            
        payload = {
            'apikey': api_key,
            'language': 'eng',
            'isTable': True, # Forces row-by-row parsing for tabular data
            'OCREngine': 2,   # Engine 2 is much better for table layouts
        }
        
        with open(file_path, 'rb') as f:
            r = requests.post(
                'https://api.ocr.space/parse/image',
                files={'file': f},
                data=payload,
                timeout=30
            )
        
        res = r.json()
        if res.get('IsErroredOnProcessing') is False:
            parsed_results = res.get('ParsedResults', [])
            extracted_text = ""
            for result in parsed_results:
                text = result.get('ParsedText', '')
                if text:
                    extracted_text += text + "\n"
            return extracted_text
        else:
            error_message = res.get('ErrorMessage')
            print(f"OCR.space API Error: {error_message}")
            return ""
    except Exception as e:
        print(f"Failed to call OCR.space API: {e}")
        return ""

# Vague/generic description patterns that indicate the AI won't have enough context
VAGUE_DESCRIPTIONS = {
    'POS PURCHASE', 'POSPURCHASE', 'POS', 'PURCHASE',
    'CHECK', 'ATM WITHDRAWAL', 'ATM', 'WITHDRAWAL',
    'DEBIT', 'CREDIT', 'PREAUTHORIZED CREDIT', 'PREAUTHORIZED',
    'DIRECT DEBIT', 'DIRECT DEPOSIT', 'TRANSFER',
}

def _is_vague_description(description):
    """Check if a transaction description is too vague for accurate categorization."""
    cleaned = re.sub(r'\d+', '', description).strip().upper()
    return cleaned in VAGUE_DESCRIPTIONS or any(cleaned == v for v in VAGUE_DESCRIPTIONS)


def extract_transactions_with_ai(text):
    """
    Asks the configured AI model to extract transactions from raw text.
    Returns a list of dicts: [{'date_str': 'YYYY-MM-DD', 'description': '...', 'amount': Decimal, 'category': '...'}]
    """
    from .ai_service import ACCOUNTING_CATEGORIES, CATEGORIZATION_RULES, _call_deepseek, _call_ollama
    
    ai_provider = getattr(settings, 'AI_PROVIDER', 'ollama').lower()
    categories_str = ", ".join(ACCOUNTING_CATEGORIES)
    
    system_message = """You are an expert financial data extraction system that reads bank statement text and extracts structured transaction data.
You MUST output ONLY a valid JSON array. No explanation, no markdown, no preamble."""
    
    prompt = f"""
Analyze the following raw bank statement text and extract ALL transactions.

IMPORTANT: The statement may have MULTIPLE sections. A summary table on one page may list short descriptions,
while a detailed section on another page provides full merchant names. You MUST cross-reference both sections
to produce the MOST DETAILED description possible for each transaction.

For example, if the summary says "POS PURCHASE 4.23" and the detail section says 
"POS PURCHASE TERMINAL 24349201 WAL-MART #3492", use the detailed description "POS PURCHASE WAL-MART" 
and the amount from the summary.

For each transaction, extract:
- date: formatted as YYYY-MM-DD. If the statement only provides MM/DD, assume the year is the current year (2026).
- description: the MOST DETAILED description available (include merchant names when found in the statement).
- amount: the decimal amount. Deposits/credits must be positive. Withdrawals/debits/charges must be negative.
- category: categorize into EXACTLY ONE of these categories: {categories_str}

{CATEGORIZATION_RULES}

Format the output as a valid JSON array of objects. Example:
[
  {{"date": "2026-10-02", "description": "POS PURCHASE WAL-MART", "amount": -4.23, "category": "Groceries"}},
  {{"date": "2026-10-03", "description": "PREAUTHORIZED CREDIT PAYROLL", "amount": 763.01, "category": "Income"}}
]

Here is the raw bank statement text:
{text}
"""
    try:
        if ai_provider == 'deepseek':
            response_text = _call_deepseek(prompt, temperature=0.0, system_message=system_message)
        else:
            response_text = _call_ollama(prompt, temperature=0.0)
            
        # Parse JSON
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            first_newline = cleaned.find("\n")
            if first_newline != -1:
                cleaned = cleaned[first_newline:].strip()
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()
                
        transactions = json.loads(cleaned)
        
        validated_txs = []
        for tx in transactions:
            if 'date' in tx and 'description' in tx and 'amount' in tx:
                try:
                    datetime.strptime(tx['date'], '%Y-%m-%d')
                except ValueError:
                    try:
                        parsed_date = datetime.strptime(tx['date'], '%m/%d/%Y')
                        tx['date'] = parsed_date.strftime('%Y-%m-%d')
                    except ValueError:
                        tx['date'] = datetime.today().strftime('%Y-%m-%d')
                
                category = tx.get('category', 'Miscellaneous')
                if category not in ACCOUNTING_CATEGORIES:
                    matched = False
                    for valid_cat in ACCOUNTING_CATEGORIES:
                        if valid_cat.lower() in category.lower():
                            category = valid_cat
                            matched = True
                            break
                    if not matched:
                        category = "Miscellaneous"
                
                validated_txs.append({
                    'date_str': tx['date'],
                    'description': tx['description'],
                    'amount': Decimal(str(tx['amount'])),
                    'category': category
                })
        return validated_txs
    except Exception as e:
        print(f"Failed to extract transactions with AI: {e}")
        return []

def process_statement(statement):
    file_path = statement.file.path
    text = ""
    
    # Extract text from PDF using pdfplumber or OCR for images
    if file_path.lower().endswith('.pdf'):
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted and extracted.strip():
                    text += extracted + "\n"
                else:
                    # Fallback to OCR if the PDF page is an image
                    try:
                        img = page.to_image(resolution=300).original
                        ocr_text = pytesseract.image_to_string(img)
                        if ocr_text:
                            text += ocr_text + "\n"
                    except Exception as e:
                        print(f"Skipped OCR on PDF page due to missing Tesseract: {e}")
                        
        # Fallback to OCR.space if no text was extracted
        if not text.strip():
            print("No text extracted via pdfplumber or local Tesseract. Falling back to OCR.space API...")
            text = ocr_via_ocr_space(file_path)
                        
    elif file_path.lower().endswith(('.png', '.jpg', '.jpeg')):
        try:
            text = pytesseract.image_to_string(Image.open(file_path))
        except Exception as e:
            print(f"Local OCR failed or missing: {e}. Falling back to OCR.space API...")
            text = ocr_via_ocr_space(file_path)
            if not text:
                raise Exception("Image uploads require Tesseract OCR, which is not installed in the Vercel serverless environment. Please upload a standard text-based PDF instead.")

    lines = text.split('\n')
    
    # Broadened regex patterns — use \d+ to handle any number of digits
    # 1. Standard: Date: MM/DD/YYYY, Description, Amount
    pattern_standard = re.compile(r'^(\d{1,4}[-/]\d{1,2}[-/]\d{1,4})\s+(.+?)\s+([+-]?\$?[\d,]+\.\d{2})$')
    
    # 2. Dummy Statement format: MM/DD Description Amount Balance (e.g., 10/02 POS PURCHASE 4.23 65.73)
    pattern_dummy = re.compile(r'^(\d{2}/\d{2})\s+(.+?)\s+([+-]?\$?[\d,]+\.\d{2}|\.\d{2})\s+([+-]?\$?[\d,]+\.\d{2})$')
    
    rules = CategoryRule.objects.filter(organization=statement.account.organization)
    
    transactions_created = 0

    # For logging/debugging in the console
    print(f"--- Extracted Text from {file_path} ---")
    print(text[:500] + ("..." if len(text) > 500 else ""))
    print("---------------------------------------")

    # Phase 1: Collect all regex matches into a list WITHOUT calling AI yet
    regex_parsed = []
    for line in lines:
        line_clean = line.strip()
        match = pattern_standard.match(line_clean)
        
        date_str = ""
        description = ""
        amount_str = ""
        
        if match:
            date_str, description, amount_str = match.groups()
        else:
            match_dummy = pattern_dummy.match(line_clean)
            if match_dummy:
                date_str, description, amount_str, balance_str = match_dummy.groups()
                # Dummy dates are MM/DD, append current year for MVP purposes
                date_str = f"{date_str}/{datetime.today().year}"
                
                # Make amount negative if it looks like a withdrawal, positive if deposit
                # Just a simple heuristic for this dummy statement format
                if "CREDIT" not in description.upper() and "DEPOSIT" not in description.upper() and "INTEREST" not in description.upper():
                    amount_str = "-" + amount_str
            else:
                continue
                
        # Clean up amount string (remove $ and ,)
        clean_amount = amount_str.replace('$', '').replace(',', '')
        if clean_amount.startswith('.'):
            clean_amount = "0" + clean_amount
        elif clean_amount.startswith('-.'):
            clean_amount = "-0." + clean_amount[2:]
            
        # Try parsing the date with multiple common formats
        date_obj = None
        date_formats = ['%m/%d/%Y', '%m/%d/%y', '%Y-%m-%d', '%m-%d-%Y', '%m-%d-%y']
        for fmt in date_formats:
            try:
                date_obj = datetime.strptime(date_str, fmt).date()
                break
            except ValueError:
                continue
        
        if not date_obj:
            continue

        try:
            amount = Decimal(clean_amount)
            regex_parsed.append({
                'date_obj': date_obj,
                'description': description.strip(),
                'amount': amount,
            })
        except (ValueError, InvalidOperation):
            continue
    
    # Phase 2: Pre-scan for vague descriptions BEFORE calling AI or saving to DB
    # This avoids making 20+ wasteful individual API calls when we'll discard results anyway
    use_ai_extraction = False
    if regex_parsed:
        vague_count = sum(1 for tx in regex_parsed if _is_vague_description(tx['description']))
        total_count = len(regex_parsed)
        
        if total_count > 0 and (vague_count / total_count) > 0.5:
            print(f"Pre-scan: {vague_count}/{total_count} regex descriptions are vague. "
                  f"Skipping individual categorization — will use AI full-text extraction instead.")
            use_ai_extraction = True
    
    # Phase 3: If descriptions are specific enough, save with individual AI categorization
    if regex_parsed and not use_ai_extraction:
        from .ai_service import ACCOUNTING_CATEGORIES
        for tx in regex_parsed:
            # Auto-categorize (Rule-based engine)
            category = "Miscellaneous"
            for rule in rules:
                if rule.keyword.lower() in tx['description'].lower():
                    category = rule.category_name
                    break
            
            # AI Fallback: If no rule matched, let AI categorize it
            if category == "Miscellaneous":
                category = categorize_transaction_with_ai(tx['description'], float(tx['amount']))
                
            # Final validation: Ensure it is a standard category
            matched_cat = None
            for std_cat in ACCOUNTING_CATEGORIES:
                if std_cat.lower() == category.lower():
                    matched_cat = std_cat
                    break
            category = matched_cat if matched_cat else "Miscellaneous"
                    
            Transaction.objects.create(
                statement=statement,
                account=statement.account,
                date=tx['date_obj'],
                description=tx['description'],
                amount=tx['amount'],
                category=category
            )
            transactions_created += 1
    
    # AI Fallback Extraction if regex failed or descriptions were too vague
    if transactions_created == 0 and text.strip():
        print("Using AI full-text extraction for better categorization...")
        ai_txs = extract_transactions_with_ai(text)
        for tx in ai_txs:
            try:
                date_obj = datetime.strptime(tx['date_str'], '%Y-%m-%d').date()
                amount = tx['amount']
                description = tx['description']
                category = tx['category']
                
                # Rule-based categorization has higher priority than AI prediction
                for rule in rules:
                    if rule.keyword.lower() in description.lower():
                        category = rule.category_name
                        break
                        
                # Final validation: Ensure it is a standard category
                from .ai_service import ACCOUNTING_CATEGORIES
                matched_cat = None
                for std_cat in ACCOUNTING_CATEGORIES:
                    if std_cat.lower() == category.lower():
                        matched_cat = std_cat
                        break
                category = matched_cat if matched_cat else "Miscellaneous"
                
                Transaction.objects.create(
                    statement=statement,
                    account=statement.account,
                    date=date_obj,
                    description=description.strip(),
                    amount=amount,
                    category=category
                )
                transactions_created += 1
            except Exception as e:
                print(f"Failed to save AI-extracted transaction: {e}")
                
    statement.processed = True
    statement.save()
    
    return transactions_created

