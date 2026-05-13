import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import re
import json
from urllib.parse import urljoin, urlparse, quote
from datetime import datetime

def get_price_from_offers(offers):
    """Helper to safely extract price details from a JSON-LD offer object."""
    if not offers: return None, None
    if isinstance(offers, list):
        for offer in offers:
            if isinstance(offer, dict) and 'price' in offer:
                offers = offer
                break
        else:
            offers = offers[0] if offers else {}
            
    if not isinstance(offers, dict): return None, None
        
    price = offers.get('price')
    if not price: return None, None
        
    try:
        numeric_price = float(price)
        currency = offers.get('priceCurrency', '')
        return f"{numeric_price} {currency}".strip(), numeric_price
    except (ValueError, TypeError):
        return None, None

def find_products_in_jsonld(data, base_url, products_list):
    """Recursively search for Product entities in parsed JSON-LD data."""
    if isinstance(data, dict):
        type_val = data.get('@type', '')
        is_product = (type_val == 'Product') if isinstance(type_val, str) else ('Product' in type_val if isinstance(type_val, list) else False)
            
        if is_product:
            name = data.get('name', 'Unknown Product')
            
            image = data.get('image', '')
            if isinstance(image, list) and image:
                image = image[0]
            elif isinstance(image, dict):
                image = image.get('url', '')
            if not isinstance(image, str): image = ''
                
            price_display, price_numeric = get_price_from_offers(data.get('offers'))
            
            prod_url = data.get('url', base_url)
            prod_url = urljoin(base_url, prod_url) if isinstance(prod_url, str) else base_url
            
            domain = urlparse(base_url).netloc
            domain_parts = domain.replace('www.', '').split('.')
            source_name = domain_parts[0].capitalize() if domain_parts else 'Unknown'

            if price_numeric is not None:
                products_list.append({
                    'name': str(name)[:80],
                    'price_display': price_display,
                    'price_numeric': price_numeric,
                    'original_price': price_numeric,
                    'url': prod_url,
                    'image': image,
                    'source': source_name,
                    'discount_pct': 0
                })
        
        for value in data.values():
            find_products_in_jsonld(value, base_url, products_list)
            
    elif isinstance(data, list):
        for item in data:
            find_products_in_jsonld(item, base_url, products_list)

def _parse_price(price_str):
    """Parses a price string into a float, handling various formats."""
    if not price_str:
        return None
    
    text = str(price_str)

    # Handle formats like "1.234,56" (German) vs "1,234.56" (US)
    if ',' in text and '.' in text:
        # If comma is the last separator, it's the decimal
        if text.rfind(',') > text.rfind('.'):
            text = text.replace('.', '').replace(',', '.')
        else:
            # If dot is the last, it's the decimal
            text = text.replace(',', '')
    else:
        # If only one separator type, assume it's a decimal
        text = text.replace(',', '.')

    # Remove all non-numeric characters except for the decimal point
    text = re.sub(r'[^\d.]', '', text)
    
    try:
        return float(text)
    except (ValueError, TypeError):
        return None

def scrape_market_data(url):
    # Detect if the input is a keyword search instead of a valid URL
    if not url.startswith('http://') and not url.startswith('https://'):
        url = f"https://www.ebay.com/sch/i.html?_nkw={quote(url)}"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080}
            )
            page = context.new_page()
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                print(f"Page load timeout/error: {e}. Attempting to continue with loaded content...")
                
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(3000)  # Give JS frameworks time to render products
            
            html_content = page.content()
            browser.close()
            
        soup = BeautifulSoup(html_content, "html.parser")
        products = []

        # 1. Strategy: Universal JSON-LD Extraction
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                if not script.string: continue
                data = json.loads(script.string)
                find_products_in_jsonld(data, url, products)
            except (json.JSONDecodeError, TypeError):
                continue

        # 2. Strategy: Fallback to HTML parsing if JSON-LD extraction found no products
        if not products:
            items = soup.find_all(['article', 'div', 'li'], class_=re.compile(r'prd|item|card|product|core|result|grid', re.I))

            for item in items:
                # Use a broad except to ensure one malformed item doesn't stop the whole scrape
                try: 
                    # 1. Image Extraction (Lazy-load aware)
                    img_tag = item.find('img')
                    image_url = ""
                    if img_tag:
                        image_url = img_tag.get('data-src') or img_tag.get('src') or img_tag.get('data-original')
                    
                    # 2. Link Extraction
                    link_tag = item.find('a', href=True)
                    if not link_tag: continue
                    product_url = urljoin(url, link_tag['href'])

                    # 3. Name Extraction
                    name_tag = item.find(['h2', 'h3', 'h4']) or item.find(class_=re.compile(r'name|title|heading', re.I))
                    name = name_tag.get_text().strip() if name_tag else "Product Name"

                    # 4. Advanced Price Extraction
                    numeric_price, original_price, raw_price_display = None, None, None
                    item_soup = BeautifulSoup(str(item), 'html.parser') # Work on a copy to safely modify it

                    # --- Step 1: Find original price (strikethrough) and remove it ---
                    original_price_tag = item_soup.find(['del', 's'], text=re.compile(r'\d'))
                    if original_price_tag:
                        original_price = _parse_price(original_price_tag.get_text())
                        original_price_tag.decompose()

                    # --- Step 2: Find current price in the remaining HTML ---
                    price_area = item_soup.find(class_=re.compile(r'price', re.I)) or item_soup
                    price_match = re.search(r'((?:[\$€£]|USD|EUR|Dhs|MAD)\s?\d[\d,.]*)|(\d[\d,.]*\s?(?:Dhs|MAD|DH))', price_area.get_text(separator=' '))

                    if price_match:
                        raw_price_display = price_match.group(0).strip()
                        numeric_price = _parse_price(raw_price_display)

                    # --- Step 3: Validation and Finalization ---
                    if not numeric_price or numeric_price < 1.0:
                        continue # Skip if no valid current price is found

                    if not original_price or original_price < numeric_price:
                        original_price = numeric_price

                    discount_pct = round(((original_price - numeric_price) / original_price) * 100) if original_price > numeric_price else 0
                        
                    domain = urlparse(url).netloc
                    domain_parts = domain.replace('www.', '').split('.')
                    source_name = domain_parts[0].capitalize() if domain_parts else 'Unknown'
                    products.append({
                        'name': name[:80],
                        'price_display': raw_price_display,
                        'price_numeric': numeric_price,
                        'original_price': original_price,
                        'url': product_url,
                        'image': image_url,
                        'source': source_name,
                        'discount_pct': discount_pct
                    })
                except Exception:
                    continue

        if not products: return None

        # Sort based on numeric value
        products.sort(key=lambda x: x['price_numeric'])
        
        cheapest = products[0]
        expensive = products[-1]
        biggest_discount = max(products, key=lambda x: x.get('discount_pct', 0))
        sources = set(p.get('source', 'Unknown') for p in products)
        
        # Dynamic Price Drop Alert
        price_alert = None
        if biggest_discount.get('discount_pct', 0) > 0:
            price_alert = {
                'name': biggest_discount['name'],
                'drop_pct': biggest_discount['discount_pct'],
                'original_price': biggest_discount['original_price'],
                'current_price': biggest_discount['price_display']
            }
        
        return {
            'all_products': products,
            'cheapest': cheapest,
            'expensive': expensive,
            'biggest_discount': biggest_discount if biggest_discount.get('discount_pct', 0) > 0 else None,
            'count': len(products),
            'stats': {
                'total_products': len(products),
                'source_count': len(sources),
                'spread_display': f"{cheapest['price_display']} - {expensive['price_display']}",
                'scan_time': datetime.now().strftime("%I:%M %p")
            },
            'price_drop_alert': price_alert
        }
    except Exception as e:
        print(f"Universal Scraper Error: {e}")
        return None