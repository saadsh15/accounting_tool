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

def _call_deepseek(prompt, temperature=0.0):
    """Helper function to call the DeepSeek API."""
    key = _get_setting('DEEPSEEK_API_KEY', '')
    url = _get_setting('DEEPSEEK_API_URL', 'https://api.deepseek.com/v1/chat/completions')
    if not key or key == 'your_deepseek_api_key_here':
        raise ValueError("DeepSeek API Key is missing or invalid. Please update the .env file.")

    headers = {
        "Authorization": f"Bearer {key}",
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


def categorize_transaction_with_ai(description, amount):
    """
    Asks the configured AI model to categorize a single transaction description.
    """
    ai_provider = _get_setting('AI_PROVIDER', 'ollama').lower()
    safe_description = re.sub(r'[^\w\s-]', '', description)[:200]
    
    prompt = f"""
You are an expert, meticulous accountant. Categorize the following bank transaction into EXACTLY ONE of the provided categories.
Do not provide any explanation, preamble, or formatting. Output only the category name exactly as it appears in the list.

Categories: {', '.join(ACCOUNTING_CATEGORIES)}

Transaction Description: "{safe_description}"
Amount: {amount}
"""

    try:
        if ai_provider == 'deepseek':
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
