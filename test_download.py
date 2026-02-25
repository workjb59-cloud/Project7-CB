"""
Debug script to test ASP.NET postback file download mechanism
This helps diagnose why files return HTML instead of PDF/Excel
"""
import os
import sys

# Set dummy env vars for testing
os.environ['AWS_ACCESS_KEY_ID'] = 'test'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'test'
os.environ['AWS_BUCKET_NAME'] = 'test'

from scraper import KCSBScraper
from bs4 import BeautifulSoup
import logging

# Set logging to DEBUG for more details
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Test URL - المجموعة الإحصائية السنوية
TEST_URL = "https://www.csb.gov.kw/Pages/Statistics?ID=18&ParentCatID=2"

print("="*60)
print("TESTING ASP.NET POSTBACK DOWNLOAD")
print("="*60)
print(f"\nTest URL: {TEST_URL}\n")

# Create scraper
scraper = KCSBScraper('test', 'test', 'test')

try:
    # Get the page
    print("Step 1: Fetching page...")
    response = scraper.session.get(TEST_URL, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, 'html.parser')
    print(f"✓ Page fetched successfully (status: {response.status_code})")
    
    # Extract ViewState
    print("\nStep 2: Extracting ViewState...")
    viewstate_data = scraper.get_viewstate_data(soup)
    print(f"✓ ViewState fields found:")
    for key in ['__VIEWSTATE', '__VIEWSTATEGENERATOR', '__EVENTVALIDATION']:
        value = viewstate_data.get(key, '')
        preview = value[:50] + '...' if len(value) > 50 else value
        print(f"  - {key}: {preview if value else '(not found)'}")
    
    # Find all hidden fields
    print("\nStep 3: Finding all hidden form fields...")
    hidden_inputs = soup.find_all('input', type='hidden')
    print(f"✓ Found {len(hidden_inputs)} hidden fields:")
    for hidden in hidden_inputs[:10]:  # Show first 10
        name = hidden.get('name', '')
        value = hidden.get('value', '')
        preview = value[:30] + '...' if len(value) > 30 else value
        print(f"  - {name}: {preview}")
    if len(hidden_inputs) > 10:
        print(f"  ... and {len(hidden_inputs) - 10} more")
    
    # Find download links
    print("\nStep 4: Finding download links in النشرات الإحصائية tab...")
    tab_content = soup.find('div', {'id': 'T3'})
    if tab_content:
        table = tab_content.find('table')
        if table:
            rows = table.find('tbody').find_all('tr') if table.find('tbody') else []
            print(f"✓ Found {len(rows)} rows in table")
            
            if rows:
                # Test with first file
                first_row = rows[0]
                cols = first_row.find_all('td')
                if len(cols) >= 2:
                    title = cols[0].get_text(strip=True)
                    link = cols[1].find('a', href=True)
                    
                    if link:
                        import re
                        href = link.get('href', '')
                        event_target_match = re.search(r"'([^']+)'", href)
                        
                        if event_target_match:
                            event_target = event_target_match.group(1)
                            
                            print(f"\n{'='*60}")
                            print(f"TESTING DOWNLOAD OF FIRST FILE")
                            print(f"{'='*60}")
                            print(f"Title: {title}")
                            print(f"Event Target: {event_target}")
                            print(f"\nStep 5: Attempting download...")
                            
                            # Try to download
                            file_info = {'title': title, 'file_type': 'pdf', 'event_target': event_target}
                            content = scraper.download_file(TEST_URL, event_target, file_info, "test.pdf")
                            
                            if content:
                                print(f"\n✓ SUCCESS! Downloaded {len(content)} bytes")
                                
                                # Check content type
                                if content[:4] == b'%PDF':
                                    print("  Content appears to be PDF ✓")
                                elif content[:2] == b'PK':
                                    print("  Content appears to be ZIP/Excel ✓")
                                else:
                                    print(f"  Content starts with: {content[:50]}")
                                    if b'<html' in content[:500].lower():
                                        print("  WARNING: Content appears to be HTML ✗")
                            else:
                                print(f"\n✗ FAILED to download file")
                                print("  Check the warnings/errors above for details")
                        else:
                            print("  Could not extract event target from link")
                    else:
                        print("  No download link found in first row")
                else:
                    print("  First row doesn't have enough columns")
            else:
                print("  No rows found in table")
        else:
            print("  No table found in tab")
    else:
        print("  Tab T3 (النشرات الإحصائية) not found")
    
    print(f"\n{'='*60}")
    print("TEST COMPLETE")
    print(f"{'='*60}\n")

except Exception as e:
    print(f"\n✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
