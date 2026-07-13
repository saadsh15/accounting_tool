from django.urls import path
from . import views

urlpatterns = [
    path('upload/', views.upload_statement, name='upload_statement'),
    path('add-account/', views.add_account, name='add_account'),
    path('statement-status/', views.statement_status, name='statement_status'),
    path('jobs/process-statement/', views.process_statement_webhook, name='process_statement_webhook'),
    path('ai-settings/', views.ai_settings, name='ai_settings'),
    path('openrouter-models/', views.openrouter_models, name='openrouter_models'),
    path('delete-transaction/<int:transaction_id>/', views.delete_transaction, name='delete_transaction'),
    path('delete-all-accounts/', views.delete_all_accounts, name='delete_all_accounts'),
    path('run-migrations/', views.run_migrations, name='run_migrations'),
]
