import requests
from bs4 import BeautifulSoup
import time
import re
from datetime import datetime
import logging
from dateutil.parser import parse
import urllib3
import traceback
import concurrent.futures
import json
import os

# Disable InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def scrape_gradconnection(job_level="graduate-jobs", discipline="computer-science", max_pages=3, save_to_excel=True):
    """
    Scrape job listings from GradConnection with optimized performance
    
    Args:
        job_level: The job level to search for (graduate-jobs, internships)
        discipline: The discipline/field to search for
        max_pages: Maximum number of pages to scrape
        save_to_excel: Whether to save results to Excel
        
    Returns:
        List of job dictionaries
    """
    start_time = time.time()
    logger.info(f"Starting GradConnection scraper for job level: '{job_level}' in discipline: '{discipline}'")
    
    # Set headers to mimic a browser visit
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    # Create a session for persistent cookies
    session = requests.Session()
    
    # Check if GradConnection is accessible
    try:
        test_response = session.get("https://au.gradconnection.com/", headers=headers, verify=False, timeout=10)
        if test_response.status_code != 200:
            logger.error(f"Cannot access GradConnection. Status code: {test_response.status_code}")
            return []
        logger.info("Successfully connected to GradConnection")
    except Exception as e:
        logger.error(f"Error connecting to GradConnection: {e}")
        return []
    
    # Define base URLs
    base_url = f'https://au.gradconnection.com/{job_level}/{discipline}/australia/'
    local_url = 'https://au.gradconnection.com'
    
    # Companies to skip
    skip_companies = ["Readygrad", "GradConnection", "CareerDC", "Premium Graduate Placements"]
    
    # Jobs list
    all_job_links = []
    jobs_list = []
    
    # First, collect all job links from all pages
    logger.info(f"Collecting job links from {max_pages} pages...")
    
    # Use a ThreadPoolExecutor to fetch pages concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        # Create a list to hold the futures
        future_to_page = {}
        
        # Submit a future for each page
        for page_num in range(1, max_pages + 1):
            if page_num == 1:
                url = base_url
            else:
                url = f"{base_url}?page={page_num}"
            
            future = executor.submit(fetch_page, session, url, headers, page_num, max_pages)
            future_to_page[future] = page_num
        
        # Process the results as they complete
        for future in concurrent.futures.as_completed(future_to_page):
            page_num = future_to_page[future]
            try:
                job_links = future.result()
                if job_links:
                    all_job_links.extend(job_links)
                    logger.info(f"Found {len(job_links)} job links on page {page_num}")
                else:
                    logger.warning(f"No job links found on page {page_num}")
            except Exception as e:
                logger.error(f"Error processing page {page_num}: {e}")
    
    logger.info(f"Total job links collected: {len(all_job_links)}")
    
    # Now process the job links concurrently
    if all_job_links:
        logger.info("Processing job details concurrently...")
        
        # Use a ThreadPoolExecutor for processing job details
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            # Create a list to hold the futures
            future_to_job = {}
            
            # Submit a future for each job link
            for i, job_link in enumerate(all_job_links):
                # Limit to no more than 100 jobs to prevent overload
                if i >= 100:
                    logger.info("Reached limit of 100 jobs, stopping.")
                    break
                    
                job_url = local_url + job_link if job_link.startswith('/') else job_link
                future = executor.submit(
                    process_job_details, 
                    session, 
                    job_url, 
                    headers, 
                    skip_companies,
                    job_level,
                    i+1,
                    len(all_job_links[:100])
                )
                future_to_job[future] = i
            
            # Process the results as they complete
            for future in concurrent.futures.as_completed(future_to_job):
                job_idx = future_to_job[future]
                try:
                    job_data = future.result()
                    if job_data:
                        jobs_list.append(job_data)
                except Exception as e:
                    logger.error(f"Error processing job {job_idx + 1}: {e}")
    
    # Save to Excel if requested
    if save_to_excel and jobs_list:
        save_jobs_to_excel(jobs_list, job_level, discipline)
    
    # Log performance metrics
    end_time = time.time()
    duration = end_time - start_time
    logger.info(f"Scraping completed in {duration:.2f} seconds")
    logger.info(f"Found {len(jobs_list)} jobs")
    
    return jobs_list

def fetch_page(session, url, headers, page_num, max_pages):
    """Fetch a single page and extract job links"""
    logger.info(f"Fetching page {page_num}/{max_pages} - URL: {url}")
    
    # Send a GET request with retries
    max_retries = 3
    retry_delay = 2
    response = None
    
    for attempt in range(max_retries):
        try:
            response = session.get(url, headers=headers, verify=False, timeout=15)
            if response.status_code == 200:
                break
            else:
                logger.warning(f"Request failed with status code {response.status_code}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
        except Exception as e:
            logger.warning(f"Request failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2
    
    if not response or response.status_code != 200:
        logger.error(f"Failed to retrieve page {page_num} after retries.")
        return []
            
    # Parse the HTML content
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Find all job listings - try multiple selectors
    job_links = soup.find_all('a', class_='box-header-title')
    
    # If the primary selector doesn't work, try alternatives
    if not job_links:
        logger.warning("Primary selector 'a.box-header-title' didn't find jobs, trying alternatives...")
        
        selectors = [
            '.box a[href*="/graduate-program/"]',
            '.box a[href*="/internship/"]',
            '.job-listing a[href*="/jobs/"]',
            '.job-card a[href*="/jobs/"]',
            'a[href*="/graduate-program/"]',
            'a[href*="/internship/"]'
        ]
        
        for selector in selectors:
            job_links = soup.select(selector)
            if job_links:
                logger.info(f"Found {len(job_links)} job links using selector: {selector}")
                break
        
        # If still no links, try to find any links that might be job listings
        if not job_links:
            logger.warning("No job links found with alternative selectors, searching all links...")
            all_links = soup.find_all('a', href=True)
            job_links = [link for link in all_links if 
                       ('/graduate-program/' in link['href'] or 
                        '/internship/' in link['href'] or 
                        '/jobs/' in link['href']) and
                        'notifyme' not in link['href']]
    
    # Extract just the href attributes
    return [link.get('href') for link in job_links if link.get('href') and "notifyme" not in link.get('href')]

def process_job_details(session, job_url, headers, skip_companies, job_level, job_num, total_jobs):
    """Process a single job details page and extract job data"""
    logger.info(f"Processing job {job_num}/{total_jobs}: {job_url}")
    
    try:
        # Fetch job details page with increased timeout
        response = session.get(job_url, headers=headers, verify=False, timeout=30)
        if response.status_code != 200:
            logger.warning(f"Failed to retrieve job details: {response.status_code}")
            return None

        # Parse the job details page
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Debug - save HTML content
        logger.info(f"HTML Content Length: {len(response.content)}")
        
        # Extract company name
        company_elem = soup.select_one('h1.employer-name, .employer-branding__title h1, .m-employer-logo h1, .company-name h1')
        company = company_elem.text.strip() if company_elem else "Unknown Company"
        
        # Skip certain companies that aren't actual job offers
        if company in skip_companies:
            logger.info(f"Skipping company: {company}")
            return None

        # Extract job title - try multiple selectors
        title_elem = soup.select_one('h1.job-header__title, h1.page-header, .opportunity-header h1, .job-title h1')
        title = title_elem.text.strip() if title_elem else "Unknown Title"
        
        # Extract job type
        job_type = "Graduate Job" if job_level == "graduate-jobs" else "Internship"
        
        # Initialize variables
        disciplines = []
        locations = []
        closing_date = None
        start_date = None
        work_from_home = "Not specified"
        international = "Not specified"
        rotation = "Not specified"
        program_duration = "Not specified"
        number_of_positions = "Not specified"
        salary = "Not specified"
        citizenship_requirements = "Not specified"
        
        # Collect all content sections
        full_description = []
        
        # Add job title and company as header
        full_description.append(f"Position: {title}")
        full_description.append(f"Company: {company}")
        full_description.append("\n")
        
        # Extract all metadata and details
        detail_items = soup.select('.opportunity-elements__item, .job-details__item, .detail-item, .job-meta__item, dt, .detail-label')
        for item in detail_items:
            item_text = item.text.strip()
            item_lower = item_text.lower()
            
            # Extract value from the element
            value_elem = item.select_one('.opportunity-elements__value, .value, .detail-value, .job-meta__value, dd')
            value = value_elem.text.strip() if value_elem else item.find_next('dd').text.strip() if item.find_next('dd') else item_text
            
            # Store the detail
            if value and not any(skip in item_lower for skip in ['share', 'print', 'apply']):
                full_description.append(f"{item_text}: {value}")
            
            # Also store in specific fields
            if 'discipline' in item_lower:
                disciplines = [d.strip() for d in value.split(',')]
            elif 'location' in item_lower:
                locations = [loc.strip() for loc in value.split(',')]
            elif 'closing date' in item_lower:
                try:
                    closing_date = parse(value).strftime('%Y-%m-%d')
                except:
                    closing_date = value
            elif 'start date' in item_lower:
                start_date = value
            elif 'work from home' in item_lower or 'remote' in item_lower:
                work_from_home = value
            elif 'international' in item_lower:
                international = value
            elif 'rotation' in item_lower:
                rotation = value
            elif 'program duration' in item_lower or 'duration' in item_lower:
                program_duration = value
            elif 'number of position' in item_lower or 'positions available' in item_lower:
                number_of_positions = value
            elif 'salary' in item_lower or 'compensation' in item_lower:
                salary = value
            elif 'citizenship' in item_lower or 'eligibility' in item_lower:
                citizenship_requirements = value
        
        full_description.append("\n")
        
        # Extract content sections with their headers
        content_sections = {
            'Overview': ['.job-overview', '.opportunity-overview', '.overview-section'],
            'Job Description': ['.job-description', '.opportunity-description', '.description-content', '#job-description',
                              '[data-test="job-description"]', '.content-block--description', '.job-details__description'],
            'Requirements': ['.requirements', '.job-requirements', '.eligibility-criteria', '#requirements',
                           '[data-test="job-requirements"]', '.content-block--requirements'],
            'Responsibilities': ['.responsibilities', '.job-responsibilities', '.role-responsibilities'],
            'Benefits': ['.benefits', '.perks', '.what-we-offer'],
            'About the Company': ['.employer-description', '.company-description', '.about-company', '#about-company',
                                '.content-block--about', '.employer-profile__description'],
            'Company Culture': ['.culture', '.our-culture', '.work-culture'],
            'How to Apply': ['.application-process', '.how-to-apply', '.apply-section']
        }
        
        # Extract and add each section
        for section_title, selectors in content_sections.items():
            section_content = []
            for selector in selectors:
                elements = soup.select(selector)
                for element in elements:
                    # Remove unwanted elements
                    for unwanted in element.find_all(['script', 'style', 'nav', 'header', 'footer']):
                        unwanted.decompose()
                    
                    # Get text content
                    text = element.get_text(separator='\n', strip=True)
                    if text and len(text) > 20:  # Only include substantial content
                        section_content.append(text)
            
            if section_content:
                full_description.append(f"{section_title}:")
                full_description.append("-" * 40)  # Add separator
                full_description.extend(section_content)
                full_description.append("\n")
        
        # If no structured content found, try to get all main content
        if len(full_description) < 5:  # If we don't have much content
            main_content = soup.select_one('main, .main-content, #main-content, .job-details, .opportunity-details')
            if main_content:
                # Remove navigation elements
                for nav in main_content.find_all(['nav', 'header', 'footer', 'script', 'style']):
                    nav.decompose()
                
                # Get all text content
                content = main_content.get_text(separator='\n', strip=True)
                if content:
                    full_description.append("Job Details:")
                    full_description.append("-" * 40)
                    full_description.append(content)
        
        # Join all content with proper spacing
        complete_description = '\n'.join(full_description)
        
        # Create job data dictionary
        job_data = {
            'title': title,
            'company': company,
            'job_type': job_type,
            'disciplines': ', '.join(disciplines) if disciplines else "Not specified",
            'location': ', '.join(locations) if locations else "Australia",
            'closing_date': closing_date or "Not specified",
            'position_start_date': start_date or "Not specified",
            'work_from_home': work_from_home,
            'international': international,
            'rotation': rotation,
            'program_duration': program_duration,
            'number_of_positions': number_of_positions,
            'salary': salary,
            'citizenship_requirements': citizenship_requirements,
            'description': complete_description,  # All content is now in the description
            'link': job_url,
            'source': 'GradConnection'
        }
        
        # Log successful extraction
        logger.info(f"Successfully extracted job details for: {title} at {company}")
        logger.info(f"Description length: {len(complete_description)}")
        
        return job_data
        
    except Exception as e:
        logger.error(f"Error processing job details: {e}")
        logger.error(traceback.format_exc())
        return None

def save_jobs_to_excel(jobs_list, job_level, discipline):
    """Save jobs to Excel file without database dependency"""
    import pandas as pd
    
    if not jobs_list:
        logger.info("No jobs to save to Excel")
        return
    
    # Create a DataFrame from the jobs list
    df = pd.DataFrame(jobs_list)
    
    # Generate a filename based on the job level and discipline
    filename = f"{discipline}_{job_level}_jobs.xlsx"
    
    # Save to Excel
    df.to_excel(filename, index=False)
    logger.info(f"Saved {len(jobs_list)} jobs to {filename}")

def load_jobs_from_excel(job_level="graduate-jobs", discipline="computer-science"):
    """Load jobs from Excel file"""
    import pandas as pd
    
    filename = f"{discipline}_{job_level}_jobs.xlsx"
    
    try:
        if os.path.exists(filename):
            df = pd.read_excel(filename)
            return df.to_dict('records')
        else:
            logger.info(f"No Excel file found: {filename}")
            return []
    except Exception as e:
        logger.error(f"Error loading jobs from Excel: {e}")
        return []

def get_last_scrape_date(job_level="graduate-jobs", discipline="computer-science"):
    """Get the last scrape date from the Excel file modification time"""
    filename = f"{discipline}_{job_level}_jobs.xlsx"
    
    try:
        if os.path.exists(filename):
            # Get file modification time
            mod_time = os.path.getmtime(filename)
            return datetime.fromtimestamp(mod_time)
        else:
            return None
    except Exception as e:
        logger.error(f"Error getting last scrape date: {e}")
        return None 