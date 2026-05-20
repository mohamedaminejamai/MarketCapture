from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from .utils import scrape_market_data
from .models import SearchLog, SavedProduct

def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)  # Automatically log the user in after signing up
            return redirect('home')
    else:
        form = UserCreationForm()
    return render(request, 'registration/register.html', {'form': form})

# @login_required  <-- Remove or comment this out to make the home page public
def home(request):
    report = None
    error = None
    if request.method == "POST":
        print("POST request received!")
        url = request.POST.get('url')
        print(f"URL: {url}")
        report = scrape_market_data(url)
        if report:
            SearchLog.objects.create(url=url, results_found=len(report['all_products']))
        else:
            error = "We couldn't extract product data from this link or search query. The site may be blocking bots or the page structure is unrecognized."
            
    return render(request, 'analyzer/index.html', {'report': report, 'error': error})

@login_required
def delete_product(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(SavedProduct, id=product_id, user=request.user)
        product.delete()
    return redirect('dashboard')

@login_required
def save_product(request):
    if request.method == 'POST':
        SavedProduct.objects.create(
            user=request.user,
            name=request.POST.get('name'),
            price=request.POST.get('price'),
            url=request.POST.get('url'),
            image=request.POST.get('image'),
            source=request.POST.get('source')
        )
    return redirect('dashboard')

@login_required
def dashboard(request):
    # Fetch recent logs to populate the history chart
    recent_logs = SearchLog.objects.order_by('-timestamp')[:10]
    chart_labels = [log.timestamp.strftime("%b %d") for log in recent_logs]
    chart_values = [log.results_found for log in recent_logs]
    
    # Fetch saved products for the current user
    saved_products = SavedProduct.objects.filter(user=request.user).order_by('-saved_at')

    # Example dummy data for the suggestions list
    suggestions = [
        {'name': 'Apple AirPods Pro', 'reason': 'Price dropped by 15% recently', 'trend': '▼'},
        {'name': 'Samsung 4K TV', 'reason': 'High search volume today', 'trend': '▲'},
    ]
    
    context = {
        'chart_labels': chart_labels,
        'chart_values': chart_values,
        'suggestions': suggestions,
        'saved_products': saved_products,
        'recent_logs': recent_logs
    }
    return render(request, 'analyzer/dashboard.html', context)
