from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from accounting.models import Transaction
from .forms import CustomUserCreationForm
from accounting.ai_service import generate_financial_insights

@login_required
def dashboard(request):
    transactions = []
    if request.user.organization:
        transactions = Transaction.objects.filter(account__organization=request.user.organization).order_by('-date')[:10]
        
    return render(request, 'core/dashboard.html', {'transactions': transactions})

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
