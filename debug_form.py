"""
Deep dive into the form data and compare with what browser sends
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
print("DEEP FORM ANALYSIS")
print("="*70)
print()

scraper = KCSBScraper('test', 'test', 'test')

try:
    # Load page
    response = scraper.session.get(TEST_URL, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, 'html.parser')
    
    print("1. FORM ELEMENT ANALYSIS")
    print("-" * 70)
    
    # Find the form
    form = soup.find('form')
    if form:
        print(f"Form ID: {form.get('id')}")
        print(f"Form Name: {form.get('name')}")
        print(f"Form Action: {form.get('action')}")
        print(f"Form Method: {form.get('method')}")
        print(f"Form Enctype: {form.get('enctype')}")
        print()
    else:
        print("❌ No form found!")
        print()
    
    print("2. ALL HIDDEN FIELDS")
    print("-" * 70)
    
    hidden_inputs = soup.find_all('input', type='hidden')
    print(f"Found {len(hidden_inputs)} hidden fields:\n")
    
    for hidden in hidden_inputs:
        name = hidden.get('name', '')
        value = hidden.get('value', '')
        
        if len(value) > 100:
            value_preview = f"{value[:50]}...{value[-50:]}"
        else:
            value_preview = value
            
        print(f"  {name}: {value_preview}")
    
    print()
    print("3. VIEWSTATE DATA CHECK")
    print("-" * 70)
    
    form_data = scraper.get_viewstate_data(soup)
    
    print(f"__VIEWSTATE: {len(form_data.get('__VIEWSTATE', ''))} chars")
    print(f"__VIEWSTATEGENERATOR: {form_data.get('__VIEWSTATEGENERATOR', 'NOT FOUND')}")
    print(f"__VIEWSTATEENCRYPTED: {form_data.get('__VIEWSTATEENCRYPTED', 'NOT FOUND')}")
    print(f"__EVENTVALIDATION: {len(form_data.get('__EVENTVALIDATION', ''))} chars")
    print()
    
    print("4. CHECKING FOR JAVASCRIPT INIT")
    print("-" * 70)
    
    # Look for any JavaScript that might set values
    scripts = soup.find_all('script')
    for script in scripts:
        script_text = script.get_text()
        if '__doPostBack' in script_text and 'function' in script_text:
            print("Found __doPostBack function definition:")
            # Extract just the function
            lines = script_text.split('\n')
            for i, line in enumerate(lines):
                if 'function __doPostBack' in line:
                    # Print function (next ~10 lines)
                    for j in range(i, min(i+15, len(lines))):
                        print(f"  {lines[j]}")
                    break
            break
    print()
    
    print("5. CHECKING THE LINK BUTTON")
    print("-" * 70)
    
    # Find the specific link button we're trying to click
    link = soup.find('a', href=lambda x: x and 'ctl01$LinkButton3' in x)
    if link:
        print(f"Found link!")
        print(f"  ID: {link.get('id')}")
        print(f"  Href: {link.get('href')}")
        print(f"  OnClick: {link.get('onclick')}")
        
        # Check parent elements
        parent = link.parent
        print(f"  Parent tag: {parent.name if parent else 'None'}")
        if parent:
            print(f"  Parent class: {parent.get('class')}")
    else:
        print("❌ Could not find the specific link!")
    
    print()
    print("6. WHAT FORM_DATA WOULD BE SENT")
    print("-" * 70)
    
    # Build complete form data
    form_data = scraper.get_viewstate_data(soup)
    form_data['__EVENTTARGET'] = 'ctl00$MainContent$RPT_Statistic$ctl01$LinkButton3'
    form_data['__EVENTARGUMENT'] = ''
    
    # Add all hidden fields
    for hidden in hidden_inputs:
        name = hidden.get('name')
        value = hidden.get('value', '')
        if name and name not in form_data:
            form_data[name] = value
    
    print("Complete form_data keys:")
    for key in sorted(form_data.keys()):
        value = form_data[key]
        if len(str(value)) > 50:
            print(f"  {key}: <{len(str(value))} chars>")
        else:
            print(f"  {key}: {value}")
    
    print()
    print("7. COOKIES IN SESSION")
    print("-" * 70)
    
    cookies = scraper.session.cookies.get_dict()
    if cookies:
        print("Active cookies:")
        for name, value in cookies.items():
            if len(value) > 50:
                print(f"  {name}: <{len(value)} chars>")
            else:
                print(f"  {name}: {value}")
    else:
        print("No cookies found")
    
    print()
    print("="*70)
    print("ANALYSIS COMPLETE")
    print("="*70)
    
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
