from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import Account, Statement, Transaction
from core.models import Organization
from .utils import process_statement
from django.contrib import messages

@login_required
def upload_statement(request):
    # Ensure the user has an organization (e.g., if created via createsuperuser)
    if not request.user.organization:
        org = Organization.objects.create(name=f"{request.user.username}'s Organization")
        request.user.organization = org
        request.user.save()

    if request.method == 'POST':
        account_id = request.POST.get('account')
        file = request.FILES.get('statement_file')
        
        if file and account_id:
            account = Account.objects.get(id=account_id)
            statement = Statement.objects.create(account=account, file=file)
            
            # Simple synchronous processing for MVP
            try:
                tx_count = process_statement(statement)
                if tx_count > 0:
                    messages.success(request, f'Statement processed successfully! {tx_count} transactions found.')
                else:
                    messages.warning(request, 'Statement was processed, but no transactions could be automatically extracted. Ensure the file contains clear, tabular transaction data.')
            except Exception as e:
                messages.error(request, f'Error processing statement: {str(e)}')
            
            return redirect('dashboard')
        else:
            messages.error(request, 'Please select a valid account and provide a statement file.')
            
    # Make sure user's org has accounts, create a default one if none exist for MVP convenience
    accounts = Account.objects.filter(organization=request.user.organization)
    if not accounts.exists():
        Account.objects.create(organization=request.user.organization, name="Main Checking")
        accounts = Account.objects.filter(organization=request.user.organization)
        
    return render(request, 'accounting/upload.html', {'accounts': accounts})

@login_required
def add_account(request):
    if not request.user.organization:
        org = Organization.objects.create(name=f"{request.user.username}'s Organization")
        request.user.organization = org
        request.user.save()

    if request.method == 'POST':
        name = request.POST.get('name')
        bank_name = request.POST.get('bank_name', '')
        account_number = request.POST.get('account_number', '')
        
        if name:
            Account.objects.create(
                organization=request.user.organization,
                name=name,
                bank_name=bank_name,
                account_number=account_number
            )
            messages.success(request, f'Account "{name}" added successfully.')
            return redirect('upload_statement')
        else:
            messages.error(request, 'Account name is required.')
            
    return render(request, 'accounting/add_account.html')

