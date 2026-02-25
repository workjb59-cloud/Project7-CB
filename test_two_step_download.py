"""
Test clicking LinkButton3 (opens modal) then lnk_down_file (downloads)
"""
import os
import sys

os.environ['AWS_ACCESS_KEY_ID'] = 'test'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'test'
os.environ['AWS_BUCKET_NAME'] = 'test'

from scraper import KCSBScraper
from bs4 import BeautifulSoup

TEST_URL = "https://www.csb.gov.kw/Pages/Statistics?ID=60&ParentCatID=70"

print("="*70)
print("TWO-STEP DOWNLOAD TEST")
print("="*70)
print()

scraper = KCSBScraper('test', 'test', 'test')

try:
    # STEP 1: Click LinkButton3 to open modal/detail view
    print("STEP 1: Click LinkButton3 (opens detail/modal)")
    print("-" * 70)
    
    response = scraper.session.get(TEST_URL, timeout=30)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    form_data = scraper.get_viewstate_data(soup)
    form_data['__EVENTTARGET'] = 'ctl00$MainContent$RPT_Statistic$ctl01$LinkButton3'
    form_data['__EVENTARGUMENT'] = ''
    
    # Add all form fields
    form = soup.find('form')
    if form:
        for inp in form.find_all('input'):
            name = inp.get('name')
            if name and name not in form_data:
                form_data[name] = inp.get('value', '')
    
    print("Posting to LinkButton3...")
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
    
    # Parse the response
    soup2 = BeautifulSoup(response.content, 'html.parser')
    
    # Look for the download link
    download_link = soup2.find('a', {'id': 'MainContent_lnk_down_file'})
    
    if download_link:
        print("✓ Found download link in response!")
        print(f"  ID: {download_link.get('id')}")
        print(f"  Href: {download_link.get('href')}")
        
        # Extract the event target
        href = download_link.get('href', '')
        if '__doPostBack' in href:
            import re
            match = re.search(r"__doPostBack\('([^']+)'", href)
            if match:
                download_event_target = match.group(1)
                print(f"  Event target: {download_event_target}")
                
                # STEP 2: Click the actual download button
                print("\nSTEP 2: Click lnk_down_file (actual download)")
                print("-" * 70)
                
                # Get fresh ViewState from response
                form_data2 = scraper.get_viewstate_data(soup2)
                form_data2['__EVENTTARGET'] = download_event_target
                form_data2['__EVENTARGUMENT'] = ''
                
                # Add all form fields from response
                form2 = soup2.find('form')
                if form2:
                    for inp in form2.find_all('input'):
                        name = inp.get('name')
                        if name and name not in form_data2:
                            form_data2[name] = inp.get('value', '')
                
                print(f"Posting to {download_event_target}...")
                download_response = scraper.session.post(
                    TEST_URL,
                    data=form_data2,
                    headers={
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'Referer': TEST_URL
                    },
                    timeout=60,
                    stream=True
                )
                
                content_type = download_response.headers.get('Content-Type', '')
                print(f"Response: {content_type}")
                print(f"Size: {len(download_response.content)} bytes")
                
                if 'pdf' in content_type.lower() or 'octet-stream' in content_type.lower():
                    # Check if it's actually a PDF
                    content = download_response.content
                    if content[:4] == b'%PDF':
                        print("\n✅ SUCCESS! Got valid PDF file!")
                        print(f"   File size: {len(content):,} bytes")
                        print("   ✓ Valid PDF signature")
                    elif content[:2] == b'PK':
                        print("\n✅ SUCCESS! Got Excel file (ZIP format)!")
                        print(f"   File size: {len(content):,} bytes")
                        print("   ✓ Valid ZIP/Excel signature")
                    else:
                        print(f"\n✅ SUCCESS! Got binary file!")
                        print(f"   File size: {len(content):,} bytes")
                        print(f"   First 4 bytes: {content[:4]}")
                elif 'html' in content_type.lower():
                    print("\n❌ Still getting HTML")
                    print(f"   Size: {len(download_response.content)} bytes")
                else:
                    print(f"\n⚠️  Got: {content_type}")
            else:
                print("❌ Could not extract event target from href")
        else:
            print("⚠️  Download link doesn't use __doPostBack")
    else:
        print("❌ Download link NOT found in response")
        print("\nLooking for alternative download links...")
        
        # Look for ANY link with 'download' or similar
        all_links = soup2.find_all('a', href=lambda x: x and 'doPostBack' in x)
        print(f"Found {len(all_links)} links with __doPostBack")
        
        for link in all_links[:10]:
            link_id = link.get('id', 'no-id')
            link_text = link.get_text(strip=True)[:50]
            print(f"  {link_id}: {link_text}")
    
    print("\n" + "="*70)
    
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
