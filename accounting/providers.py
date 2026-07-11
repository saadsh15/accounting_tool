"""Registry of supported LLM providers.

Deliberately free of Django imports so both models.py and ai_service.py can
import it without a cycle.

Two transports cover everything:

- ``openai``  -- the /chat/completions shape. DeepSeek, OpenRouter, OpenAI and
  most hosted providers speak it, so they differ only by base URL and model.
- ``ollama``  -- Ollama's native /api/generate.

No frontier model IDs are hardcoded anywhere. OpenRouter proxies Claude, GPT,
Gemini, Llama and the rest, and its model list is fetched live (see
ai_service.fetch_openrouter_models), so new models appear without a code change.
"""

OPENAI_TRANSPORT = 'openai'
OLLAMA_TRANSPORT = 'ollama'

PROVIDERS = {
    'ollama': {
        'label': 'Ollama (local)',
        'transport': OLLAMA_TRANSPORT,
        'base_url': 'http://127.0.0.1:11434',
        'default_model': 'phi3',
        'requires_key': False,
        'model_catalog': False,
        'help': 'Runs on this server. No API key, no per-call cost.',
    },
    'deepseek': {
        'label': 'DeepSeek',
        'transport': OPENAI_TRANSPORT,
        'base_url': 'https://api.deepseek.com/v1',
        'default_model': 'deepseek-chat',
        'requires_key': True,
        'model_catalog': False,
        'help': 'Hosted. Needs a DeepSeek API key.',
    },
    'openrouter': {
        'label': 'OpenRouter (Claude, GPT, Gemini, Llama, ...)',
        'transport': OPENAI_TRANSPORT,
        'base_url': 'https://openrouter.ai/api/v1',
        # No default: the model list is fetched live and the user picks one.
        # Hardcoding a frontier model ID here would be stale within weeks.
        'default_model': '',
        'requires_key': True,
        'model_catalog': True,
        'help': 'One key, every frontier model. Pick the model below.',
    },
}

PROVIDER_CHOICES = [(key, cfg['label']) for key, cfg in PROVIDERS.items()]

OPENROUTER_MODELS_URL = 'https://openrouter.ai/api/v1/models'


def get_provider(name):
    """Returns the provider spec, falling back to ollama for unknown names."""
    return PROVIDERS.get(name, PROVIDERS['ollama'])
