from django.db import models
from core.models import Organization

class Account(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='accounts')
    name = models.CharField(max_length=255)
    bank_name = models.CharField(max_length=255, blank=True)
    account_number = models.CharField(max_length=50, blank=True)
    
    def __str__(self):
        return f"{self.name} ({self.bank_name})"

class Statement(models.Model):
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='statements')
    file = models.FileField(upload_to='statements/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)
    
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
