"""
Debug script to analyze a specific category page and show all links found
This helps understand why some downloads fail
"""
import os
import sys

os.environ['AWS_ACCESS_KEY_ID'] = 'test'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'test'
os.environ['AWS_BUCKET_NAME'] = 'test'

from scraper import KCSBScraper
from bs4 import BeautifulSoup
import re

# Test with the problematic category
TEST_URL = "https://www.csb.gov.kw/Pages/Statistics?ID=60&ParentCatID=70"
TAB_ID = "T3"  # النشرات الإحصائية

print("="*70)
print("ANALYZING PAGE LINKS")
print("="*70)
print(f"URL: {TEST_URL}")
print(f"Tab: {TAB_ID}\n")

scraper = KCSBScraper('test', 'test', 'test')

try:
    response = scraper.session.get(TEST_URL, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, 'html.parser')
    
    tab_content = soup.find('div', {'id': TAB_ID})
    
    if not tab_content:
        print(f"❌ Tab {TAB_ID} not found!")
        sys.exit(1)
    
    print(f"✓ Found tab {TAB_ID}\n")
    
    # Analyze main table
    print("-"*70)
    print("MAIN TABLE ANALYSIS")
    print("-"*70)
    
    table = tab_content.find('table')
    if table:
        rows = table.find('tbody').find_all('tr') if table.find('tbody') else []
        print(f"Found {len(rows)} rows\n")
        
        for idx, row in enumerate(rows, 1):
            cols = row.find_all('td')
            if len(cols) < 2:
                continue
            
            title = cols[0].get_text(strip=True)
            print(f"\nRow {idx}: {title[:60]}")
            
            # Check for modal trigger
            title_cell = cols[0]
            modal_trigger = title_cell.find('a', {'data-toggle': 'modal'}) or \
                          title_cell.find('a', {'onclick': lambda x: x and 'modal' in x.lower()})
            
            if modal_trigger:
                print("  ⚠️  MODAL TRIGGER - Will be skipped (files in modal)")
                continue
            
            # Find links in download column
            links = cols[1].find_all('a', href=True)
            
            if not links:
                print("  ❌ No links found")
                continue
            
            for link_idx, link in enumerate(links, 1):
                href = link.get('href', '')
                img = link.find('img')
                img_src = img.get('src', '') if img else ''
                
                print(f"  Link {link_idx}:")
                print(f"    - Has image: {'✓' if img else '✗'}")
                print(f"    - Image src: {img_src}")
                print(f"    - Has __doPostBack: {'✓' if '__doPostBack' in href else '✗'}")
                
                if img and ('pdf' in img_src.lower() or 'xls' in img_src.lower()):
                    if '__doPostBack' in href:
                        event_match = re.search(r"'([^']+)'", href)
                        if event_match:
                            print(f"    - Event target: {event_match.group(1)}")
                            print(f"    ✅ VALID DOWNLOAD LINK")
                        else:
                            print(f"    ❌ Could not extract event target")
                    else:
                        print(f"    ❌ Not a postback link")
                else:
                    print(f"    ⚠️  Not a file download icon")
    else:
        print("❌ No table found in main tab")
    
    # Analyze modal
    print("\n" + "-"*70)
    print("MODAL POPUP ANALYSIS")
    print("-"*70)
    
    modal = soup.find('div', {'id': 'Panel_Statistic'})
    
    if modal:
        print("✓ Found modal popup\n")
        
        modal_table = modal.find('table')
        if modal_table:
            modal_rows = modal_table.find('tbody').find_all('tr') if modal_table.find('tbody') else []
            print(f"Found {len(modal_rows)} rows in modal\n")
            
            for idx, row in enumerate(modal_rows, 1):
                cols = row.find_all('td')
                if len(cols) < 2:
                    continue
                
                title = cols[0].get_text(strip=True)
                print(f"\nModal Row {idx}: {title[:60]}")
                
                links = cols[1].find_all('a', href=True)
                
                if not links:
                    print("  ❌ No links found")
                    continue
                
                for link_idx, link in enumerate(links, 1):
                    href = link.get('href', '')
                    img = link.find('img')
                    img_src = img.get('src', '') if img else ''
                    
                    print(f"  Link {link_idx}:")
                    print(f"    - Has image: {'✓' if img else '✗'}")
                    print(f"    - Image src: {img_src}")
                    print(f"    - Has __doPostBack: {'✓' if '__doPostBack' in href else '✗'}")
                    
                    if img and ('pdf' in img_src.lower() or 'xls' in img_src.lower()):
                        if '__doPostBack' in href:
                            event_match = re.search(r"'([^']+)'", href)
                            if event_match:
                                print(f"    - Event target: {event_match.group(1)}")
                                print(f"    ✅ VALID DOWNLOAD LINK")
                            else:
                                print(f"    ❌ Could not extract event target")
                        else:
                            print(f"    ❌ Not a postback link")
                    else:
                        print(f"    ⚠️  Not a file download icon")
        else:
            print("❌ No table found in modal")
    else:
        print("❌ No modal popup found")
    
    print("\n" + "="*70)
    print("ANALYSIS COMPLETE")
    print("="*70)

except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
