"""
Compare our form data with what's actually on the page
Also try a direct download approach
"""
import os
import sys

os.environ['AWS_ACCESS_KEY_ID'] = 'test'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'test'
os.environ['AWS_BUCKET_NAME'] = 'test'

from scraper import KCSBScraper
from bs4 import BeautifulSoup
from urllib.parse import urljoin, parse_qs, urlparse
import requests

TEST_URL = "https://www.csb.gov.kw/Pages/Statistics?ID=60&ParentCatID=70"
EVENT_TARGET = "ctl00$MainContent$RPT_Statistic$ctl01$LinkButton3"

print("="*70)
print("TRYING ALTERNATIVE DOWNLOAD METHODS")
print("="*70)
print()

scraper = KCSBScraper('test', 'test', 'test')

try:
    # Load page
    print("Loading page...")
    response = scraper.session.get(TEST_URL, timeout=30)
    soup = BeautifulSoup(response.content, 'html.parser')
    print("✓ Page loaded\n")
    
    # Check if there's a direct URL pattern
    print("METHOD 1: Check for direct download URLs")
    print("-" * 70)
    
    # Look at the page source for any hints about file URLs
    link = soup.find('a', href=lambda x: x and 'LinkButton3' in x)
    if link:
        print(f"Link href: {link.get('href')}")
        print(f"Link onclick: {link.get('onclick')}")
        
        # Check if there's any data attributes
        for attr in link.attrs:
            if attr.startswith('data-'):
                print(f"  {attr}: {link.get(attr)}")
    
    # Look for any file URLs in page
    all_links = soup.find_all('a', href=True)
    pdf_links = [a for a in all_links if 'pdf' in a.get('href', '').lower()]
    xls_links = [a for a in all_links if 'xls' in a.get('href', '').lower() or 'excel' in a.get('href', '').lower()]
    
    print(f"\nDirect PDF links found: {len(pdf_links)}")
    print(f"Direct XLS links found: {len(xls_links)}")
    
    if pdf_links:
        print("\nFirst few PDF links:")
        for link in pdf_links[:3]:
            print(f"  {link.get('href')}")
    
    print("\n" + "="*70)
    print("METHOD 2: Try minimal postback")
    print("-" * 70)
    
    # Try with absolutely minimal form data - just the essentials
    form_data_minimal = {
        '__EVENTTARGET': EVENT_TARGET,
        '__EVENTARGUMENT': '',
        '__VIEWSTATE': soup.find('input', {'name': '__VIEWSTATE'}).get('value'),
        '__VIEWSTATEGENERATOR': soup.find('input', {'name': '__VIEWSTATEGENERATOR'}).get('value'),
        '__EVENTVALIDATION': soup.find('input', {'name': '__EVENTVALIDATION'}).get('value')
    }
    
    print("Trying with ONLY ViewState fields...")
    print(f"Form data keys: {list(form_data_minimal.keys())}")
    
    response = scraper.session.post(
        TEST_URL,
        data=form_data_minimal,
        headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': TEST_URL
        },
        timeout=60
    )
    
    content_type = response.headers.get('Content-Type', '')
    print(f"Response: {content_type}")
    print(f"Size: {len(response.content)} bytes")
    
    if 'pdf' in content_type:
        print("✅ SUCCESS with minimal form data!")
    elif len(response.content) == 270695:
        print("❌ Same HTML page returned")
    else:
        print(f"⚠️  Different response (size: {len(response.content)})")
    
    print("\n" + "="*70)
    print("METHOD 3: Check for ASP.NET AJAX")
    print("-" * 70)
    
    # Check if page uses ScriptManager (AJAX-enabled)
    script_manager = soup.find('input', {'name': '__ASYNCPOST'})
    if script_manager:
        print("⚠️  Page uses ASP.NET AJAX!")
        print("Trying async postback...")
        
        form_data_async = form_data_minimal.copy()
        form_data_async['__ASYNCPOST'] = 'true'
        form_data_async['ScriptManager1'] = f'ScriptManager1|{EVENT_TARGET}'
        
        response = scraper.session.post(
            TEST_URL,
            data=form_data_async,
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'Referer': TEST_URL,
                'X-MicrosoftAjax': 'Delta=true'
            },
            timeout=60
        )
        
        content_type = response.headers.get('Content-Type', '')
        print(f"Response: {content_type}")
        print(f"Size: {len(response.content)} bytes")
        
        if 'pdf' in content_type:
            print("✅ SUCCESS with AJAX postback!")
        else:
            # Show first 500 chars
            preview = response.content[:500].decode('utf-8', errors='ignore')
            print(f"Response preview:\n{preview}\n")
    else:
        print("✓ Page does NOT use ASP.NET AJAX")
    
    print("\n" + "="*70)
    print("METHOD 4: Analyze response for errors")
    print("-" * 70)
    
    # Load page again and do full postback
    response = scraper.session.get(TEST_URL, timeout=30)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    form_data = scraper.get_viewstate_data(soup)
    form_data['__EVENTTARGET'] = EVENT_TARGET
    form_data['__EVENTARGUMENT'] = ''
    
    # Get all form fields
    form = soup.find('form')
    if form:
        all_inputs = form.find_all('input')
        for inp in all_inputs:
            name = inp.get('name')
            if name and name not in form_data:
                form_data[name] = inp.get('value', '')
    
    response = scraper.session.post(
        TEST_URL,
        data=form_data,
        headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': TEST_URL,
            'Origin': 'https://www.csb.gov.kw'
        },
        timeout=60
    )
    
    # Parse response for any ASP.NET error messages
    response_soup = BeautifulSoup(response.content, 'html.parser')
    
    # Check for validation errors
    validation_summary = response_soup.find('div', {'class': 'validation-summary-errors'})
    if validation_summary:
        print("❌ ASP.NET Validation Errors:")
        print(validation_summary.get_text(strip=True))
    
    # Check for ViewState errors
    if 'viewstate' in response.text.lower() and 'error' in response.text.lower():
        print("⚠️  Possible ViewState error detected")
    
    # Check if the page structure changed (indicating postback was processed)
    response_vs = response_soup.find('input', {'name': '__VIEWSTATE'})
    if response_vs:
        original_vs = soup.find('input', {'name': '__VIEWSTATE'}).get('value')
        new_vs = response_vs.get('value')
        
        if original_vs == new_vs:
            print("❌ ViewState unchanged - postback NOT processed")
        else:
            print("✓ ViewState changed - postback WAS processed")
            print("⚠️  But still returned HTML instead of file")
    
    print("\n" + "="*70)
    print("DIAGNOSIS COMPLETE")
    print("="*70)
    
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
