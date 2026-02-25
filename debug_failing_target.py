"""
Debug what's in the HTML response for a specific event target
"""
import os
import sys

os.environ['AWS_ACCESS_KEY_ID'] = 'test'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'test'
os.environ['AWS_BUCKET_NAME'] = 'test'

from scraper import KCSBScraper
from bs4 import BeautifulSoup
import re

TEST_URL = "https://www.csb.gov.kw/Pages/Statistics?ID=18&ParentCatID=2"
# Use the failing event target from logs
EVENT_TARGET = "ctl00$MainContent$RPT_Statistic$ctl05$LinkButton3"

print("="*70)
print("DEBUGGING FAILING EVENT TARGET")
print("="*70)
print(f"URL: {TEST_URL}")
print(f"Event: {EVENT_TARGET}")
print()

scraper = KCSBScraper('test', 'test', 'test')

try:
    # Do step 1
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
    
    print("Posting to event target...")
    response = scraper.session.post(
        TEST_URL,
        data=form_data,
        headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': TEST_URL
        },
        timeout=60
    )
    
    print(f"Response: {response.headers.get('Content-Type')}")
    print(f"Size: {len(response.content)} bytes")
    print()
    
    # Parse HTML
    detail_soup = BeautifulSoup(response.content, 'html.parser')
    
    # Look for lnk_down_file
    print("Looking for 'lnk_down_file'...")
    download_link = detail_soup.find('a', {'id': lambda x: x and 'lnk_down_file' in x})
    
    if download_link:
        print(f"✓ Found: {download_link.get('id')}")
    else:
        print("❌ NOT found")
        print()
        print("Searching for ALL links with __doPostBack and 'download' related:")
        
        # Find all links with doPostBack
        all_links = detail_soup.find_all('a', href=lambda x: x and '__doPostBack' in x)
        print(f"Total __doPostBack links: {len(all_links)}")
        print()
        
        # Look for download-related links
        download_keywords = ['download', 'تحميل', 'file', 'ملف', 'pdf', 'xls']
        
        for link in all_links:
            link_id = link.get('id', '')
            link_text = link.get_text(strip=True)
            link_onclick = link.get('onclick', '')
            
            # Check if it matches any download keyword
            matches_download = any(kw in link_id.lower() or kw in link_text.lower() or kw in link_onclick.lower() 
                                  for kw in download_keywords)
            
            if matches_download or 'LinkButton' in link_id:
                print(f"Link: {link_id if link_id else 'no-id'}")
                if link_text:
                    print(f"  Text: {link_text[:60]}")
                print(f"  Href: {link.get('href', '')[:80]}")
                if link_onclick:
                    print(f"  OnClick: {link_onclick[:80]}")
                
                # Check for images (PDF/Excel icons)
                img = link.find('img')
                if img:
                    print(f"  Image: {img.get('src', '')}")
                print()
        
        print("-" * 70)
        print("Looking for buttons with 'download' or file indicators:")
        
        # Also check for actual button elements
        buttons = detail_soup.find_all('button')
        for btn in buttons:
            btn_id = btn.get('id', '')
            btn_text = btn.get_text(strip=True)
            btn_onclick = btn.get('onclick', '')
            
            if any(kw in btn_id.lower() or kw in btn_text.lower() or kw in btn_onclick.lower() 
                   for kw in download_keywords):
                print(f"Button: {btn_id}")
                print(f"  Text: {btn_text}")
                print(f"  OnClick: {btn_onclick[:100]}")
                print()
    
    print("="*70)
    
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
