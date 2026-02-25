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
import pandas as pd
from io import BytesIO
import argparse

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
                return {'files': [], 'text_content': None}
            
            files = []
            text_content = None
            
            # Find table with files
            table = tab_content.find('table')
            
            if table:
                rows = table.find('tbody').find_all('tr') if table.find('tbody') else []
                
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) < 2:
                        continue
                    
                    title = cols[0].get_text(strip=True)
                    
                    # Check if this row has a modal trigger (skip these, get files from modal instead)
                    title_cell = cols[0]
                    modal_trigger = title_cell.find('a', {'data-toggle': 'modal'}) or title_cell.find('a', {'onclick': lambda x: x and 'modal' in x.lower()})
                    
                    if modal_trigger:
                        logger.debug(f"    Skipping parent row (opens modal): {title[:50]}")
                        continue
                    
                    # Find download links (only with file icons)
                    pdf_links = cols[1].find_all('a', href=True)
                    
                    for link in pdf_links:
                        img = link.find('img')
                        if not img:
                            continue
                        
                        img_src = img.get('src', '')
                        
                        # Only process actual file download links (with pdf/excel icons)
                        if 'pdf' not in img_src.lower() and 'xls' not in img_src.lower():
                            continue
                        
                        file_type = 'pdf' if 'pdf' in img_src.lower() else 'excel' if 'xls' in img_src.lower() else 'unknown'
                        
                        # Extract the postback event target
                        href = link.get('href', '')
                        
                        # Must contain __doPostBack to be a valid download link
                        if '__doPostBack' not in href:
                            logger.debug(f"    Skipping non-postback link: {title[:30]}")
                            continue
                        
                        event_target_match = re.search(r"'([^']+)'", href)
                        
                        if event_target_match:
                            event_target = event_target_match.group(1)
                            
                            files.append({
                                'title': title,
                                'file_type': file_type,
                                'event_target': event_target
                            })
            
            # Also check for modal popup with additional files
            modal = soup.find('div', {'id': 'Panel_Statistic'})
            if modal:
                logger.info(f"    Found modal popup with additional files")
                modal_table = modal.find('table')
                
                if modal_table:
                    modal_rows = modal_table.find('tbody').find_all('tr') if modal_table.find('tbody') else []
                    
                    for row in modal_rows:
                        cols = row.find_all('td')
                        if len(cols) < 2:
                            continue
                        
                        title = cols[0].get_text(strip=True)
                        
                        # Find download links (only with file icons)
                        pdf_links = cols[1].find_all('a', href=True)
                        
                        for link in pdf_links:
                            img = link.find('img')
                            if not img:
                                continue
                            
                            img_src = img.get('src', '')
                            
                            # Only process actual file download links (with pdf/excel icons)
                            if 'pdf' not in img_src.lower() and 'xls' not in img_src.lower():
                                continue
                            
                            file_type = 'pdf' if 'pdf' in img_src.lower() else 'excel' if 'xls' in img_src.lower() else 'unknown'
                            
                            # Extract the postback event target
                            href = link.get('href', '')
                            
                            # Must contain __doPostBack to be a valid download link
                            if '__doPostBack' not in href:
                                logger.debug(f"    Skipping non-postback modal link: {title[:30]}")
                                continue
                            
                            event_target_match = re.search(r"'([^']+)'", href)
                            
                            if event_target_match:
                                event_target = event_target_match.group(1)
                                
                                files.append({
                                    'title': title,
                                    'file_type': file_type,
                                    'event_target': event_target,
                                    'source': 'modal'  # Mark as coming from modal
                                })
            
            # If no files found, check for text content
            if not files:
                text_content = self.extract_text_content(tab_content, tab_id)
            
            return {'files': files, 'text_content': text_content}
            
        except Exception as e:
            logger.error(f"Error scraping tab {tab_name}: {e}")
            return {'files': [], 'text_content': None}
    
    def extract_text_content(self, tab_content, tab_id):
        """Extract text content from tabs like الموضوع, البيانات الوصفية, التقارير"""
        data = {}
        
        try:
            # For T2 (الموضوع) - extract definition and components
            if tab_id == 'T2':
                list_group = tab_content.find('div', class_='list-group')
                if list_group:
                    sections = []
                    list_items = list_group.find_all('a', class_='list-group-item')
                    
                    current_section = None
                    for item in list_items:
                        if 'active' in item.get('class', []):
                            current_section = item.get_text(strip=True)
                        else:
                            content = item.get_text(strip=True)
                            if content and current_section:
                                sections.append({
                                    'القسم': current_section,
                                    'المحتوى': content
                                })
                    
                    if sections:
                        data['sections'] = sections
            
            # For T4 (البيانات الوصفية) - extract metadata
            elif tab_id == 'T4':
                title_elem = tab_content.find('span', {'id': re.compile(r'.*lbl_calc_title.*')})
                details_elem = tab_content.find('span', {'id': re.compile(r'.*lbl_calc_details.*')})
                
                title = title_elem.get_text(strip=True) if title_elem else ''
                details = details_elem.get_text(strip=True) if details_elem else ''
                
                if title or details:
                    data['metadata'] = [{
                        'العنوان': title,
                        'التفاصيل': details
                    }]
            
            # For T5 (التقارير) - check for any text content
            elif tab_id == 'T5':
                # Sometimes T5 has text content outside the table
                text_divs = tab_content.find_all('div', class_='col-md-12')
                content_found = []
                
                for div in text_divs:
                    text = div.get_text(strip=True)
                    # Filter out empty or very short text
                    if text and len(text) > 50:
                        content_found.append(text)
                
                if content_found:
                    data['reports'] = [{'المحتوى': '\n\n'.join(content_found)}]
            
            return data if data else None
            
        except Exception as e:
            logger.error(f"Error extracting text content: {e}")
            return None
    
    def create_excel_from_data(self, data, tab_name):
        """Convert text data to Excel format"""
        try:
            output = BytesIO()
            
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                if 'sections' in data:
                    df = pd.DataFrame(data['sections'])
                    df.to_excel(writer, sheet_name=tab_name[:30], index=False)
                elif 'metadata' in data:
                    df = pd.DataFrame(data['metadata'])
                    df.to_excel(writer, sheet_name=tab_name[:30], index=False)
                elif 'reports' in data:
                    df = pd.DataFrame(data['reports'])
                    df.to_excel(writer, sheet_name=tab_name[:30], index=False)
                else:
                    # Generic handling
                    for key, value in data.items():
                        if isinstance(value, list):
                            df = pd.DataFrame(value)
                            df.to_excel(writer, sheet_name=key[:30], index=False)
            
            output.seek(0)
            return output.getvalue()
            
        except Exception as e:
            logger.error(f"Error creating Excel file: {e}")
            return None
    
    def download_file(self, category_url, event_target, file_info, save_path):
        """Download a file using ASP.NET two-step postback"""
        max_retries = 3
        
        for attempt in range(1, max_retries + 1):
            try:
                # STEP 1: Get the page to extract ViewState
                response = self.session.get(category_url, timeout=30)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Get ViewState data and all form fields
                form_data = self.get_viewstate_data(soup)
                form_data['__EVENTTARGET'] = event_target
                form_data['__EVENTARGUMENT'] = ''
                
                # Get the form and its action URL
                form = soup.find('form')
                form_action_url = category_url  # Default to page URL
                
                if form:
                    # Get form action if specified
                    form_action = form.get('action')
                    if form_action:
                        form_action_url = urljoin(category_url, form_action)
                    
                    # Get all form fields
                    all_inputs = form.find_all('input')
                    for inp in all_inputs:
                        name = inp.get('name')
                        if not name or name in form_data:
                            continue
                        
                        input_type = inp.get('type', '').lower()
                        
                        if input_type == 'checkbox' or input_type == 'radio':
                            if inp.get('checked'):
                                form_data[name] = inp.get('value', 'on')
                        else:
                            form_data[name] = inp.get('value', '')
                    
                    # Get all select/dropdown fields
                    all_selects = form.find_all('select')
                    for select in all_selects:
                        name = select.get('name')
                        if not name or name in form_data:
                            continue
                        
                        selected = select.find('option', selected=True)
                        if selected:
                            form_data[name] = selected.get('value', '')
                        else:
                            first_option = select.find('option')
                            form_data[name] = first_option.get('value', '') if first_option else ''
                    
                    # Get all textarea fields
                    all_textareas = form.find_all('textarea')
                    for textarea in all_textareas:
                        name = textarea.get('name')
                        if name and name not in form_data:
                            form_data[name] = textarea.get_text(strip=True)
                
                # Prepare headers for ASP.NET postback
                post_headers = {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Referer': category_url,
                    'Origin': 'https://www.csb.gov.kw',
                    'Accept': '*/*',
                    'Accept-Language': 'ar,en;q=0.9',
                    'Cache-Control': 'no-cache'
                }
                
                # STEP 2: Post to open detail/modal view
                logger.debug(f"Step 1: Posting to {event_target}")
                first_response = self.session.post(
                    form_action_url,
                    data=form_data,
                    headers=post_headers,
                    timeout=60
                )
                
                first_response.raise_for_status()
                
                # Check what we got
                content_type = first_response.headers.get('Content-Type', '')
                
                # If we got a file directly (some links might work in one step)
                if ('application/pdf' in content_type or 
                    'application/vnd' in content_type or 
                    'application/octet-stream' in content_type):
                    
                    content = first_response.content
                    if len(content) > 1000 or content[:4] == b'%PDF' or content[:2] == b'PK':
                        logger.debug("Got file in one step")
                        return content
                
                # If we got HTML, look for the download link
                if 'text/html' in content_type:
                    logger.debug("Got HTML, looking for download link...")
                    detail_soup = BeautifulSoup(first_response.content, 'html.parser')
                    
                    # Pattern 1: Look for the modal download link (lnk_down_file)
                    download_link = detail_soup.find('a', {'id': lambda x: x and 'lnk_down_file' in x})
                    
                    # Pattern 2: Look for RepeaterForChild links (expanded section pattern)
                    if not download_link:
                        logger.debug("lnk_down_file not found, checking RepeaterForChild...")
                        
                        # Determine which file type we want (PDF or Excel) based on original event target
                        want_pdf = 'LinkButton3' in event_target  # LinkButton3 = PDF
                        want_excel = 'LinkButton4' in event_target  # LinkButton4 = Excel
                        
                        # Find all RepeaterForChild links
                        repeater_links = detail_soup.find_all('a', {'id': lambda x: x and 'RepeaterForChild' in x})
                        
                        for link in repeater_links:
                            img = link.find('img')
                            if img:
                                img_src = img.get('src', '').lower()
                                
                                # Match file type
                                if want_pdf and 'pdf' in img_src:
                                    download_link = link
                                    logger.debug(f"Found RepeaterForChild PDF link: {link.get('id')}")
                                    break
                                elif want_excel and ('xls' in img_src or 'excel' in img_src):
                                    download_link = link
                                    logger.debug(f"Found RepeaterForChild Excel link: {link.get('id')}")
                                    break
                    
                    if download_link:
                        logger.debug("Found download link, performing second postback...")
                        
                        # Extract event target from href
                        href = download_link.get('href', '')
                        if '__doPostBack' in href:
                            match = re.search(r"__doPostBack\('([^']+)'", href)
                            if match:
                                download_event_target = match.group(1)
                                
                                # STEP 3: Get fresh ViewState from detail view
                                form_data2 = self.get_viewstate_data(detail_soup)
                                form_data2['__EVENTTARGET'] = download_event_target
                                form_data2['__EVENTARGUMENT'] = ''
                                
                                # Get all form fields from detail view
                                form2 = detail_soup.find('form')
                                if form2:
                                    for inp in form2.find_all('input'):
                                        name = inp.get('name')
                                        if name and name not in form_data2:
                                            form_data2[name] = inp.get('value', '')
                                
                                # STEP 4: Post to download link
                                logger.debug(f"Step 2: Posting to {download_event_target}")
                                download_response = self.session.post(
                                    form_action_url,
                                    data=form_data2,
                                    headers=post_headers,
                                    timeout=60,
                                    stream=True
                                )
                                
                                download_response.raise_for_status()
                                
                                # Check if we got the file
                                content_type = download_response.headers.get('Content-Type', '')
                                
                                if ('application/pdf' in content_type or 
                                    'application/vnd' in content_type or 
                                    'application/octet-stream' in content_type or
                                    'application/x-download' in content_type):
                                    
                                    content = download_response.content
                                    
                                    # Verify it's actually a file
                                    if len(content) < 1000:
                                        try:
                                            if b'<html' in content.lower():
                                                logger.warning(f"Small file contains HTML, skipping")
                                                if attempt < max_retries:
                                                    time.sleep(3)
                                                    continue
                                                return None
                                        except:
                                            pass
                                    
                                    return content
                    
                    # If we couldn't find download link, log details
                    logger.warning(f"Could not find download link (lnk_down_file or RepeaterForChild) in response")
                    logger.debug(f"Response size: {len(first_response.content)} bytes")
                    
                    # Debug: count what we did find
                    all_postback_links = detail_soup.find_all('a', href=lambda x: x and '__doPostBack' in x)
                    repeater_links = [l for l in all_postback_links if 'RepeaterForChild' in l.get('id', '')]
                    logger.debug(f"Found {len(all_postback_links)} total postback links, {len(repeater_links)} RepeaterForChild links")
                
                # If we get here, something didn't work
                logger.warning(f"Unexpected content type: {content_type}")
                logger.warning(f"Event target was: {event_target}")
                
                # Retry if not last attempt
                if attempt < max_retries:
                    logger.info(f"  Retry {attempt}/{max_retries}...")
                    time.sleep(3)
                    continue
                
                logger.error(f"Failed after {max_retries} attempts. File: {file_info['title'][:50]}")
                return None
                    
            except Exception as e:
                logger.error(f"Error downloading file (attempt {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    time.sleep(3)
                    continue
                return None
        
        return None
    
    def file_exists_in_s3(self, s3_path):
        """Check if file already exists in S3"""
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_path)
            return True
        except:
            return False
    
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
        
        stats = {'total': 0, 'success': 0, 'failed': 0, 'skipped': 0}
        
        for tab in tabs:
            tab_name = self.sanitize_filename(tab['name'])
            logger.info(f"  Processing tab: {tab_name}")
            
            result = self.scrape_tab_content(category_url, tab['name'], tab['id'])
            files = result['files']
            text_content = result['text_content']
            
            # Process downloadable files
            for idx, file_info in enumerate(files, 1):
                stats['total'] += 1
                
                title = self.sanitize_filename(file_info['title'])
                file_type = file_info['file_type']
                event_target = file_info['event_target']
                is_modal = file_info.get('source') == 'modal'
                
                # Create S3 path
                extension = 'pdf' if file_type == 'pdf' else 'xlsx' if file_type == 'excel' else 'bin'
                filename = f"{title}_{idx}.{extension}"
                s3_path = f"{self.base_s3_path}/{main_category}/{subcategory}/{tab_name}/{filename}"
                
                # Check if file already exists in S3
                if self.file_exists_in_s3(s3_path):
                    modal_prefix = "[Modal] " if is_modal else ""
                    logger.info(f"    Skipping (already exists): {modal_prefix}{title[:50]}...")
                    stats['skipped'] += 1
                    continue
                
                modal_prefix = "[Modal] " if is_modal else ""
                logger.info(f"    Downloading: {modal_prefix}{title[:50]}...")
                
                # Download file
                file_content = self.download_file(category_url, event_target, file_info, s3_path)
                
                if file_content:
                    # Upload to S3
                    if self.upload_to_s3(file_content, s3_path):
                        stats['success'] += 1
                        logger.info(f"    ✓ Successfully uploaded: {filename}")
                    else:
                        stats['failed'] += 1
                        logger.error(f"    ✗ Failed to upload: {filename}")
                else:
                    stats['failed'] += 1
                    logger.error(f"    ✗ Failed to download: {filename}")
                
                # Be respectful - add delay between downloads
                time.sleep(3)
            
            # Process text content if no files found
            if not files and text_content:
                stats['total'] += 1
                filename = f"{tab_name}_content.xlsx"
                s3_path = f"{self.base_s3_path}/{main_category}/{subcategory}/{tab_name}/{filename}"
                
                # Check if text content already exists
                if self.file_exists_in_s3(s3_path):
                    logger.info(f"    Skipping text content (already exists): {tab_name}")
                    stats['skipped'] += 1
                    continue
                
                logger.info(f"    Extracting text content from {tab_name}")
                
                # Convert text content to Excel
                excel_content = self.create_excel_from_data(text_content, tab_name)
                
                if excel_content:
                    if self.upload_to_s3(excel_content, s3_path):
                        stats['success'] += 1
                        logger.info(f"    Uploaded text content as Excel: {filename}")
                    else:
                        stats['failed'] += 1
                else:
                    stats['failed'] += 1
        
        return stats
    
    def run(self, filter_main_category=None):
        """Main execution method"""
        if filter_main_category:
            logger.info(f"Starting KCSB data scraping for category: {filter_main_category}")
        else:
            logger.info("Starting KCSB data scraping for ALL categories...")
        
        # Get all categories
        categories = self.get_categories()
        
        if not categories:
            logger.error("No categories found. Exiting.")
            return
        
        # Filter by main category if specified
        if filter_main_category:
            categories = [c for c in categories if c['main_category'] == filter_main_category]
            logger.info(f"Filtered to {len(categories)} subcategories in '{filter_main_category}'")
            
            if not categories:
                logger.error(f"No subcategories found for main category: {filter_main_category}")
                return
        
        # Statistics
        total_stats = {'total': 0, 'success': 0, 'failed': 0, 'skipped': 0}
        
        # Process each category
        for idx, category in enumerate(categories, 1):
            logger.info(f"\n[{idx}/{len(categories)}] Processing category...")
            
            stats = self.scrape_category(category)
            
            total_stats['total'] += stats['total']
            total_stats['success'] += stats['success']
            total_stats['failed'] += stats['failed']
            total_stats['skipped'] += stats.get('skipped', 0)
            
            # Delay between categories
            time.sleep(3)
        
        # Final summary
        logger.info("\n" + "="*50)
        logger.info("SCRAPING COMPLETE")
        logger.info(f"Total files found: {total_stats['total']}")
        logger.info(f"New files uploaded: {total_stats['success']}")
        logger.info(f"Already existed (skipped): {total_stats['skipped']}")
        logger.info(f"Failed: {total_stats['failed']}")
        logger.info("="*50)


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Scrape KCSB data and upload to S3')
    parser.add_argument(
        '--category',
        type=str,
        help='Filter by main category name (e.g., "الاحصاءات العامة")',
        default=None
    )
    args = parser.parse_args()
    
    # Get AWS credentials from environment variables
    aws_access_key = os.environ.get('AWS_ACCESS_KEY_ID')
    aws_secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    bucket_name = os.environ.get('AWS_BUCKET_NAME')
    
    if not all([aws_access_key, aws_secret_key, bucket_name]):
        logger.error("AWS credentials not found in environment variables")
        exit(1)
    
    # Create scraper and run with optional category filter
    scraper = KCSBScraper(aws_access_key, aws_secret_key, bucket_name)
    scraper.run(filter_main_category=args.category)
