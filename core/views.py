from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from accounting.models import Transaction
from .forms import CustomUserCreationForm

@login_required
def dashboard(request):
    transactions = []
    if request.user.organization:
        transactions = Transaction.objects.filter(account__organization=request.user.organization).order_by('-date')[:10]
        
    return render(request, 'core/dashboard.html', {'transactions': transactions})

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
