import pdfplumber
import pytesseract
from PIL import Image
import re
from datetime import datetime
from .models import Transaction, CategoryRule
from decimal import Decimal, InvalidOperation
from .ai_service import categorize_transaction_with_ai

def process_statement(statement):
    file_path = statement.file.path
    text = ""
    
    # Extract text from PDF using pdfplumber or OCR for images
    if file_path.lower().endswith('.pdf'):
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
                else:
                    # Fallback to OCR if the PDF page is an image
                    img = page.to_image(resolution=300).original
                    ocr_text = pytesseract.image_to_string(img)
                    if ocr_text:
                        text += ocr_text + "\n"
    elif file_path.lower().endswith(('.png', '.jpg', '.jpeg')):
        text = pytesseract.image_to_string(Image.open(file_path))

    lines = text.split('\n')
    
    # Broadened regex patterns:
    # 1. Standard: Date: MM/DD/YYYY, Description, Amount
    pattern_standard = re.compile(r'^(\d{1,4}[-/]\d{1,2}[-/]\d{1,4})\s+(.+?)\s+([+-]?\$?\d{1,3}(?:,\d{3})*\.\d{2})$')
    
    # 2. Dummy Statement format: MM/DD Description Amount Balance (e.g., 10/02 POS PURCHASE 4.23 65.73)
    pattern_dummy = re.compile(r'^(\d{2}/\d{2})\s+(.+?)\s+([+-]?\$?\d{1,3}(?:,\d{3})*\.\d{2}|\.\d{2})\s+([+-]?\$?\d{1,3}(?:,\d{3})*\.\d{2})$')
    
    rules = CategoryRule.objects.filter(organization=statement.account.organization)
    
    transactions_created = 0

    # For logging/debugging in the console
    print(f"--- Extracted Text from {file_path} ---")
    print(text[:500] + ("..." if len(text) > 500 else ""))
    print("---------------------------------------")

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
            
            # Auto-categorize (Rule-based engine)
            category = "Uncategorized"
            for rule in rules:
                if rule.keyword.lower() in description.lower():
                    category = rule.category_name
                    break
            
            # AI Fallback: If no rule matched, let Ollama categorize it
            if category == "Uncategorized":
                category = categorize_transaction_with_ai(description, float(amount))
                    
            Transaction.objects.create(
                statement=statement,
                account=statement.account,
                date=date_obj,
                description=description.strip(),
                amount=amount,
                category=category
            )
            transactions_created += 1
        except (ValueError, InvalidOperation):
            continue
                
    statement.processed = True
    statement.save()
    
    return transactions_created

