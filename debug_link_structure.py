"""
Debug script to examine the exact structure of RepeaterForChild links
"""
import os
os.environ['AWS_ACCESS_KEY_ID'] = 'test'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'test'
os.environ['AWS_BUCKET_NAME'] = 'test'

from scraper import KCSBScraper
from bs4 import BeautifulSoup
import re

TEST_URL = "https://www.csb.gov.kw/Pages/Statistics?ID=18&ParentCatID=2"
EVENT_TARGET = "ctl00$MainContent$RPT_Statistic$ctl05$LinkButton3"

print("="*70)
print("EXAMINING REPEATERFORCHILD LINK STRUCTURE")
print("="*70)

scraper = KCSBScraper('test', 'test', 'test')

# Load page
response = scraper.session.get(TEST_URL, timeout=30)
soup = BeautifulSoup(response.content, 'html.parser')

# Prepare form data for first postback (click LinkButton to expand section)
form_data = scraper.get_viewstate_data(soup)
form_data['__EVENTTARGET'] = EVENT_TARGET
form_data['__EVENTARGUMENT'] = ''

form = soup.find('form')
if form:
    for inp in form.find_all('input'):
        name = inp.get('name')
        if name and name not in form_data:
            form_data[name] = inp.get('value', '')

# Click LinkButton to expand section
print("\n1. Clicking LinkButton to expand section...")
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

print(f"   Response size: {len(response.content):,} bytes")

# Parse expanded section
detail_soup = BeautifulSoup(response.content, 'html.parser')

# Find RepeaterForChild links
repeater_links = detail_soup.find_all('a', {'id': lambda x: x and 'RepeaterForChild' in x})

print(f"\n2. Found {len(repeater_links)} RepeaterForChild links\n")

# Examine first 3 links in detail
for idx, link in enumerate(repeater_links[:3], 1):
    print(f"Link #{idx}:")
    print(f"  ID: {link.get('id', 'NO ID')}")
    
    # Find the entire table row this link is in
    tr = link.find_parent('tr')
    if tr:
        print(f"  TABLE ROW structure:")
        tds = tr.find_all('td')
        for td_idx, td in enumerate(tds, 1):
            td_text = td.get_text(strip=True)
            print(f"    TD#{td_idx}: '{td_text[:100]}'")
        print(f"  Full TR HTML: {str(tr)[:500]}...")
    else:
        print(f"  No parent <tr> found")
    
    print()

print("="*70)
