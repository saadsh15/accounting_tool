from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
import os
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from .models import Account, AISettings, Statement, Transaction
from core.models import Organization
from .providers import PROVIDERS
from .ai_service import check_connection, fetch_openrouter_models, resolve_ai_config
from .queue import enqueue_statement, is_configured as queue_is_configured, verify_signature
from .tasks import process_statement_job
from django.contrib import messages
from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import json
import logging

logger = logging.getLogger(__name__)

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

            # Hand the work off: OCR + LLM calls outlast the serverless function budget.
            # With no queue configured this runs inline instead.
            try:
                queued = enqueue_statement(statement.id)
                if queued:
                    messages.info(request, 'Statement uploaded. Extracting transactions in the background — this page will update when it finishes.')
                else:
                    statement.refresh_from_db()
                    if statement.status == Statement.Status.DONE and statement.transactions_found:
                        messages.success(request, f'Statement processed. {statement.transactions_found} transactions found.')
                    elif statement.status == Statement.Status.DONE:
                        messages.warning(request, 'Statement processed, but no transactions could be extracted. Ensure the file contains clear, tabular transaction data.')
                    else:
                        messages.error(request, f'Could not process statement: {statement.error_message}')
            except Exception as e:
                # Queue unreachable. Mark it failed rather than silently stranding an
                # upload that nobody will ever process.
                logger.exception("Could not queue statement %s", statement.id)
                statement.status = Statement.Status.FAILED
                statement.error_message = f'Could not queue for processing: {e}'
                statement.save(update_fields=['status', 'error_message'])
                messages.error(request, 'Statement uploaded but could not be queued for processing. Please try again.')

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

@csrf_exempt
@require_POST
def process_statement_webhook(request):
    """Endpoint QStash calls back to run the extraction.

    Public and session-less by necessity — QStash has no cookies — so the JWT
    signature is the ONLY thing preventing a stranger from driving this endpoint
    against arbitrary statement IDs. Never process an unverified request.
    """
    signature = request.headers.get('Upstash-Signature', '')
    if not signature:
        return HttpResponseForbidden('Missing signature.')

    url = f"{settings.SITE_URL.rstrip('/')}{reverse('process_statement_webhook')}"
    try:
        valid = verify_signature(signature, request.body, url)
    except ValueError as exc:
        logger.error("Webhook rejected: %s", exc)
        return HttpResponseForbidden('Signing keys not configured.')

    if not valid:
        logger.warning("Webhook rejected: invalid signature.")
        return HttpResponseForbidden('Invalid signature.')

    try:
        statement_id = json.loads(request.body)['statement_id']
    except (ValueError, KeyError):
        return HttpResponse('Bad payload.', status=400)

    # A raised exception returns 500, which is QStash's cue to retry. The job marks
    # the statement failed before re-raising, so a permanent failure is still visible.
    count = process_statement_job(statement_id)
    return JsonResponse({'statement_id': statement_id, 'transactions': count})


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

