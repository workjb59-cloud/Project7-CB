"""
Test script to verify multiple files are downloaded from expanded sections (RepeaterForChild pattern)
"""
import os
from dotenv import load_dotenv
from scraper import KCSBScraper

# Load environment variables
load_dotenv()

def test_expanded_section():
    """Test downloading multiple files from an expanded section"""
    
    # Initialize scraper
    scraper = KCSBScraper(
        aws_access_key=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        bucket_name=os.getenv('AWS_S3_BUCKET')
    )
    
    print("Fetching categories to find ID=18...")
    categories = scraper.get_categories()
    
    # Find a category with ID=18 (known to have expanded sections)
    test_category = None
    for cat in categories:
        if cat['id'] == '18':
            test_category = cat
            break
    
    if not test_category:
        print("ERROR: Could not find category with ID=18")
        print("\nAvailable categories:")
        for cat in categories[:5]:  # Show first 5
            print(f"  ID={cat['id']}: {cat['main_category']} > {cat['subcategory']}")
        return
    
    print(f"\nTesting with: {test_category['main_category']} > {test_category['subcategory']}")
    print("=" * 70)
    
    # Test scraping just this one category
    stats = scraper.scrape_category(test_category)
    
    print("=" * 70)
    print(f"\nTest Results:")
    print(f"  Total files: {stats['total']}")
    print(f"  Successful: {stats['success']}")
    print(f"  Failed: {stats['failed']}")
    print(f"  Skipped: {stats.get('skipped', 0)}")
    print("\nCheck logs above to verify:")
    print("1. 'Found N files in expanded section' message appears")
    print("2. 'Downloading 1/N from expanded section...' messages for each file")
    print("3. '✓ Uploaded child file N/N' messages for each successful upload")
    print("4. Multiple files uploaded to S3 from same expanded section")

if __name__ == "__main__":
    test_expanded_section()
