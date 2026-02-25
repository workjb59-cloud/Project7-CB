"""
Quick test script to run scraper on a single category
Useful for testing fixes before running full workflow
"""
import os
import sys
os.environ['AWS_ACCESS_KEY_ID'] = 'test'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'test'
os.environ['AWS_BUCKET_NAME'] = 'test'

# Ensure environment variables are set
if not os.getenv('AWS_ACCESS_KEY_ID'):
    print("⚠️  AWS credentials not set. Please set:")
    print("   set AWS_ACCESS_KEY_ID=your_key")
    print("   set AWS_SECRET_ACCESS_KEY=your_secret")
    print("   set AWS_BUCKET_NAME=your_bucket")
    sys.exit(1)

import argparse
from scraper import KCSBScraper
import logging

# Setup logging to show more details
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def main():
    parser = argparse.ArgumentParser(description='Test scraper on a single category')
    parser.add_argument('--category', type=str, required=True, 
                       help='Main category name to test (in Arabic)')
    parser.add_argument('--verbose', action='store_true',
                       help='Enable debug logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    print("="*70)
    print("KCSB TEST SCRAPER")
    print("="*70)
    print(f"Category: {args.category}")
    print(f"Verbose: {args.verbose}")
    print()
    
    # Available categories for reference
    available_categories = [
        "الاحصاءات العامة",
        "الاحصاءات السكانية",
        "الإحصاءات الاقتصادية",
        "الإحصاءات التجارية والزراعية",
        "الاحصاءات الاجتماعية والخدمات"
    ]
    
    if args.category not in available_categories:
        print(f"⚠️  Warning: Category '{args.category}' not in known categories:")
        for cat in available_categories:
            print(f"   - {cat}")
        print()
    
    try:
        scraper = KCSBScraper(
            aws_access_key=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            bucket_name=os.getenv('AWS_BUCKET_NAME')
        )
        
        print("Starting scrape...")
        scraper.run(filter_main_category=args.category)
        
        print("\n" + "="*70)
        print("✅ TEST COMPLETE")
        print("="*70)
        
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
