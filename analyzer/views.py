from django.shortcuts import render
from .utils import scrape_market_data
from .models import SearchLog

def home(request):
    report = None
    if request.method == "POST":
        print("POST request received!")
        url = request.POST.get('url')
        print(f"URL: {url}")
        report = scrape_market_data(url)
        if report:
            SearchLog.objects.create(url=url, results_found=len(report['all_products']))
            
    return render(request, 'analyzer/index.html', {'report': report})
