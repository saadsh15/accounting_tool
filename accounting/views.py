from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import Account, Statement, Transaction
from .utils import process_statement
from django.contrib import messages

@login_required
def upload_statement(request):
    if request.method == 'POST':
        account_id = request.POST.get('account')
        file = request.FILES.get('statement_file')
        
        if file and account_id:
            account = Account.objects.get(id=account_id)
            statement = Statement.objects.create(account=account, file=file)
            
            # Simple synchronous processing for MVP
            try:
                process_statement(statement)
                messages.success(request, 'Statement processed successfully!')
            except Exception as e:
                messages.error(request, f'Error processing statement: {str(e)}')
            
            return redirect('dashboard')
            
    # Make sure user's org has accounts, create a default one if none exist for MVP convenience
    if request.user.organization:
        accounts = Account.objects.filter(organization=request.user.organization)
        if not accounts.exists():
            Account.objects.create(organization=request.user.organization, name="Main Checking")
            accounts = Account.objects.filter(organization=request.user.organization)
    else:
        accounts = []
        
    return render(request, 'accounting/upload.html', {'accounts': accounts})
