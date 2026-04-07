from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from accounting.models import Transaction
from .forms import CustomUserCreationForm
from accounting.ai_service import generate_financial_insights
from django.db.models import Sum
from decimal import Decimal

@login_required
def dashboard(request):
    transactions = []
    total_income = Decimal('0.00')
    total_expenses = Decimal('0.00')
    net_balance = Decimal('0.00')
    category_data = {}
    
    if request.user.organization:
        org_txs = Transaction.objects.filter(account__organization=request.user.organization)
        transactions = org_txs.order_by('-date')[:10]
        
        for tx in org_txs:
            if tx.amount > 0:
                total_income += tx.amount
            else:
                total_expenses += abs(tx.amount)
                
                # Aggregate expenses by category for the chart
                cat = tx.category if tx.category else 'Uncategorized'
                category_data[cat] = category_data.get(cat, Decimal('0.00')) + abs(tx.amount)
                
        net_balance = total_income - total_expenses
        
    # Prepare data for Chart.js
    chart_labels = list(category_data.keys())
    chart_values = [float(v) for v in category_data.values()]
        
    context = {
        'transactions': transactions,
        'total_income': total_income,
        'total_expenses': total_expenses,
        'net_balance': net_balance,
        'chart_labels': chart_labels,
        'chart_values': chart_values,
    }
    return render(request, 'core/dashboard.html', context)

@login_required
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
            insights = generate_financial_insights(tx_data)
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
