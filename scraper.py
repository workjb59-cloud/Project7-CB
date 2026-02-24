import requests
from bs4 import BeautifulSoup
import os
import boto3
from botocore.exceptions import NoCredentialsError
import time
import logging
from urllib.parse import urljoin, quote
import re
import ssl
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Custom SSL adapter to handle legacy SSL renegotiation
class SSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context()
        context.load_default_certs()
        context.set_ciphers('DEFAULT@SECLEVEL=1')
        # Allow legacy renegotiation for older servers
        context.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
        kwargs['ssl_context'] = context
        return super().init_poolmanager(*args, **kwargs)

# Disable SSL warnings for legacy connections
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class KCSBScraper:
    def __init__(self, aws_access_key, aws_secret_key, bucket_name):
        self.base_url = "https://www.csb.gov.kw/Pages/"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        # Mount custom SSL adapter for both http and https
        self.session.mount('https://', SSLAdapter())
        self.session.mount('http://', SSLAdapter())
        
        # S3 setup
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key
        )
        self.bucket_name = bucket_name
        self.base_s3_path = "KCSB-data"
        
    def sanitize_filename(self, filename):
        """Remove or replace invalid characters for file names"""
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        filename = filename.strip()
        return filename
    
    def get_categories(self):
        """Extract all main categories and subcategories"""
        url = f"{self.base_url}Statistics.aspx?ID=18&ParentCatID=2"
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            categories = []
            
            # Find all toggle sections (main categories)
            toggle_sections = soup.find_all('div', class_='toggle')
            
            for section in toggle_sections:
                label = section.find('label')
                if not label:
                    continue
                    
                main_category = label.get_text(strip=True)
                toggle_content = section.find('div', class_='toggle-content')
                
                if not toggle_content:
                    continue
                
                # Find all subcategories
                links = toggle_content.find_all('a', href=True)
                
                for link in links:
                    # Skip parent links without IDs
                    if link.get('class') and 'parent' in link.get('class'):
                        continue
                        
                    subcategory_name = link.find('span').get_text(strip=True) if link.find('span') else link.get_text(strip=True)
                    href = link['href']
                    
                    # Extract ID and ParentCatID from href
                    id_match = re.search(r'ID=(\d+)', href)
                    parent_match = re.search(r'ParentCatID=(\d+)', href)
                    
                    if id_match:
                        category_id = id_match.group(1)
                        parent_id = parent_match.group(1) if parent_match else ''
                        
                        categories.append({
                            'main_category': main_category,
                            'subcategory': subcategory_name,
                            'id': category_id,
                            'parent_id': parent_id,
                            'url': urljoin(self.base_url, href.replace('Statistics.aspx', 'Statistics'))
                        })
            
            logger.info(f"Found {len(categories)} subcategories across all main categories")
            return categories
            
        except Exception as e:
            logger.error(f"Error fetching categories: {e}")
            return []
    
    def get_viewstate_data(self, soup):
        """Extract ASP.NET ViewState and other hidden fields"""
        viewstate = soup.find('input', {'name': '__VIEWSTATE'})
        viewstate_gen = soup.find('input', {'name': '__VIEWSTATEGENERATOR'})
        event_validation = soup.find('input', {'name': '__EVENTVALIDATION'})
        
        return {
            '__VIEWSTATE': viewstate['value'] if viewstate else '',
            '__VIEWSTATEGENERATOR': viewstate_gen['value'] if viewstate_gen else '',
            '__EVENTVALIDATION': event_validation['value'] if event_validation else ''
        }
    
    def scrape_tab_content(self, category_url, tab_name, tab_id):
        """Scrape content from a specific tab"""
        try:
            response = self.session.get(category_url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Get the tab content div
            tab_content = soup.find('div', {'id': tab_id})
            
            if not tab_content:
                logger.warning(f"Tab {tab_name} not found")
                return []
            
            files = []
            
            # Find table with files
            table = tab_content.find('table')
            if not table:
                logger.info(f"No table found in tab {tab_name}")
                return []
            
            rows = table.find('tbody').find_all('tr') if table.find('tbody') else []
            
            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 2:
                    continue
                
                title = cols[0].get_text(strip=True)
                
                # Find download links
                pdf_links = cols[1].find_all('a', href=True)
                
                for link in pdf_links:
                    img = link.find('img')
                    if not img:
                        continue
                    
                    img_src = img.get('src', '')
                    file_type = 'pdf' if 'pdf' in img_src.lower() else 'excel' if 'xls' in img_src.lower() else 'unknown'
                    
                    # Extract the postback event target
                    href = link.get('href', '')
                    event_target_match = re.search(r"'([^']+)'", href)
                    
                    if event_target_match:
                        event_target = event_target_match.group(1)
                        
                        files.append({
                            'title': title,
                            'file_type': file_type,
                            'event_target': event_target
                        })
            
            return files
            
        except Exception as e:
            logger.error(f"Error scraping tab {tab_name}: {e}")
            return []
    
    def download_file(self, category_url, event_target, file_info, save_path):
        """Download a file using ASP.NET postback"""
        try:
            # First, get the page to extract ViewState
            response = self.session.get(category_url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Get ViewState data
            form_data = self.get_viewstate_data(soup)
            form_data['__EVENTTARGET'] = event_target
            form_data['__EVENTARGUMENT'] = ''
            
            # Post the form to trigger download
            download_response = self.session.post(
                category_url,
                data=form_data,
                timeout=60,
                stream=True
            )
            
            download_response.raise_for_status()
            
            # Check if we got a file
            content_type = download_response.headers.get('Content-Type', '')
            
            if 'application/pdf' in content_type or 'application/vnd' in content_type or 'octet-stream' in content_type:
                return download_response.content
            else:
                logger.warning(f"Unexpected content type: {content_type}")
                return None
                
        except Exception as e:
            logger.error(f"Error downloading file: {e}")
            return None
    
    def upload_to_s3(self, file_content, s3_path):
        """Upload file to S3"""
        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_path,
                Body=file_content
            )
            logger.info(f"Uploaded to S3: {s3_path}")
            return True
        except NoCredentialsError:
            logger.error("AWS credentials not found")
            return False
        except Exception as e:
            logger.error(f"Error uploading to S3: {e}")
            return False
    
    def scrape_category(self, category_info):
        """Scrape all tabs and files for a category"""
        main_category = self.sanitize_filename(category_info['main_category'])
        subcategory = self.sanitize_filename(category_info['subcategory'])
        category_url = category_info['url']
        
        logger.info(f"Processing: {main_category} -> {subcategory}")
        
        # Define the 4 tabs
        tabs = [
            {'name': 'الموضوع', 'id': 'T2'},
            {'name': 'النشرات الإحصائية', 'id': 'T3'},
            {'name': 'البيانات الوصفية', 'id': 'T4'},
            {'name': 'التقارير', 'id': 'T5'}
        ]
        
        stats = {'total': 0, 'success': 0, 'failed': 0}
        
        for tab in tabs:
            tab_name = self.sanitize_filename(tab['name'])
            logger.info(f"  Processing tab: {tab_name}")
            
            files = self.scrape_tab_content(category_url, tab['name'], tab['id'])
            
            for idx, file_info in enumerate(files, 1):
                stats['total'] += 1
                
                title = self.sanitize_filename(file_info['title'])
                file_type = file_info['file_type']
                event_target = file_info['event_target']
                
                # Create S3 path
                extension = 'pdf' if file_type == 'pdf' else 'xlsx' if file_type == 'excel' else 'bin'
                filename = f"{title}_{idx}.{extension}"
                s3_path = f"{self.base_s3_path}/{main_category}/{subcategory}/{tab_name}/{filename}"
                
                logger.info(f"    Downloading: {title[:50]}...")
                
                # Download file
                file_content = self.download_file(category_url, event_target, file_info, s3_path)
                
                if file_content:
                    # Upload to S3
                    if self.upload_to_s3(file_content, s3_path):
                        stats['success'] += 1
                    else:
                        stats['failed'] += 1
                else:
                    stats['failed'] += 1
                
                # Be respectful - add delay
                time.sleep(2)
        
        return stats
    
    def run(self):
        """Main execution method"""
        logger.info("Starting KCSB data scraping...")
        
        # Get all categories
        categories = self.get_categories()
        
        if not categories:
            logger.error("No categories found. Exiting.")
            return
        
        # Statistics
        total_stats = {'total': 0, 'success': 0, 'failed': 0}
        
        # Process each category
        for idx, category in enumerate(categories, 1):
            logger.info(f"\n[{idx}/{len(categories)}] Processing category...")
            
            stats = self.scrape_category(category)
            
            total_stats['total'] += stats['total']
            total_stats['success'] += stats['success']
            total_stats['failed'] += stats['failed']
            
            # Delay between categories
            time.sleep(3)
        
        # Final summary
        logger.info("\n" + "="*50)
        logger.info("SCRAPING COMPLETE")
        logger.info(f"Total files processed: {total_stats['total']}")
        logger.info(f"Successfully uploaded: {total_stats['success']}")
        logger.info(f"Failed: {total_stats['failed']}")
        logger.info("="*50)


if __name__ == "__main__":
    # Get AWS credentials from environment variables
    aws_access_key = os.environ.get('AWS_ACCESS_KEY_ID')
    aws_secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    bucket_name = os.environ.get('AWS_BUCKET_NAME')
    
    if not all([aws_access_key, aws_secret_key, bucket_name]):
        logger.error("AWS credentials not found in environment variables")
        exit(1)
    
    # Create scraper and run
    scraper = KCSBScraper(aws_access_key, aws_secret_key, bucket_name)
    scraper.run()
