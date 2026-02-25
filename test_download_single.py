"""
Test downloading a specific file from the problematic page
This helps verify the ASP.NET postback is working correctly
"""
import os
import sys

os.environ['AWS_ACCESS_KEY_ID'] = 'test'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'test'
os.environ['AWS_BUCKET_NAME'] = 'test'

from scraper import KCSBScraper
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

# The problematic page
TEST_URL = "https://www.csb.gov.kw/Pages/Statistics?ID=60&ParentCatID=70"

# Try to download the first file from the list
EVENT_TARGET = "ctl00$MainContent$RPT_Statistic$ctl01$LinkButton3"  # 2024 PDF

print("="*70)
print("TESTING FILE DOWNLOAD")
print("="*70)
print(f"URL: {TEST_URL}")
print(f"Event Target: {EVENT_TARGET}")
print(f"File: إحصاءات الاتصالات وتكنولوجيا المعلومات2024 (PDF)")
print()

scraper = KCSBScraper('test', 'test', 'test')

try:
    # Step 1: Loading page...
    print("Step 1: Loading page...")
    response = scraper.session.get(TEST_URL, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, 'html.parser')
    print("✓ Page loaded")
    
    # Check cookies after GET
    cookies = scraper.session.cookies.get_dict()
    if cookies:
        print(f"✓ Cookies set: {list(cookies.keys())}")
    else:
        print("⚠️  No cookies set by server")
    print()
    
    # Get ViewState
    print("Step 2: Extracting ViewState...")
    form_data = scraper.get_viewstate_data(soup)
    print(f"✓ Found ViewState ({len(form_data['__VIEWSTATE'])} chars)")
    print(f"✓ Found ViewStateGenerator: {form_data.get('__VIEWSTATEGENERATOR', 'N/A')}")
    print(f"✓ Found EventValidation ({len(form_data.get('__EVENTVALIDATION', ''))} chars)")
    print()
    
    # Add ALL form fields (ASP.NET requires all fields, not just hidden)
    print("Step 3: Collecting ALL form fields...")
    form = soup.find('form')
    field_count = 0
    
    if form:
        # Get all input fields
        all_inputs = form.find_all('input')
        for inp in all_inputs:
            name = inp.get('name')
            if not name or name in form_data:
                continue
            
            input_type = inp.get('type', '').lower()
            
            if input_type == 'checkbox' or input_type == 'radio':
                if inp.get('checked'):
                    form_data[name] = inp.get('value', 'on')
                    field_count += 1
            else:
                form_data[name] = inp.get('value', '')
                field_count += 1
        
        # Get all select fields
        all_selects = form.find_all('select')
        for select in all_selects:
            name = select.get('name')
            if not name or name in form_data:
                continue
            
            selected = select.find('option', selected=True)
            if selected:
                form_data[name] = selected.get('value', '')
            else:
                first_option = select.find('option')
                form_data[name] = first_option.get('value', '') if first_option else ''
            field_count += 1
        
        # Get all textarea fields
        all_textareas = form.find_all('textarea')
        for textarea in all_textareas:
            name = textarea.get('name')
            if name and name not in form_data:
                form_data[name] = textarea.get_text(strip=True)
                field_count += 1
    
    print(f"✓ Added {field_count} form fields (text inputs, selects, textareas, etc.)")
    print(f"✓ Total form fields: {len(form_data)}")
    print()
    
    # Set event target
    form_data['__EVENTTARGET'] = EVENT_TARGET
    form_data['__EVENTARGUMENT'] = ''
    
    # Get form action URL
    form_action_url = TEST_URL  # Default
    if form:
        form_action = form.get('action')
        if form_action:
            form_action_url = urljoin(TEST_URL, form_action)
            print(f"Step 3b: Form action URL")
            print(f"✓ Form action: {form_action}")
            print(f"✓ Resolved URL: {form_action_url}")
            print()
    
    # Prepare headers
    post_headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Referer': TEST_URL,
        'Origin': 'https://www.csb.gov.kw',
        'Accept': '*/*',
        'Accept-Language': 'ar,en;q=0.9',
        'Cache-Control': 'no-cache'
    }
    
    print("Step 4: Sending POST request...")
    print(f"POST URL: {form_action_url}")
    print(f"Headers:")
    for key, val in post_headers.items():
        print(f"  {key}: {val}")
    print()
    
    # Post the form
    download_response = scraper.session.post(
        form_action_url,
        data=form_data,
        headers=post_headers,
        timeout=60,
        stream=True,
        allow_redirects=True
    )
    
    download_response.raise_for_status()
    
    print("Step 5: Analyzing response...")
    content_type = download_response.headers.get('Content-Type', '')
    content_disposition = download_response.headers.get('Content-Disposition', '')
    content_length = download_response.headers.get('Content-Length', 'Unknown')
    
    print(f"Response Headers:")
    print(f"  Content-Type: {content_type}")
    print(f"  Content-Disposition: {content_disposition}")
    print(f"  Content-Length: {content_length}")
    print()
    
    # Check content
    content = download_response.content
    
    print(f"Response Size: {len(content)} bytes")
    print()
    
    # Check if it's actually a file or HTML
    if 'application/pdf' in content_type:
        print("✅ SUCCESS! Got PDF file")
        print(f"   File size: {len(content):,} bytes")
        
        # Check PDF signature
        if content[:4] == b'%PDF':
            print("   ✓ Valid PDF signature")
        else:
            print("   ⚠️  PDF signature not found")
            
    elif 'text/html' in content_type:
        print("❌ FAILED! Got HTML instead of file")
        
        # Show preview
        try:
            preview = content[:1000].decode('utf-8', errors='ignore')
            print("\nHTML Preview:")
            print("-" * 70)
            print(preview)
            print("-" * 70)
        except:
            pass
            
    elif 'application/vnd' in content_type or 'application/octet-stream' in content_type:
        print("✅ SUCCESS! Got Excel file")
        print(f"   File size: {len(content):,} bytes")
        
    else:
        print(f"⚠️  UNEXPECTED content type: {content_type}")
        
        # Try to determine if it's binary or text
        try:
            text = content[:500].decode('utf-8', errors='ignore')
            if '<html' in text.lower() or '<!doctype' in text.lower():
                print("   Content appears to be HTML")
                print("\nPreview:")
                print("-" * 70)
                print(text)
                print("-" * 70)
            else:
                print("   Content appears to be text/other")
        except:
            print("   Content appears to be binary")
    
    print("\n" + "="*70)
    
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
