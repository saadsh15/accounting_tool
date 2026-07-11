from django.db import models
from core.models import Organization
from .providers import PROVIDER_CHOICES, get_provider


class AISettings(models.Model):
    """Per-organization LLM provider choice.

    Absent, the org falls back to the server's .env defaults, so existing
    installs keep working untouched.
    """
    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name='ai_settings')
    provider = models.CharField(max_length=32, choices=PROVIDER_CHOICES, default='ollama')
    model = models.CharField(max_length=200, blank=True)
    # Write-only in the UI: set via the form, never rendered back to the browser.
    api_key = models.CharField(max_length=255, blank=True)
    base_url = models.URLField(blank=True, help_text='Overrides the provider default. Leave blank for the default.')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'AI settings'
        verbose_name_plural = 'AI settings'

    def __str__(self):
        return f"{self.organization.name}: {self.provider}/{self.model or 'default'}"

    @property
    def masked_api_key(self):
        """Enough to confirm which key is set, not enough to use it."""
        if not self.api_key:
            return ''
        return f"{'•' * 8}{self.api_key[-4:]}" if len(self.api_key) > 4 else '•' * 8

    @property
    def effective_model(self):
        return self.model or get_provider(self.provider)['default_model']

class Account(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='accounts')
    name = models.CharField(max_length=255)
    bank_name = models.CharField(max_length=255, blank=True)
    account_number = models.CharField(max_length=50, blank=True)
    
    def __str__(self):
        return f"{self.name} ({self.bank_name})"

class Statement(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        DONE = 'done', 'Done'
        FAILED = 'failed', 'Failed'

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='statements')
    file = models.FileField(upload_to='statements/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    transactions_found = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)

    IN_FLIGHT = (Status.PENDING, Status.PROCESSING)

    def __str__(self):
        return f"Statement for {self.account.name} at {self.uploaded_at.strftime('%Y-%m-%d')}"

class CategoryRule(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='rules')
    keyword = models.CharField(max_length=100)
    category_name = models.CharField(max_length=100)
    
    def __str__(self):
        return f"If '{self.keyword}' then '{self.category_name}'"

class Transaction(models.Model):
    statement = models.ForeignKey(Statement, on_delete=models.CASCADE, related_name='transactions', null=True, blank=True)
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='transactions')
    date = models.DateField()
    description = models.CharField(max_length=500)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.CharField(max_length=100, blank=True)
    
    def __str__(self):
        return f"{self.date} - {self.description} : {self.amount}"
