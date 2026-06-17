import requests
import json
import re
from django.conf import settings

# Global AI Settings
AI_PROVIDER = getattr(settings, 'AI_PROVIDER', 'ollama').lower()

# DeepSeek Settings
DEEPSEEK_API_KEY = getattr(settings, 'DEEPSEEK_API_KEY', '')
DEEPSEEK_API_URL = getattr(settings, 'DEEPSEEK_API_URL', 'https://api.deepseek.com/v1/chat/completions')

# Ollama Settings
OLLAMA_URL = getattr(settings, 'OLLAMA_URL', 'http://127.0.0.1:11434/api/generate')
OLLAMA_MODEL = getattr(settings, 'OLLAMA_MODEL', 'phi3')

ACCOUNTING_CATEGORIES = [
    "Income", "Rent/Mortgage", "Utilities", "Groceries", 
    "Dining Out", "Transportation", "Insurance", "Entertainment", 
    "Healthcare", "Personal Care", "Debt Payments", "Savings/Investments", 
    "Education", "Miscellaneous", "Bank Fees"
]


def _call_deepseek(prompt, temperature=0.0):
    """Helper function to call the DeepSeek API."""
    if not DEEPSEEK_API_KEY or DEEPSEEK_API_KEY == 'your_deepseek_api_key_here':
        raise ValueError("DeepSeek API Key is missing or invalid. Please update the .env file.")

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "deepseek-chat", # the standard chat model for deepseek
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature,
        "stream": False
    }

    response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    return data.get("choices", [])[0].get("message", {}).get("content", "").strip()


def _call_ollama(prompt, temperature=0.0):
    """Helper function to call the local Ollama API."""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
        }
    }
    
    response = requests.post(OLLAMA_URL, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    return data.get("response", "").strip()


def categorize_transaction_with_ai(description, amount):
    """
    Asks the configured AI model to categorize a single transaction description.
    """
    safe_description = re.sub(r'[^\w\s-]', '', description)[:200]
    
    prompt = f"""
You are an expert, meticulous accountant. Categorize the following bank transaction into EXACTLY ONE of the provided categories.
Do not provide any explanation, preamble, or formatting. Output only the category name exactly as it appears in the list.

Categories: {', '.join(ACCOUNTING_CATEGORIES)}

Transaction Description: "{safe_description}"
Amount: {amount}
"""

    try:
        if AI_PROVIDER == 'deepseek':
            category = _call_deepseek(prompt, temperature=0.0)
        else:
            category = _call_ollama(prompt, temperature=0.0)
        
        # Clean up output
        category = category.replace('"', '').replace("'", "").replace(".", "").strip()
        
        # Fallback if hallucinated
        if category not in ACCOUNTING_CATEGORIES:
            for valid_cat in ACCOUNTING_CATEGORIES:
                if valid_cat.lower() in category.lower():
                    return valid_cat
            return "Uncategorized"
            
        return category
        
    except Exception as e:
        print(f"AI API Error ({AI_PROVIDER}): {e}")
        return "Uncategorized"


def generate_financial_insights(transactions_data):
    """
    Takes a list of transaction dictionaries and generates a financial summary/insights.
    """
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
        if AI_PROVIDER == 'deepseek':
            return _call_deepseek(prompt, temperature=0.7)
        else:
            return _call_ollama(prompt, temperature=0.7)
    except Exception as e:
        print(f"AI API Error ({AI_PROVIDER}): {e}")
        return f"Could not generate insights at this time via {AI_PROVIDER}. Check logs for details."
