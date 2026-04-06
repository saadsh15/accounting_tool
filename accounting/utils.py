import pdfplumber
import pytesseract
from PIL import Image
import re
from datetime import datetime
from .models import Transaction, CategoryRule
from decimal import Decimal, InvalidOperation

def process_statement(statement):
    file_path = statement.file.path
    text = ""
    
    # Extract text from PDF using pdfplumber or OCR for images
    if file_path.lower().endswith('.pdf'):
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text() + "\n"
    elif file_path.lower().endswith(('.png', '.jpg', '.jpeg')):
        text = pytesseract.image_to_string(Image.open(file_path))

    # Basic Regex to find typical statement lines: Date (MM/DD/YYYY), Description, Amount
    # Example: 12/25/2023 STARBUCKS STORE -5.50
    lines = text.split('\n')
    pattern = re.compile(r'^(\d{2}/\d{2}/\d{4})\s+(.+?)\s+(-?\d+\.\d{2})$')
    
    rules = CategoryRule.objects.filter(organization=statement.account.organization)

    for line in lines:
        match = pattern.match(line.strip())
        if match:
            date_str, description, amount_str = match.groups()
            try:
                date = datetime.strptime(date_str, '%m/%d/%Y').date()
                amount = Decimal(amount_str)
                
                # Auto-categorize
                category = "Uncategorized"
                for rule in rules:
                    if rule.keyword.lower() in description.lower():
                        category = rule.category_name
                        break
                        
                Transaction.objects.create(
                    statement=statement,
                    account=statement.account,
                    date=date,
                    description=description.strip(),
                    amount=amount,
                    category=category
                )
            except (ValueError, InvalidOperation):
                continue
                
    statement.processed = True
    statement.save()
