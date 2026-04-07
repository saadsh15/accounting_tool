import requests
import json
from django.conf import settings

OLLAMA_URL = getattr(settings, 'OLLAMA_URL', 'http://127.0.0.1:11434/api/generate')
OLLAMA_MODEL = getattr(settings, 'OLLAMA_MODEL', 'phi3') # E.g., phi3 is a ~3.8B model, qwen2 is a ~4B parameter model

def categorize_transaction_with_ai(description, amount):
    """
    Asks the local Ollama model to categorize a single transaction description.
    """
    categories = [
        "Income", "Rent/Mortgage", "Utilities", "Groceries", 
        "Dining Out", "Transportation", "Insurance", "Entertainment", 
        "Healthcare", "Personal Care", "Debt Payments", "Savings/Investments", 
        "Education", "Miscellaneous", "Bank Fees"
    ]
    
    prompt = f"""
You are an expert, meticulous accountant. Categorize the following bank transaction into EXACTLY ONE of the provided categories.
Do not provide any explanation, preamble, or formatting. Output only the category name exactly as it appears in the list.

Categories: {', '.join(categories)}

Transaction Description: "{description}"
Amount: {amount}
"""

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.0, # Zero temperature for deterministic categorization
        }
    }
    
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        category = data.get("response", "").strip()
        
        # Clean up in case the model adds quotes or punctuation
        category = category.replace('"', '').replace("'", "").replace(".", "").strip()
        
        # Fallback if the model hallucinates a category
        if category not in categories:
            # Simple heuristic mapping if it's close
            for valid_cat in categories:
                if valid_cat.lower() in category.lower():
                    return valid_cat
            return "Uncategorized"
            
        return category
        
    except Exception as e:
        print(f"Ollama API Error: {e}")
        return "Uncategorized"

def generate_financial_insights(transactions_data):
    """
    Takes a list of transaction dictionaries and generates a financial summary/insights.
    """
    tx_text = "\n".join([f"{t['date']}: {t['description']} - ${t['amount']} ({t['category']})" for t in transactions_data])
    
    prompt = f"""
You are an expert financial advisor and accountant. Analyze the following list of recent bank transactions and provide a short, professional, 2-3 paragraph financial insight report. 
Highlight where the user is spending the most money, any anomalies, and a brief piece of actionable advice to improve their savings. 

Transactions:
{tx_text}

Report:
"""

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.7,
        }
    }
    
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data.get("response", "").strip()
    except Exception as e:
        print(f"Ollama API Error: {e}")
        return "Could not generate insights at this time. Ensure Ollama is running locally and the model is downloaded."
