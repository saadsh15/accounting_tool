from django.shortcuts import render, redirect, get_object_or_404
import os
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from .models import Account, AISettings, Statement, Transaction
from core.models import Organization
from .providers import PROVIDERS
from .ai_service import check_connection, fetch_openrouter_models, resolve_ai_config
from .tasks import process_statement_task
from django.contrib import messages
from django.conf import settings
from django.http import JsonResponse

@login_required
@never_cache
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
            # 1. File Size Validation (5MB Limit)
            if file.size > 5 * 1024 * 1024:
                messages.error(request, 'File size exceeds the 5MB limit.')
                return redirect('upload_statement')

            # 2. File Extension Validation
            ext = os.path.splitext(file.name)[1].lower()
            if ext not in ['.pdf', '.png', '.jpg', '.jpeg']:
                messages.error(request, 'Unsupported file type. Please upload a PDF or image.')
                return redirect('upload_statement')

            # 3. IDOR Fix: Ensure account belongs to user's organization
            account = get_object_or_404(Account, id=account_id, organization=request.user.organization)
            
            statement = Statement.objects.create(account=account, file=file)

            # Hand off to a worker: OCR + LLM calls can outlast the request timeout.
            try:
                process_statement_task.delay(statement.id)
                messages.info(request, 'Statement uploaded. Extracting transactions in the background — this page will update when it finishes.')
            except Exception as e:
                # Broker unreachable. Leave the statement PENDING so it can be retried
                # rather than silently stranding an upload nobody will ever process.
                statement.status = Statement.Status.FAILED
                statement.error_message = f'Could not queue for processing: {e}'
                statement.save(update_fields=['status', 'error_message'])
                messages.error(request, 'Statement uploaded but could not be queued for processing. Please contact support.')

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
@never_cache
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

@login_required
@never_cache
def ai_settings(request):
    """Per-organization LLM provider selection."""
    if not request.user.organization:
        org = Organization.objects.create(name=f"{request.user.username}'s Organization")
        request.user.organization = org
        request.user.save()

    config, _ = AISettings.objects.get_or_create(organization=request.user.organization)

    if request.method == 'POST':
        provider = request.POST.get('provider', '')
        if provider not in PROVIDERS:
            messages.error(request, 'Unknown provider.')
            return redirect('ai_settings')

        config.provider = provider
        config.model = request.POST.get('model', '').strip()
        config.base_url = request.POST.get('base_url', '').strip()

        # Blank means "leave the stored key alone", not "erase it" — the field is
        # never populated with the real key, so a blank submit must not wipe it.
        submitted_key = request.POST.get('api_key', '').strip()
        if submitted_key:
            config.api_key = submitted_key
        elif request.POST.get('clear_api_key'):
            config.api_key = ''

        config.save()

        if request.POST.get('action') == 'test':
            ok, detail = check_connection(resolve_ai_config(request.user.organization))
            if ok:
                messages.success(request, f'Connection OK. {detail}')
            else:
                messages.error(request, f'Connection failed: {detail}')
        else:
            messages.success(request, 'AI settings saved.')

        return redirect('ai_settings')

    return render(request, 'accounting/ai_settings.html', {
        'config': config,
        'providers': PROVIDERS,
    })


@login_required
@never_cache
def openrouter_models(request):
    """Live model catalog, so new frontier models appear without a deploy."""
    try:
        return JsonResponse({'models': fetch_openrouter_models()})
    except Exception as exc:
        return JsonResponse({'models': [], 'error': str(exc)[:200]}, status=502)


@login_required
@never_cache
def statement_status(request):
    """Lets the dashboard poll for background processing without a manual refresh."""
    if not request.user.organization:
        return JsonResponse({'in_flight': 0})

    in_flight = Statement.objects.filter(
        account__organization=request.user.organization,
        status__in=Statement.IN_FLIGHT,
    ).count()
    return JsonResponse({'in_flight': in_flight})


@login_required
@never_cache
def delete_transaction(request, transaction_id):
    if request.method == 'POST':
        password = request.POST.get('root_password')
        
        # IDOR Fix: Ensure transaction belongs to the user's organization
        transaction = get_object_or_404(
            Transaction, 
            id=transaction_id, 
            account__organization=request.user.organization
        )
        
        # Verify root password
        root_pwd = getattr(settings, 'DELETE_ROOT_PASSWORD', 'root')
        if password == root_pwd:
            transaction.delete()
            messages.success(request, 'Transaction deleted successfully.')
        else:
            messages.error(request, 'Incorrect root password. Transaction not deleted.')
            
    return redirect('dashboard')

@login_required
@never_cache
def delete_all_accounts(request):
    if request.method == 'POST':
        password = request.POST.get('root_password')
        
        # Verify root password
        root_pwd = getattr(settings, 'DELETE_ROOT_PASSWORD', 'root')
        if password == root_pwd:
            # Delete all accounts belonging to the user's organization
            accounts = Account.objects.filter(organization=request.user.organization)
            count = accounts.count()
            accounts.delete()
            messages.success(request, f'Successfully deleted all {count} account(s) and their associated data.')
        else:
            messages.error(request, 'Incorrect root password. Accounts were not deleted.')
            
    return redirect('upload_statement')

