from django.urls import path
from . import views

urlpatterns = [
    path('upload/', views.upload_statement, name='upload_statement'),
    path('add-account/', views.add_account, name='add_account'),
    path('delete-transaction/<int:transaction_id>/', views.delete_transaction, name='delete_transaction'),
]
