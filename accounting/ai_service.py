import requests
import json
import re
from dataclasses import dataclass
from django.conf import settings
from django.core.cache import cache

from .providers import (
    OLLAMA_TRANSPORT,
    OPENAI_TRANSPORT,
    OPENROUTER_MODELS_URL,
    get_provider,
)

ACCOUNTING_CATEGORIES = [
    "Income", "Rent/Mortgage", "Utilities", "Groceries",
    "Dining Out", "Transportation", "Insurance", "Entertainment",
    "Healthcare", "Personal Care", "Debt Payments", "Savings/Investments",
    "Education", "Miscellaneous", "Bank Fees"
]

REQUEST_TIMEOUT = 60


def _get_setting(name, default):
    return getattr(settings, name, default)


@dataclass(frozen=True)
class AIConfig:
    provider: str
    transport: str
    model: str
    api_key: str
    base_url: str


def resolve_ai_config(organization=None):
    """Per-org settings if configured, otherwise the server's .env defaults.

    Organizations that never visit the settings page keep the old behaviour.
    """
    ai_settings = getattr(organization, 'ai_settings', None) if organization else None

    if ai_settings:
        spec = get_provider(ai_settings.provider)
        return AIConfig(
            provider=ai_settings.provider,
            transport=spec['transport'],
            model=ai_settings.effective_model,
            api_key=ai_settings.api_key,
            base_url=ai_settings.base_url or spec['base_url'],
        )

    provider = _get_setting('AI_PROVIDER', 'ollama').lower()
    spec = get_provider(provider)

    if spec['transport'] == OLLAMA_TRANSPORT:
        # The legacy OLLAMA_URL env var is a full /api/generate URL, not a base.
        base_url = _get_setting('OLLAMA_URL', spec['base_url'])
        model = _get_setting('OLLAMA_MODEL', spec['default_model'])
        api_key = ''
    else:
        base_url = _get_setting('AI_BASE_URL', '') or spec['base_url']
        model = _get_setting('AI_MODEL', '') or spec['default_model']
        api_key = _get_setting('AI_API_KEY', '') or _get_setting('DEEPSEEK_API_KEY', '')

    return AIConfig(
        provider=provider,
        transport=spec['transport'],
        model=model,
        api_key=api_key,
        base_url=base_url,
    )


def _ollama_generate_url(base_url):
    """Accepts either a base URL or a full /api/generate URL (the legacy env format)."""
    url = base_url.rstrip('/')
    return url if url.endswith('/api/generate') else f"{url}/api/generate"


def _call_ollama(prompt, config, temperature=0.0, system_message=None):
    payload = {
        "model": config.model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if system_message:
        payload["system"] = system_message

    response = requests.post(_ollama_generate_url(config.base_url), json=payload, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json().get("response", "").strip()


def _call_openai_compatible(prompt, config, temperature=0.0, system_message=None):
    """DeepSeek, OpenRouter, and any other /chat/completions provider."""
    if not config.api_key:
        raise ValueError(
            f"No API key configured for {config.provider}. Add one on the AI Settings page."
        )
    if not config.model:
        raise ValueError(
            f"No model selected for {config.provider}. Choose one on the AI Settings page."
        )

    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    if config.provider == 'openrouter':
        # OpenRouter attributes traffic with these; both are optional.
        headers["HTTP-Referer"] = _get_setting('SITE_URL', 'http://localhost')
        headers["X-Title"] = "Accountant"

    messages = []
    if system_message:
        messages.append({"role": "system", "content": system_message})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": config.model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }

    url = f"{config.base_url.rstrip('/')}/chat/completions"
    response = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()

    choices = data.get("choices") or []
    if not choices:
        # OpenRouter reports upstream failures in-band with a 200.
        raise ValueError(f"{config.provider} returned no choices: {data.get('error', data)}")
    return (choices[0].get("message", {}).get("content") or "").strip()


def call_llm(prompt, organization=None, temperature=0.0, system_message=None, config=None):
    """Single entry point: resolves the org's provider and dispatches by transport."""
    config = config or resolve_ai_config(organization)
    if config.transport == OLLAMA_TRANSPORT:
        return _call_ollama(prompt, config, temperature, system_message)
    return _call_openai_compatible(prompt, config, temperature, system_message)


def fetch_openrouter_models(force=False):
    """Live catalog of every model OpenRouter proxies, cached for an hour.

    Fetched rather than hardcoded so new frontier models appear without a deploy.
    Needs no API key: the catalog endpoint is public.
    """
    cache_key = 'openrouter_models'
    if not force:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    response = requests.get(OPENROUTER_MODELS_URL, timeout=15)
    response.raise_for_status()

    models = [
        {'id': m['id'], 'name': m.get('name') or m['id']}
        for m in response.json().get('data', [])
        if m.get('id')
    ]
    models.sort(key=lambda m: m['name'].lower())

    cache.set(cache_key, models, 3600)
    return models


def check_connection(config):
    """Round-trips a trivial prompt so a bad key or model surfaces on the settings
    page rather than silently failing later inside a worker."""
    try:
        reply = call_llm("Reply with the single word: OK", config=config, temperature=0.0)
    except Exception as exc:
        return False, str(exc)[:300]
    return True, f"{config.provider} responded: {reply[:80] or '(empty response)'}"


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

def categorize_transaction_with_ai(description, amount, organization=None):
    """
    Asks the organization's configured AI model to categorize a single transaction.
    """
    config = resolve_ai_config(organization)
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
        category = call_llm(prompt, config=config, temperature=0.0, system_message=system_message)

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
        print(f"AI API Error ({config.provider}): {e}")
        return "Miscellaneous"


def generate_financial_insights(transactions_data, organization=None):
    """
    Takes a list of transaction dictionaries and generates a financial summary/insights.
    """
    config = resolve_ai_config(organization)
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
        return call_llm(prompt, config=config, temperature=0.7)
    except Exception as e:
        print(f"AI API Error ({config.provider}): {e}")
        return f"Could not generate insights at this time via {config.provider}. Check logs for details."
