"""
Try clicking the LinkButton again with absolutely minimal data
to see if direct download works
"""
import os
import sys

os.environ['AWS_ACCESS_KEY_ID'] = 'test'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'test'
os.environ['AWS_BUCKET_NAME'] = 'test'

from scraper import KCSBScraper
from bs4 import BeautifulSoup

TEST_URL = "https://www.csb.gov.kw/Pages/Statistics?ID=18&ParentCatID=2"
EVENT_TARGET = "ctl00$MainContent$RPT_Statistic$ctl05$LinkButton3"

print("="*70)
print("TESTING DIRECT DOWNLOAD (ONE-STEP)")
print("="*70)
print()

scraper = KCSBScraper('test', 'test', 'test')

try:
    # Load page
    print("Loading page...")
    response = scraper.session.get(TEST_URL, timeout=30)
    soup = BeautifulSoup(response.content, 'html.parser')
    original_size = len(response.content)
    print(f"Original page size: {original_size:,} bytes")
    print()
    
    # Try with minimal ViewState only
    print("METHOD 1: Minimal postback (ViewState only)")
    print("-" * 70)
    
    vs = soup.find('input', {'name': '__VIEWSTATE'}).get('value')
    vsg = soup.find('input', {'name': '__VIEWSTATEGENERATOR'}).get('value')
    ev = soup.find('input', {'name': '__EVENTVALIDATION'}).get('value')
    
    form_data = {
        '__EVENTTARGET': EVENT_TARGET,
        '__EVENTARGUMENT': '',
        '__VIEWSTATE': vs,
        '__VIEWSTATEGENERATOR': vsg,
        '__EVENTVALIDATION': ev
    }
    
    response = scraper.session.post(
        TEST_URL,
        data=form_data,
        headers={'Content-Type': 'application/x-www-form-urlencoded', 'Referer': TEST_URL},
        timeout=60,
        stream=True
    )
    
    ct = response.headers.get('Content-Type', '')
    size = len(response.content)
    
    print(f"Response: {ct}")
    print(f"Size: {size:,} bytes")
    
    if 'pdf' in ct.lower() or 'octet-stream' in ct.lower():
        if response.content[:4] == b'%PDF':
            print("✅ SUCCESS! Got PDF directly")
        else:
            print(f"⚠️  Got binary, first 4 bytes: {response.content[:4]}")
    elif size == original_size:
        print("❌ Same page returned (postback ignored)")
    else:
        print(f"⚠️  Different HTML ({size:,} vs {original_size:,} bytes)")
    
    print()
    
    # Now try with ALL form fields
    print("METHOD 2: Complete form state")
    print("-" * 70)
    
    # Reload page for fresh state
    response = scraper.session.get(TEST_URL, timeout=30)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    form_data = scraper.get_viewstate_data(soup)
    form_data['__EVENTTARGET'] = EVENT_TARGET
    form_data['__EVENTARGUMENT'] = ''
    
    form = soup.find('form')
    if form:
        for inp in form.find_all('input'):
            name = inp.get('name')
            if name and name not in form_data:
                form_data[name] = inp.get('value', '')
    
    print(f"Form data fields: {len(form_data)}")
    
    response = scraper.session.post(
        TEST_URL,
        data=form_data,
        headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': TEST_URL,
            'Origin': 'https://www.csb.gov.kw'
        },
        timeout=60,
        stream=True
    )
    
    ct = response.headers.get('Content-Type', '')
    size = len(response.content)
    
    print(f"Response: {ct}")
    print(f"Size: {size:,} bytes")
    
    if 'pdf' in ct.lower() or 'octet-stream' in ct.lower():
        if response.content[:4] == b'%PDF':
            print("✅ SUCCESS! Got PDF with full form state")
        else:
            print(f"⚠️  Got binary, first 4 bytes: {response.content[:4]}")
    elif size == original_size:
        print("❌ Same page returned (postback ignored)")
    else:
        print(f"⚠️  Different HTML ({size:,} vs {original_size:,} bytes)")
        
        # Check if ViewState changed
        response_soup = BeautifulSoup(response.content, 'html.parser')
        new_vs = response_soup.find('input', {'name': '__VIEWSTATE'})
        if new_vs:
            if new_vs.get('value') == vs:
                print("   ViewState UNCHANGED")
            else:
                print("   ViewState CHANGED")
    
    print("\n" + "="*70)
    
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
