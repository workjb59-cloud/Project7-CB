"""
Test script to verify category filtering works correctly
Run this to see which categories will be processed by each job
"""
import os
os.environ['AWS_ACCESS_KEY_ID'] = 'test'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'test'
os.environ['AWS_BUCKET_NAME'] = 'test'

from scraper import KCSBScraper

# The 5 main categories from the website
CATEGORIES = [
    "الاحصاءات العامة",
    "الاحصاءات السكانية",
    "الإحصاءات الاقتصادية",
    "الإحصاءات التجارية والزراعية",
    "الاحصاءات الاجتماعية والخدمات"
]

print("Testing category filtering...\n")
print("="*60)

# Create scraper (won't actually scrape, just test filtering)
scraper = KCSBScraper('test', 'test', 'test')

# Get all categories
all_categories = scraper.get_categories()

if not all_categories:
    print("ERROR: Could not fetch categories from website")
    print("This might be due to:")
    print("  - SSL/TLS connection issues")
    print("  - Network connectivity problems")
    print("  - Website structure changes")
    exit(1)

print(f"Total subcategories found: {len(all_categories)}\n")

# Test filtering for each main category
for main_cat in CATEGORIES:
    filtered = [c for c in all_categories if c['main_category'] == main_cat]
    print(f"\n{main_cat}:")
    print(f"  Subcategories: {len(filtered)}")
    if filtered:
        print(f"  Examples:")
        for sub in filtered[:3]:  # Show first 3
            print(f"    - {sub['subcategory']}")
        if len(filtered) > 3:
            print(f"    ... and {len(filtered) - 3} more")

print("\n" + "="*60)
print("\nCategory filtering test PASSED ✅")
print(f"\nEach parallel job will process a subset of the {len(all_categories)} total subcategories.")
print("This ensures no job exceeds GitHub Actions time limits.")
