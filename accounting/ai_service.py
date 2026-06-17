import requests
import json
import re
from django.conf import settings

ACCOUNTING_CATEGORIES = [
    "Income", "Rent/Mortgage", "Utilities", "Groceries", 
    "Dining Out", "Transportation", "Insurance", "Entertainment", 
    "Healthcare", "Personal Care", "Debt Payments", "Savings/Investments", 
    "Education", "Miscellaneous", "Bank Fees"
]

def _get_setting(name, default):
    return getattr(settings, name, default)

def _call_deepseek(prompt, temperature=0.0, system_message=None):
    """Helper function to call the DeepSeek API."""
    key = _get_setting('DEEPSEEK_API_KEY', '')
    url = _get_setting('DEEPSEEK_API_URL', 'https://api.deepseek.com/v1/chat/completions')
    if not key or key == 'your_deepseek_api_key_here':
        raise ValueError("DeepSeek API Key is missing or invalid. Please update the .env file.")

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    
    messages = []
    if system_message:
        messages.append({"role": "system", "content": system_message})
    messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": temperature,
        "stream": False
    }

    response = requests.post(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    return data.get("choices", [])[0].get("message", {}).get("content", "").strip()


def _call_ollama(prompt, temperature=0.0):
    """Helper function to call the local Ollama API."""
    url = _get_setting('OLLAMA_URL', 'http://127.0.0.1:11434/api/generate')
    model = _get_setting('OLLAMA_MODEL', 'phi3')
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
        }
    }
    
    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    return data.get("response", "").strip()


# Explicit categorization rules to embed in the AI prompt
CATEGORIZATION_RULES = """
RULES — follow these strictly:
- "PAYROLL", "SALARY", "WAGE", "DIRECT DEPOSIT", "PREAUTHORIZED CREDIT" (from employer/payroll), "SOCIAL SECURITY", "SSA", "US TREASURY", "TAX REFUND", "INTEREST CREDIT" → Income
- "RENT", "MORTGAGE", "LEASE PAYMENT", "APARTMENT RENT", "HOUSING" → Rent/Mortgage
- "ELECTRIC", "GAS BILL", "WATER", "SEWER", "INTERNET", "CABLE", "PHONE BILL", "MOBILE", "UTILITY" → Utilities
- "WAL-MART", "WALMART", "GROCERY", "KROGER", "SAFEWAY", "ALDI", "COSTCO", "DILLONS", "FOOD", "SUPERMARKET", "MARKET" → Groceries
- "RESTAURANT", "CAFE", "COFFEE", "STARBUCKS", "MCDONALD", "PIZZA", "BAR", "GRILL", "DELI", "DINING", "DINER", "BISTRO" → Dining Out
- "GAS STATION", "PETROL", "FUEL", "UBER", "LYFT", "TAXI", "PARKING", "TRANSIT", "BUS", "TRAIN", "AIRLINE", "FLIGHT" → Transportation
- "INSURANCE", "GEICO", "STATE FARM", "ALLSTATE", "PROGRESSIVE", "HOME INSURANCE" → Insurance
- "NETFLIX", "SPOTIFY", "HULU", "DISNEY", "CINEMA", "MOVIE", "THEATER", "GAMING", "SPORTS", "CONCERT", "TICKET" → Entertainment
- "PHARMACY", "HOSPITAL", "DOCTOR", "MEDICAL", "DENTAL", "VISION", "HEALTH", "CLINIC", "CVS", "WALGREENS" → Healthcare
- "SALON", "BARBER", "SPA", "GYM", "FITNESS", "BEAUTY", "COSMETIC", "DRY CLEAN" → Personal Care
- "LOAN PAYMENT", "CREDIT CARD PAYMENT", "STUDENT LOAN", "CAR PAYMENT", "DEBT" → Debt Payments
- "401K", "IRA", "INVESTMENT", "BROKERAGE", "SAVINGS TRANSFER", "MUTUAL FUND", "STOCK" → Savings/Investments
- "TUITION", "SCHOOL", "UNIVERSITY", "COLLEGE", "BOOK", "COURSE", "TRAINING" → Education
- "SERVICE CHARGE", "MONTHLY FEE", "OVERDRAFT", "ATM FEE", "BANK FEE", "MAINTENANCE FEE", "NSF FEE" → Bank Fees
- "HOME DEPOT", "LOWES", "HARDWARE", "JEWELER", "AMAZON", "TARGET", "DEPARTMENT STORE", generic "POS PURCHASE", "CHECK", "ATM WITHDRAWAL", anything else → Miscellaneous

CRITICAL RULES FOR CREDITS AND DEBITS:
- If the amount is POSITIVE (a credit/deposit) and the description mentions PAYROLL, CREDIT, DEPOSIT, TREASURY, or SSA → ALWAYS categorize as "Income"
- "PREAUTHORIZED CREDIT" with a positive amount is almost always "Income" (payroll or government payment)
- "ATM WITHDRAWAL" is "Miscellaneous" (we don't know what cash was used for)
- Generic "POS PURCHASE" without a merchant name is "Miscellaneous"
- Generic "CHECK" without details is "Miscellaneous"
"""

def categorize_transaction_with_ai(description, amount):
    """
    Asks the configured AI model to categorize a single transaction description.
    """
    ai_provider = _get_setting('AI_PROVIDER', 'ollama').lower()
    safe_description = re.sub(r'[^\w\s-]', '', description)[:200]
    
    system_message = """You are an expert, meticulous accountant who categorizes bank transactions with extreme precision.
You MUST output ONLY the category name — no explanation, no quotes, no punctuation, no preamble.
You MUST pick from the provided category list. Never invent new categories."""
    
    amount_type = "CREDIT/DEPOSIT (money IN)" if amount >= 0 else "DEBIT/WITHDRAWAL (money OUT)"
    
    prompt = f"""Categorize this bank transaction into EXACTLY ONE category.

Categories: {', '.join(ACCOUNTING_CATEGORIES)}

{CATEGORIZATION_RULES}

Transaction Description: "{safe_description}"
Amount: {amount} ({amount_type})

Output ONLY the category name, nothing else:"""

    try:
        if ai_provider == 'deepseek':
            category = _call_deepseek(prompt, temperature=0.0, system_message=system_message)
        else:
            category = _call_ollama(prompt, temperature=0.0)
        
        # Clean up output
        category = category.replace('"', '').replace("'", "").replace(".", "").strip()
        # Remove any trailing/leading whitespace or newlines
        category = category.split('\n')[0].strip()
        
        # Fallback if hallucinated
        if category not in ACCOUNTING_CATEGORIES:
            for valid_cat in ACCOUNTING_CATEGORIES:
                if valid_cat.lower() in category.lower():
                    return valid_cat
            return "Miscellaneous"
            
        return category
        
    except Exception as e:
        print(f"AI API Error ({ai_provider}): {e}")
        return "Miscellaneous"


def generate_financial_insights(transactions_data):
    """
    Takes a list of transaction dictionaries and generates a financial summary/insights.
    """
    ai_provider = _get_setting('AI_PROVIDER', 'ollama').lower()
    tx_text = "\n".join([f"{t['date']}: {t['description']} - ${t['amount']} ({t['category']})" for t in transactions_data])
    
    prompt = f"""
You are an expert financial advisor and accountant. Analyze the following list of recent bank transactions and provide a short, professional, 2-3 paragraph financial insight report. 
Highlight where the user is spending the most money based on these specific accounting categories: {', '.join(ACCOUNTING_CATEGORIES)}.
Identify any anomalies, and provide a brief piece of actionable advice to improve their savings. 

Transactions:
{tx_text}

Report:
"""

    try:
        if ai_provider == 'deepseek':
            return _call_deepseek(prompt, temperature=0.7)
        else:
            return _call_ollama(prompt, temperature=0.7)
    except Exception as e:
        print(f"AI API Error ({ai_provider}): {e}")
        return f"Could not generate insights at this time via {ai_provider}. Check logs for details."
