from django.contrib import admin
from .models import Account, AISettings, Statement, CategoryRule, Transaction

admin.site.register(Account)
admin.site.register(Statement)
admin.site.register(CategoryRule)
admin.site.register(Transaction)


@admin.register(AISettings)
class AISettingsAdmin(admin.ModelAdmin):
    list_display = ('organization', 'provider', 'model', 'masked_api_key', 'updated_at')
    # The raw key is never rendered, in the admin or anywhere else.
    exclude = ('api_key',)
    readonly_fields = ('masked_api_key',)
