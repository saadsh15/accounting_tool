from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.contrib.auth import login
from django.http import HttpResponse
import csv
from accounting.models import Statement, Transaction
from .forms import CustomUserCreationForm
from accounting.ai_service import generate_financial_insights
from django.db.models import Sum
from decimal import Decimal

def landing_page(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'core/landing.html')

@login_required
@never_cache
def dashboard(request):
    transactions = []
    total_income = Decimal('0.00')
    total_expenses = Decimal('0.00')
    net_balance = Decimal('0.00')
    
    EXPENSE_CATEGORIES = [
        "Rent/Mortgage", "Utilities", "Groceries", 
        "Dining Out", "Transportation", "Insurance", "Entertainment", 
        "Healthcare", "Personal Care", "Debt Payments", "Savings/Investments", 
        "Education", "Miscellaneous", "Bank Fees"
    ]
    
    category_data = {cat: Decimal('0.00') for cat in EXPENSE_CATEGORIES}
    
    statements_in_flight = 0
    failed_statements = []

    if request.user.organization:
        org_statements = Statement.objects.filter(account__organization=request.user.organization)
        statements_in_flight = org_statements.filter(status__in=Statement.IN_FLIGHT).count()
        failed_statements = org_statements.filter(status=Statement.Status.FAILED).order_by('-uploaded_at')[:5]

        org_txs = Transaction.objects.filter(account__organization=request.user.organization)
        transactions = org_txs.order_by('-date')[:10]
        
        for tx in org_txs:
            if tx.amount > 0:
                total_income += tx.amount
            else:
                total_expenses += abs(tx.amount)
                
                # Aggregate expenses by category for the chart
                cat = tx.category if tx.category else 'Miscellaneous'
                matched_cat = None
                for std_cat in EXPENSE_CATEGORIES:
                    if std_cat.lower() == cat.lower():
                        matched_cat = std_cat
                        break
                
                if matched_cat:
                    category_data[matched_cat] += abs(tx.amount)
                else:
                    category_data["Miscellaneous"] += abs(tx.amount)
                
        net_balance = total_income - total_expenses
        
    # Prepare data for Chart.js (only non-zero categories for a clean chart)
    chart_labels = []
    chart_values = []
    for cat in EXPENSE_CATEGORIES:
        val = category_data[cat]
        if val > 0:
            chart_labels.append(cat)
            chart_values.append(float(val))
        
    context = {
        'transactions': transactions,
        'total_income': total_income,
        'total_expenses': total_expenses,
        'net_balance': net_balance,
        'chart_labels': chart_labels,
        'chart_values': chart_values,
        'statements_in_flight': statements_in_flight,
        'failed_statements': failed_statements,
    }
    return render(request, 'core/dashboard.html', context)

@login_required
@never_cache
def ai_insights(request):
    insights = None
    if request.user.organization:
        # Get the latest 50 transactions to send to the AI
        recent_txs = Transaction.objects.filter(account__organization=request.user.organization).order_by('-date')[:50]
        
        tx_data = [
            {
                'date': tx.date.strftime('%Y-%m-%d'),
                'description': tx.description,
                'amount': float(tx.amount),
                'category': tx.category
            }
            for tx in recent_txs
        ]
        
        if tx_data:
            insights = generate_financial_insights(tx_data, organization=request.user.organization)
        else:
            insights = "Upload a bank statement first so the AI has data to analyze."
            
    return render(request, 'core/ai_insights.html', {'insights': insights})

def signup(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('dashboard')
    else:
        form = CustomUserCreationForm()
    return render(request, 'registration/signup.html', {'form': form})

@login_required
@never_cache
def download_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="accounting_data.csv"'

    writer = csv.writer(response)
    writer.writerow(['Date', 'Description', 'Amount', 'Category', 'Account'])

    if request.user.organization:
        transactions = Transaction.objects.filter(account__organization=request.user.organization).order_by('-date')
        for tx in transactions:
            writer.writerow([tx.date, tx.description, tx.amount, tx.category, tx.account.name])

    return response
