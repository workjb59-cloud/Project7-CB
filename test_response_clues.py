"""
Search the HTML response for error messages or clues
"""
import os
import sys

os.environ['AWS_ACCESS_KEY_ID'] = 'test'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'test'
os.environ['AWS_BUCKET_NAME'] = 'test'

from scraper import KCSBScraper
from bs4 import BeautifulSoup

TEST_URL = "https://www.csb.gov.kw/Pages/Statistics?ID=60&ParentCatID=70"
EVENT_TARGET = "ctl00$MainContent$RPT_Statistic$ctl01$LinkButton3"

print("="*70)
print("SEARCHING RESPONSE FOR CLUES")
print("="*70)
print()

scraper = KCSBScraper('test', 'test', 'test')

try:
    # Do a full postback
    response = scraper.session.get(TEST_URL, timeout=30)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    form_data = scraper.get_viewstate_data(soup)
    form_data['__EVENTTARGET'] = EVENT_TARGET
    form_data['__EVENTARGUMENT'] = ''
    
    # Add all form fields
    form = soup.find('form')
    if form:
        for inp in form.find_all('input'):
            name = inp.get('name')
            if name and name not in form_data:
                form_data[name] = inp.get('value', '')
    
    print("Sending postback...")
    response = scraper.session.post(
        TEST_URL,
        data=form_data,
        headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': TEST_URL
        },
        timeout=60
    )
    
    print(f"Response size: {len(response.content)} bytes")
    print()
    
    # Parse response
    response_soup = BeautifulSoup(response.content, 'html.parser')
    response_text = response.text
    
    # 1. Check for error messages
    print("1. Checking for error messages...")
    print("-" * 70)
    
    error_indicators = [
        'error', 'exception', 'invalid', 'validation', 'failed',
        'unauthorized', 'forbidden', 'not found'
    ]
    
    for indicator in error_indicators:
        if indicator in response_text.lower():
            # Find context around the error
            idx = response_text.lower().find(indicator)
            context_start = max(0, idx - 100)
            context_end = min(len(response_text), idx + 200)
            context = response_text[context_start:context_end]
            
            # Clean up for display
            context = ' '.join(context.split())
            
            print(f"Found '{indicator}' at position {idx}:")
            print(f"  ...{context}...\n")
            break
    else:
        print("✓ No obvious error messages found\n")
    
    # 2. Check if LinkButton is still there
    print("2. Checking if download link is still visible...")
    print("-" * 70)
    
    response_link = response_soup.find('a', {'id': lambda x: x and 'LinkButton3' in x})
    if response_link:
        print(f"✓ LinkButton3 found in response:")
        print(f"  ID: {response_link.get('id')}")
        print(f"  Href: {response_link.get('href')}")
        print(f"  Enabled: {not response_link.get('disabled')}")
    else:
        print("❌ LinkButton3 NOT found in response - might be hidden/disabled")
    print()
    
    # 3. Check for JavaScript errors or alerts
    print("3. Checking for JavaScript alerts/errors...")
    print("-" * 70)
    
    scripts = response_soup.find_all('script')
    for script in scripts:
        script_text = script.get_text()
        if 'alert' in script_text or 'console.error' in script_text:
            print("Found alert/error in script:")
            print(script_text[:300])
            print()
            break
    else:
        print("✓ No JavaScript alerts found\n")
    
    # 4. Check for modal or popup that might contain the file
    print("4. Checking for modals or popups...")
    print("-" * 70)
    
    modals = response_soup.find_all('div', {'class': lambda x: x and 'modal' in str(x).lower()})
    if modals:
        print(f"Found {len(modals)} modal(s)")
        for idx, modal in enumerate(modals[:2], 1):
            print(f"\nModal {idx}:")
            print(f"  ID: {modal.get('id')}")
            print(f"  Classes: {modal.get('class')}")
            
            # Check for download links in modal
            modal_links = modal.find_all('a', href=True)
            pdf_links = [a for a in modal_links if 'pdf' in a.get('href', '').lower()]
            if pdf_links:
                print(f"  Contains {len(pdf_links)} PDF link(s)")
    else:
        print("No modals found\n")
    
    # 5. Check the actual title and meta to see which page was returned
    print("5. Identifying returned page...")
    print("-" * 70)
    
    title = response_soup.find('title')
    if title:
        print(f"Page title: {title.get_text(strip=True)}")
    
    # Check if it's the same page or redirected
    og_url = response_soup.find('meta', {'property': 'og:url'})
    if og_url:
        print(f"OG URL: {og_url.get('content')}")
    
    # Check final URL after redirects
    print(f"Final URL: {response.url}")
    print()
    
    # 6. Look for event validation errors specifically
    print("6. Checking for EventValidation errors...")
    print("-" * 70)
    
    if 'eventvalidation' in response_text.lower():
        print("⚠️  'eventvalidation' mentioned in response")
        # Find the context
        idx = response_text.lower().find('eventvalidation')
        context = response_text[max(0, idx-150):min(len(response_text), idx+150)]
        print(f"Context: {' '.join(context.split())[:200]}...\n")
    else:
        print("✓ No EventValidation errors\n")
    
    # 7. Check if there's a specific message about the file
    print("7. Searching for file-related messages...")
    print("-" * 70)
    
    file_keywords = ['download', 'file', 'pdf', 'تحميل', 'ملف']
    for keyword in file_keywords:
        if keyword in response_text.lower():
            positions = []
            start = 0
            while True:
                idx = response_text.lower().find(keyword, start)
                if idx == -1:
                    break
                positions.append(idx)
                start = idx + 1
            
            print(f"'{keyword}' appears {len(positions)} times")
            
            # Show first occurrence context if it looks like a message
            if positions and len(positions) < 100:  # Not overwhelming
                idx = positions[0]
                context = response_text[max(0, idx-80):min(len(response_text), idx+120)]
                context_clean = ' '.join(context.split())
                if len(context_clean) < 250:
                    print(f"  First: ...{context_clean}...")
    
    print("\n" + "="*70)
    print("ANALYSIS COMPLETE")
    print("="*70)
    
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
