import requests
from bs4 import BeautifulSoup
import time
import re
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def scrape_seek(keyword, location, num_pages=3):
    """
    Scrape job listings from Seek.com.au
    
    Args:
        keyword: Search keyword for jobs
        location: Job location
        num_pages: Number of pages to scrape
        
    Returns:
        List of job dictionaries
    """
    logger.info(f"Starting Seek.com.au scraper for keyword: '{keyword}' in location: '{location}'")
    
    # Prepare the keyword for the URL
    keyword_url = keyword.replace(' ', '-')
    location_url = location.replace(' ', '-').lower()
    if location_url == 'all-australia':
        location_url = ''  # Seek uses empty location for "All Australia"
    
    # Set up headers to mimic a browser
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    
    jobs_list = []
    total_jobs = 0
    
    # Loop through pages
    for page in range(1, num_pages + 1):
        # Construct the URL
        if location_url:
            url = f"https://www.seek.com.au/{keyword_url}-jobs/in-{location_url}?page={page}"
        else:
            url = f"https://www.seek.com.au/{keyword_url}-jobs?page={page}"
        
        logger.info(f"Scraping page {page} - URL: {url}")
        
        try:
            # Send request with exponential backoff retry
            max_retries = 3
            retry_delay = 2
            
            for attempt in range(max_retries):
                try:
                    response = requests.get(url, headers=headers, timeout=10)
                    response.raise_for_status()  # Raise exception for non-200 status
                    break
                except (requests.exceptions.RequestException, requests.exceptions.HTTPError) as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"Request failed, retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        logger.error(f"Failed to retrieve page {page} after {max_retries} attempts: {e}")
                        continue
            
            # Parse HTML content
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find all job listings
            job_cards = soup.find_all('article', class_=lambda x: x and '_1wkzzau0' in x)
            
            if not job_cards:
                logger.warning(f"No job listings found using primary selector on page {page}. Trying alternative selectors.")
                # Try another selector if the first one doesn't work
                job_cards = soup.find_all('article')
                if not job_cards:
                    # If still no jobs, try one more method
                    job_cards = soup.select('[data-card-type="JobCard"]')
                    if not job_cards:
                        # If we still can't find jobs, break the loop
                        logger.error("No job cards found with any selector. Check if Seek's HTML structure has changed.")
                        break
            
            # Process each job card
            for i, job_card in enumerate(job_cards):
                try:
                    # Extract job title
                    title_elem = job_card.find('a', attrs={'data-automation': 'jobTitle'}) or job_card.find('h3')
                    title = title_elem.get_text().strip() if title_elem else "Unknown Title"
                    
                    # Extract job link
                    link = "https://www.seek.com.au" + title_elem['href'] if title_elem and 'href' in title_elem.attrs else None
                    
                    # Extract company name
                    company_elem = job_card.find('a', attrs={'data-automation': 'jobCompany'}) or job_card.find('span', class_=lambda x: x and 'company' in x.lower())
                    company = company_elem.get_text().strip() if company_elem else "Unknown Company"
                    
                    # Extract location
                    location_elem = job_card.find(attrs={'data-automation': 'jobLocation'}) or job_card.find('span', string=lambda x: x and ('melbourne' in x.lower() or 'sydney' in x.lower() or 'brisbane' in x.lower() or 'perth' in x.lower() or 'australia' in x.lower()))
                    job_location = location_elem.get_text().strip() if location_elem else "Unknown Location"
                    
                    # Extract job type
                    job_type_elem = job_card.find(attrs={'data-automation': 'jobWorkType'}) or job_card.find('span', string=lambda x: x and ('full time' in x.lower() or 'part time' in x.lower() or 'casual' in x.lower() or 'contract' in x.lower()))
                    job_type = job_type_elem.get_text().strip() if job_type_elem else "Not specified"
                    
                    # Extract listing date
                    date_elem = job_card.find(attrs={'data-automation': 'jobListingDate'}) or job_card.select_one('time') or job_card.find('span', string=lambda x: x and ('day' in x.lower() or 'hour' in x.lower() or 'min' in x.lower()))
                    listing_date = date_elem.get_text().strip() if date_elem else "Unknown Date"
                    
                    # Extract salary if available
                    salary_elem = job_card.find(attrs={'data-automation': 'jobSalary'}) or job_card.find('span', string=lambda x: x and ('$' in x or 'salary' in x.lower()))
                    salary = salary_elem.get_text().strip() if salary_elem else "Not specified"
                    
                    # Calculate estimated closing date (usually 30 days from posting for Seek jobs)
                    closing_date = None
                    try:
                        if 'day' in listing_date.lower():
                            days_ago = int(re.search(r'(\d+)', listing_date).group(1))
                            posting_date = datetime.now().date()
                            closing_date = posting_date.replace(day=posting_date.day + 30 - days_ago)
                        else:
                            # For very recent jobs (hours/mins ago), set 30 days from now
                            closing_date = datetime.now().date().replace(day=datetime.now().date().day + 30)
                    except:
                        closing_date = None
                    
                    # Create job object
                    job = {
                        'Program Title': title,
                        'Company': company,
                        'Link': link,
                        'Job Type': job_type,
                        'Location': job_location,
                        'Closing Date': closing_date,
                        'Listing Date': listing_date,
                        'Salary': salary,
                        'Source': 'Seek',
                        # Add empty fields to match the expected format
                        'Disciplines': "Not specified",
                        'Work from Home': "Not specified",
                        'International': "Not specified"
                    }
                    
                    jobs_list.append(job)
                    total_jobs += 1
                    
                    if i % 5 == 0:
                        logger.info(f"Processed {i} jobs on page {page}")
                
                except Exception as e:
                    logger.error(f"Error processing job: {e}")
                    continue
            
            # Add a delay between page requests to be respectful to the server
            time.sleep(2)
            
        except Exception as e:
            logger.error(f"Error processing page {page}: {e}")
            continue
    
    logger.info(f"Scraping completed. Found {total_jobs} jobs from Seek.")
    return jobs_list 