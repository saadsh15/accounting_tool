from django.contrib import admin
from .models import Account, Statement, CategoryRule, Transaction

admin.site.register(Account)
admin.site.register(Statement)
admin.site.register(CategoryRule)
admin.site.register(Transaction)
