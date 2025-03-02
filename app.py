from flask import Flask, render_template, request, jsonify, Response, stream_with_context
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
import json
from datetime import datetime, timedelta
from dateutil.parser import parse
import urllib3
import os
import traceback
import random

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

class CustomError(Exception):
    pass

def grad_connection_scrape(job_level, discipline, location="australia"):
    """Scrape job listings from GradConnection"""
    # Set headers to mimic a browser visit
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }

    base_url = f'https://au.gradconnection.com/{job_level}/{discipline}/{location}/'
    local_url = 'https://au.gradconnection.com'
    page_num = 1
    jobs_list = []
    max_pages = 10  # Increased limit (will continue until no more jobs or pages found)
    total_jobs_found = 0
    current_progress = 0
    last_page_count = -1  # Track the number of jobs on the last page to detect the end

    while page_num <= max_pages:
        # Construct the URL for the current page
        if page_num == 1:
            url = f"{base_url}"
        else:
            url = f"{base_url}?page={page_num}"

        # Send a GET request
        try:
            yield json.dumps({"progress": current_progress, "status": f"Connecting to GradConnection page {page_num}..."})
            response = requests.get(url, headers=headers, verify=False, timeout=15)
            
            # Break the loop if the request failed
            if response.status_code != 200:
                print(f"Failed to retrieve page {page_num}. Status code: {response.status_code}")
                yield json.dumps({"warning": f"Failed to retrieve GradConnection page {page_num}. Status code: {response.status_code}"})
                break
            
            # Parse the HTML content
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find all job listings - try different selectors as the site might have changed
            job_listings = soup.find_all('a', class_='box-header-title')
            
            # If no jobs found with the primary selector, try alternative selectors
            if not job_listings:
                # Try other potential selectors
                job_listings = soup.find_all('a', class_='job-title')
                if not job_listings:
                    job_listings = soup.select('.job-listing a[href*="/job/"]')
                if not job_listings:
                    job_listings = soup.select('article a[href*="/job/"]')
                if not job_listings:
                    job_listings = soup.select('a[href*="/job/"]')
            
            if not job_listings:
                print(f"No job listings found on page {page_num} using any selector.")
                yield json.dumps({"warning": f"No job listings found on GradConnection page {page_num}."})
                break
            
            # Check if we've reached the last page (no new jobs)
            if len(job_listings) == 0 or (last_page_count == len(job_listings) and page_num > 1):
                print(f"No more job listings found after page {page_num-1}.")
                yield json.dumps({"warning": f"No more job listings found after GradConnection page {page_num-1}."})
                break
            
            last_page_count = len(job_listings)
            total_jobs_found += len(job_listings)
            yield json.dumps({"progress": current_progress, "status": f"Found {len(job_listings)} jobs on GradConnection page {page_num}"})
            
            # Calculate total expected steps for progress bar
            total_steps = total_jobs_found * 2  # Each job needs 2 requests (listing page and detail page)
            
            # Extract details for each job
            job_index = 0
            for job in job_listings:
                job_index += 1
                current_progress = ((page_num - 1) * len(job_listings) + job_index) / (total_jobs_found * 1.5) * 50  # GradConnection takes 50% of progress
                yield json.dumps({"progress": current_progress, "status": f"Scraping GradConnection page {page_num}, job {job_index}/{len(job_listings)}"})
                
                # Get the job URL - handle different element structures
                job_link = None
                if job.has_attr('href'):
                    job_link = str(job.get('href'))
                
                if not job_link:
                    continue
                
                if not "notifyme" in job_link:
                    # Ensure the URL is absolute
                    if job_link.startswith('/'):
                        current_url = local_url + job_link
                    elif job_link.startswith('http'):
                        current_url = job_link
                    else:
                        current_url = local_url + '/' + job_link
                    
                    try:
                        job_response = requests.get(current_url, headers=headers, verify=False, timeout=15)
                        if job_response.status_code != 200:
                            print(f"Failed to retrieve job details. Status code: {job_response.status_code}")
                            continue
                            
                        job_soup = BeautifulSoup(job_response.content, 'html.parser')

                        # Extract job details
                        job_type = None
                        disciplines = None
                        job_location = None
                        international = None
                        closing_date = None
                        position_start_date = None
                        
                        # Try to find job details with different selectors
                        job_detail = job_soup.find_all('li', class_='box-content-catagories catagories-list')
                        if not job_detail:
                            job_detail = job_soup.select('.job-details li')
                        
                        if job_detail:
                            for detail in job_detail:
                                strong_tag = detail.find('strong', class_='box-content-catagories-bold')
                                if not strong_tag:
                                    strong_tag = detail.find('strong')
                                
                                if strong_tag:
                                    strong_text = strong_tag.get_text().strip()
                                    detail_text = detail.get_text().strip()
                                    
                                    if "Job type" in strong_text:
                                        job_type = detail_text.replace(strong_text, "").strip()
                                    elif "Disciplines" in strong_text:
                                        disciplines = detail_text.replace(strong_text, "").strip()
                                    elif "Locations" in strong_text:
                                        # Extract the full location text
                                        location_text = detail_text.replace(strong_text, "").strip()
                                        # Handle "show more" in locations
                                        if "show more" in location_text:
                                            # Extract all cities by removing the "show more" text
                                            job_location = location_text.replace("...show more", "").strip()
                                        else:
                                            job_location = location_text
                                    elif "ACCEPTS INTERNATIONAL" in strong_text:
                                        international = "Yes"
                                    elif "Closing Date" in strong_text:
                                        closing_date_text = detail_text.replace(strong_text, "").strip()
                                        try:
                                            closing_date = parse(closing_date_text)
                                            closing_date = closing_date.strftime("%Y-%m-%d")
                                        except:
                                            closing_date = closing_date_text
                                    elif "Position Start Date" in strong_text:
                                        position_start_date = detail_text.replace(strong_text, "").strip()
                        
                        # Try different selectors for company name and job title
                        company_name_elem = job_soup.find('h1', class_='employers-panel-title')
                        if not company_name_elem:
                            company_name_elem = job_soup.select_one('.company-name')
                        
                        program_name_elem = job_soup.find('h1', class_='employers-profile-h1')
                        if not program_name_elem:
                            program_name_elem = job_soup.select_one('.job-title')
                        
                        # If we still don't have a job title, try to extract from the URL or page title
                        if not program_name_elem:
                            page_title = job_soup.find('title')
                            if page_title:
                                program_name = page_title.get_text().split(' | ')[0].strip()
                            else:
                                program_name = job_link.split('/')[-1].replace('-', ' ').title()
                        else:
                            program_name = program_name_elem.get_text().strip()
                        
                        # If we still don't have a company name, extract from the page or URL
                        if not company_name_elem:
                            company_meta = job_soup.find('meta', property='og:site_name')
                            if company_meta:
                                company_name = company_meta.get('content', 'Unknown Company')
                            else:
                                company_name = job_link.split('/')[3].replace('-', ' ').title()
                        else:
                            company_name = company_name_elem.get_text().strip()
                        
                        # Skip certain companies
                        if company_name.lower() not in ["readygrad", "gradconnection", "careerdc", "premium graduate placements"]:
                            jobs_list.append({
                                'title': program_name,
                                'company': company_name,
                                'link': current_url,
                                'job_type': job_type,
                                'disciplines': disciplines,
                                'location': job_location,
                                'international': international,
                                'position_start_date': position_start_date,
                                'closing_date': closing_date,
                                'source': 'GradConnection'
                            })
                    except Exception as e:
                        print(f"Error processing job: {str(e)}")
                        traceback.print_exc()
                    
                    # Add a small delay to be respectful
                    time.sleep(0.5)
        except Exception as e:
            print(f"Error scraping page {page_num}: {str(e)}")
            traceback.print_exc()
            yield json.dumps({"error": f"Error scraping GradConnection page {page_num}: {str(e)}"})
        
        # Check if we've reached the pagination limit or the end of the job listings
        pagination = soup.select('.pagination a')
        max_page_found = False
        for page_link in pagination:
            try:
                page_number = int(page_link.text.strip())
                if page_number > max_pages:
                    max_pages = page_number
                    max_page_found = True
            except ValueError:
                pass
        
        # If no higher page number is found, we might be at the last page
        if not max_page_found and page_num >= max_pages:
            print(f"Reached the last available page: {page_num}")
            yield json.dumps({"warning": f"Reached the last available GradConnection page: {page_num}"})
            break
            
        # Increment page number and add a delay
        page_num += 1
        time.sleep(1)

    yield json.dumps({"progress": 50, "status": "Completed GradConnection scraping", "results": jobs_list})
    return jobs_list

def seek_scrape(job_level, discipline, location="All-Australia"):
    """Scrape job listings from Seek"""
    # Format job level for Seek URL
    if job_level == "graduate-jobs":
        seek_keyword = "graduate"
    elif job_level == "internships":
        seek_keyword = "internship"
    else:
        seek_keyword = job_level
    
    # Set headers to mimic a browser visit
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    # Initialize list to store job data
    jobs_list = []
    
    # Test different URL formats as Seek might have changed their URL structure
    url_formats = [
        f'https://www.seek.com.au/{seek_keyword}-jobs/in-{location}?classification={discipline}',
        f'https://www.seek.com.au/{seek_keyword}-jobs/{location.lower()}?classification={discipline}',
        f'https://www.seek.com.au/jobs?keywords={seek_keyword}&where={location}&classification={discipline}'
    ]
    
    local_url = 'https://www.seek.com.au'
    page_num = 1
    max_pages = 20  # Increased initial limit (will adjust based on pagination)
    total_jobs_found = 0
    url_index = 0
    base_url = url_formats[url_index]
    last_page_count = -1  # Track the number of jobs on the last page to detect the end
    
    while page_num <= max_pages:
        # Try the next URL format if we've already tried this one
        if page_num == 1 and url_index > 0:
            base_url = url_formats[url_index]
        
        # Construct the URL for the current page
        if page_num == 1:
            url = f"{base_url}"
        else:
            if '?' in base_url:
                url = f"{base_url}&page={page_num}"
            else:
                url = f"{base_url}?page={page_num}"
        
        try:
            # Send a GET request
            yield json.dumps({"progress": 50 + (url_index * 10), "status": f"Connecting to Seek (attempt {url_index + 1})..."})
            response = requests.get(url, headers=headers, timeout=15)
            
            # If the request failed, try the next URL format
            if response.status_code != 200:
                print(f"Failed to retrieve page with URL {url}. Status code: {response.status_code}")
                url_index += 1
                if url_index < len(url_formats):
                    continue
                else:
                    yield json.dumps({"warning": f"Failed to retrieve Seek listings with any URL format. Status code: {response.status_code}"})
                    break
            
            # Parse the HTML content
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find all job listings - try different selectors
            job_listings = soup.find_all('article')
            
            # If no jobs found with the primary selector, try alternative selectors
            if not job_listings:
                job_listings = soup.select('div[data-automation="normalJob"]')
            if not job_listings:
                job_listings = soup.select('.job-card')
            if not job_listings:
                job_listings = soup.select('a[data-automation="jobTitle"]')
                # Convert these to a list of parent elements if found
                if job_listings:
                    job_listings = [link.find_parent('div', class_=lambda x: x and 'job' in x.lower()) for link in job_listings]
            
            # Check if we've reached the last page (no new jobs or same jobs as previous page)
            if len(job_listings) == 0 or (last_page_count == len(job_listings) and page_num > 1):
                print(f"No more job listings found after page {page_num-1}.")
                yield json.dumps({"warning": f"No more job listings found after Seek page {page_num-1}."})
                break
            
            last_page_count = len(job_listings)
            
            # Break the loop if no jobs found
            if not job_listings:
                print(f"No job listings found on page {page_num} using any selector. URL: {url}")
                url_index += 1
                if url_index < len(url_formats):
                    page_num = 1  # Reset page number for new URL format
                    continue
                else:
                    yield json.dumps({"warning": f"No job listings found on Seek page {page_num} using any selector."})
                    break
            
            total_jobs_found += len(job_listings)
            yield json.dumps({"progress": 50 + (page_num * 5), "status": f"Found {len(job_listings)} jobs on Seek page {page_num}"})
            
            # Extract details for each job
            job_index = 0
            for job in job_listings:
                job_index += 1
                current_progress = 50 + ((page_num - 1) * len(job_listings) + job_index) / (total_jobs_found * 1.5) * 50  # Seek takes 50% of progress
                yield json.dumps({"progress": current_progress, "status": f"Scraping Seek page {page_num}, job {job_index}/{len(job_listings)}"})
                
                try:
                    # Try different ways to get the job title
                    title_elem = job.find('a', {'data-automation': 'jobTitle'})
                    if not title_elem:
                        title_elem = job.find('a', class_=lambda x: x and 'title' in x.lower())
                    if not title_elem:
                        title_elem = job.select_one('h3, h2, h1')
                    
                    title = title_elem.get_text().strip() if title_elem else "Untitled Position"
                    
                    # Try different ways to get the job URL
                    url_elem = title_elem if title_elem and title_elem.name == 'a' else job.find('a')
                    if url_elem and url_elem.has_attr('href'):
                        url_extra = url_elem['href']
                        # Make sure we have an absolute URL
                        if url_extra.startswith('/'):
                            url_new = local_url + url_extra
                        elif url_extra.startswith('http'):
                            url_new = url_extra
                        else:
                            url_new = local_url + '/' + url_extra
                    else:
                        # Try to find any link in the job card
                        links = job.find_all('a')
                        if links:
                            url_extra = links[0]['href']
                            url_new = local_url + url_extra if url_extra.startswith('/') else url_extra
                        else:
                            # If we can't find a link, skip this job
                            continue
                    
                    # Try different ways to get the company name
                    company = job.find('a', {'data-automation': 'jobCompany'}) or job.find('a', {'data-type': 'company'})
                    if not company:
                        company = job.select_one('.company-name, .job-company, [data-automation="jobCompany"]')
                    
                    company_name = company.get_text().strip() if company else "Not specified"
                    
                    # Skip certain companies
                    if company_name.lower() not in ["readygrad", "gradconnection"]:
                        # Try different ways to get the location
                        location_elem = job.find('span', {'data-automation': 'jobLocation'})
                        if not location_elem:
                            location_elem = job.select_one('.location, .job-location, [data-automation="jobLocation"]')
                        location_text = location_elem.get_text().strip() if location_elem else None
                        
                        # Try different ways to get the date posted
                        date_elem = job.find('span', {'data-automation': 'jobListingDate'})
                        if not date_elem:
                            date_elem = job.select_one('.date, .listing-date, [data-automation="jobListingDate"]')
                        date_text = date_elem.get_text().strip() if date_elem else None
                        
                        # Try different ways to get the job type
                        job_type_elem = job.find('span', {'data-automation': 'jobWorkType'})
                        if not job_type_elem:
                            job_type_elem = job.select_one('.work-type, .job-type, [data-automation="jobWorkType"]')
                        job_type = job_type_elem.get_text().strip() if job_type_elem else None
                        
                        jobs_list.append({
                            'title': title,
                            'company': company_name,
                            'link': url_new,
                            'location': location_text,
                            'date_posted': date_text,
                            'job_type': job_type,
                            'source': 'Seek'
                        })
                except Exception as e:
                    print(f"Error processing Seek job: {str(e)}")
                    traceback.print_exc()
        except Exception as e:
            print(f"Error scraping Seek page {page_num}: {str(e)}")
            traceback.print_exc()
            yield json.dumps({"error": f"Error scraping Seek page {page_num}: {str(e)}"})
        
        # Check for pagination to see if there are more pages
        pagination = soup.select('a[data-automation="page-link"], .pagination a, a.page-number')
        max_page_found = False
        for page_link in pagination:
            try:
                page_number = int(''.join(filter(str.isdigit, page_link.text.strip())))
                if page_number > max_pages:
                    max_pages = page_number
                    max_page_found = True
            except ValueError:
                pass
        
        # If no higher page number is found and we're at the current max, we might be at the last page
        if not max_page_found and page_num >= max_pages:
            print(f"Reached the last available page: {page_num}")
            yield json.dumps({"warning": f"Reached the last available Seek page: {page_num}"})
            break
        
        # Increment page number and add a delay
        page_num += 1
        time.sleep(1)
    
    yield json.dumps({"progress": 100, "status": "Completed Seek scraping", "results": jobs_list})
    return jobs_list

def prosple_scrape(job_level, discipline, location="australia"):
    """Scrape job listings from Prosple with enhanced browser emulation"""
    # Set browser-like headers with more complete parameters
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
        'Priority': 'high'
    }
    
    # Extensive list of modern user agents
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_1_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (iPad; CPU OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/120.0.6099.101 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 OPR/106.0.0.0'
    ]
    
    # Add more realistic referrers
    referrers = [
        'https://www.google.com/search?q=graduate+jobs+australia+2024',
        'https://www.bing.com/search?q=internships+australia+tech+companies',
        'https://au.indeed.com/jobs?q=graduate&l=Australia',
        'https://www.seek.com.au/graduate-jobs',
        'https://www.linkedin.com/jobs/search/?keywords=graduate&location=Australia',
        'https://www.glassdoor.com.au/Job/australia-graduate-jobs-SRCH_IL.0,9_IN16_KO10,18.htm',
        'https://gradaustralia.com.au/graduate-jobs',
        'https://www.prospects.ac.uk/jobs-and-work-experience/job-sectors/business-consulting-and-management/graduate-jobs-in-australia'
    ]
    
    # Format job level for Prosple URL
    if job_level == "graduate-jobs":
        prosple_job_level = "graduate"
    elif job_level == "internships":
        prosple_job_level = "internship"
    else:
        prosple_job_level = job_level
    
    # Format discipline for Prosple URL
    prosple_discipline_map = {
        'computer-science': 'computer-science-information-technology',
        'data-science-and-analytics': 'data-science-analytics',
        'engineering': 'engineering',
        'finance': 'finance-accounting-economics',
        'mathematics': 'mathematics-statistics',
    }
    prosple_discipline = prosple_discipline_map.get(discipline, 'all-disciplines')
    
    # Format location for Prosple
    if location.lower() == 'australia':
        prosple_location = 'australia'
    else:
        # Try to map the location to what Prosple expects
        prosple_location = location.replace(' ', '-').lower()
    
    # Try different URL patterns
    url_formats = [
        f'https://au.prosple.com/jobs/{prosple_job_level}/{prosple_discipline}/{prosple_location}',
        f'https://au.prosple.com/jobs/{prosple_job_level}/{prosple_discipline}',
        f'https://au.prosple.com/search-jobs?opportunity_types={prosple_job_level}&disciplines={prosple_discipline}',
        f'https://au.prosple.com/jobs/{prosple_job_level}-jobs/{prosple_discipline}/{prosple_location}',
        f'https://au.prosple.com/jobs'
    ]
    
    # Add URLs for employer browsing
    employer_urls = [
        'https://au.prosple.com/employers',
        'https://au.prosple.com/employers/popular',
        'https://au.prosple.com/employers/featured'
    ]
    
    local_url = 'https://au.prosple.com'
    page_num = 1
    jobs_list = []
    max_pages = 5  # Limit pages to avoid blocking
    total_jobs_found = 0
    current_progress = 0
    last_page_count = -1
    url_index = 0
    
    # Create a session with request customization
    session = requests.Session()
    
    # Configure the session with additional parameters
    session.verify = True  # Enable SSL verification
    session.timeout = 30   # Set timeout
    
    # Set default cookies that a typical browser would have
    cookies = {
        'cookieconsent_status': 'allow',
        'session_visited': 'true',
        'timezone': 'Australia/Sydney',  # Set appropriate timezone
        'visitor_id': f'{int(time.time())}-{random.randint(10000,99999)}'
    }
    
    # Add cookies to session
    session.cookies.update(cookies)
    
    # Proxy configuration (optional - uncomment if you want to use proxies)
    # proxies = {
    #    'http': 'http://yourproxy:port',
    #    'https': 'https://yourproxy:port',
    # }
    # session.proxies.update(proxies)
    
    # Initialize with multiple preparatory requests to establish browser-like behavior
    try:
        # Add randomized delay and jitter to appear more human-like
        time.sleep(1 + random.random() * 2)
        
        # First, visit the main site to get cookies
        initial_headers = headers.copy()
        initial_headers['User-Agent'] = random.choice(user_agents)
        
        # Mimic a user typing the URL directly (no referrer)
        main_url = 'https://au.prosple.com/'
        session.get(main_url, headers=initial_headers, timeout=20)
        
        # Simulate navigation through the site
        time.sleep(2 + random.random() * 3)  # Human-like delay
        
        # Visit the about page as a typical user might do
        about_headers = initial_headers.copy()
        about_headers['Referer'] = main_url
        session.get('https://au.prosple.com/about', headers=about_headers, timeout=20)
        
        # Visit the employers page
        time.sleep(1.5 + random.random() * 2)  # Variable delay
        employer_headers = about_headers.copy()
        employer_headers['Referer'] = 'https://au.prosple.com/about'
        session.get('https://au.prosple.com/employers', headers=employer_headers, timeout=20)
        
        # Add other common pages a real user might visit
        for page in ['help', 'contact', 'industries']:
            if random.random() > 0.5:  # Don't always visit every page (more realistic)
                time.sleep(1 + random.random() * 2)
                page_headers = headers.copy()
                page_headers['User-Agent'] = random.choice(user_agents)
                page_headers['Referer'] = f'https://au.prosple.com/{random.choice(["about", "employers", ""])}'
                session.get(f'https://au.prosple.com/{page}', headers=page_headers, timeout=20)
        
    except Exception as e:
        print(f"Error initializing session: {str(e)}")
        yield json.dumps({"warning": f"Error initializing session: {str(e)}"})
    
    # Mode for direct employer browsing
    employer_mode = False
    employer_index = 0
    employer_list = []
    
    # Main scraping loop
    while page_num <= max_pages and (url_index < len(url_formats) or employer_mode):
        # Handle employer mode scraping
        if employer_mode:
            if employer_index >= len(employer_list):
                if employer_list:
                    # We've processed all employers, try other methods
                    employer_mode = False
                    continue
                else:
                    # Try to fetch employers first
                    try:
                        for employer_base_url in employer_urls:
                            yield json.dumps({"progress": 40, "status": f"Browsing employers on Prosple..."})
                            
                            # Use different browser profiles for each request
                            emp_headers = headers.copy()
                            emp_headers['User-Agent'] = random.choice(user_agents)
                            emp_headers['Referer'] = random.choice(referrers)
                            
                            # Realistic human delay
                            time.sleep(2 + random.random() * 3)
                            
                            emp_response = session.get(employer_base_url, headers=emp_headers, timeout=20)
                            
                            if emp_response.status_code == 200:
                                emp_soup = BeautifulSoup(emp_response.content, 'html.parser')
                                
                                # Find employer links - try multiple selector patterns
                                emp_links = emp_soup.select('a[href*="/employer/"], a[href*="/organization/"]')
                                
                                if not emp_links:
                                    # Try broader selectors
                                    emp_links = emp_soup.select('.employer-card a, .organization-card a, .employer-listing a')
                                
                                if not emp_links:
                                    # Try more generic selectors
                                    emp_links = emp_soup.select('a[class*="employer"], a[class*="organization"], .card a')
                                
                                for link in emp_links:
                                    if link.has_attr('href'):
                                        emp_url = link['href']
                                        if emp_url.startswith('/'):
                                            emp_url = local_url + emp_url
                                        elif not emp_url.startswith('http'):
                                            emp_url = local_url + '/' + emp_url
                                            
                                        # Add to our employer list if not already there
                                        if emp_url not in employer_list:
                                            employer_list.append(emp_url)
                                
                                if employer_list:
                                    yield json.dumps({"progress": 45, "status": f"Found {len(employer_list)} employers on Prosple"})
                                    break
                            
                        if not employer_list:
                            # No employers found, exit employer mode
                            employer_mode = False
                            continue
                    except Exception as e:
                        print(f"Error fetching employers: {str(e)}")
                        employer_mode = False
                        continue
            
            # Process current employer
            employer_url = employer_list[employer_index]
            employer_index += 1
            
            try:
                yield json.dumps({"progress": 45 + employer_index, "status": f"Checking employer {employer_index}/{len(employer_list)} on Prosple..."})
                
                # Use a different profile for each employer
                current_headers = headers.copy()
                current_headers['User-Agent'] = random.choice(user_agents)
                
                # Set realistic referrer (as if coming from search or previous page)
                if random.random() > 0.3:  # Sometimes come from an external site
                    current_headers['Referer'] = random.choice(referrers)
                else:  # Sometimes navigate from within the site
                    current_headers['Referer'] = 'https://au.prosple.com/employers'
                
                # Human-like delay with some randomness
                time.sleep(2 + random.random() * 3)
                
                # Occasionally add random query parameters to appear more legitimate
                query_params = {}
                if random.random() > 0.7:
                    query_params = {
                        'source': random.choice(['direct', 'search', 'recommendation']),
                        'utm_medium': random.choice(['organic', 'referral']),
                        '_': str(int(time.time() * 1000))  # Timestamp to prevent caching
                    }
                
                emp_response = session.get(employer_url, headers=current_headers, params=query_params, timeout=20)
                
                if emp_response.status_code != 200:
                    continue
                
                emp_soup = BeautifulSoup(emp_response.content, 'html.parser')
                
                # Try multiple patterns to find job listings from this employer
                job_links = emp_soup.select('a[href*="/job/"], a[href*="/opportunity/"]')
                
                if not job_links:
                    # Try more specific selectors
                    job_links = emp_soup.select('.job-listing a, .opportunity-listing a, .position-card a')
                
                if not job_links:
                    # Try more generic selectors
                    job_links = emp_soup.select('a[class*="job"], a[class*="opportunity"], .card a')
                
                # Get the company name from the employer page
                company_name = "Unknown Company"
                company_elem = emp_soup.select_one('h1, .employer-name, .organization-name, .company-name')
                if company_elem:
                    company_name = company_elem.get_text().strip()
                
                for job_link in job_links:
                    if job_link.has_attr('href'):
                        job_url = job_link['href']
                        if job_url.startswith('/'):
                            job_url = local_url + job_url
                        elif not job_url.startswith('http'):
                            job_url = local_url + '/' + job_url
                        
                        # Extract job details from the link or parent container
                        job_title_elem = job_link.select_one('h2, h3, .job-title, .opportunity-title') or job_link
                        job_title = job_title_elem.get_text().strip() if job_title_elem else "Untitled Position"
                        
                        # Find parent container with more details
                        job_container = job_link.find_parent('div', class_=lambda c: c and ('card' in c or 'job' in c or 'listing' in c or 'opportunity' in c))
                        
                        location_elem = None
                        job_type_elem = None
                        closing_date_elem = None
                        
                        if job_container:
                            location_elem = job_container.select_one('.location, .job-location, .opportunity-location')
                            job_type_elem = job_container.select_one('.job-type, .work-type, .employment-type')
                            closing_date_elem = job_container.select_one('.closing-date, .deadline, .application-close')
                        
                        job_location = location_elem.get_text().strip() if location_elem else None
                        job_type = job_type_elem.get_text().strip() if job_type_elem else None
                        closing_date = None
                        
                        if closing_date_elem:
                            closing_date_text = closing_date_elem.get_text().strip()
                            try:
                                if "closing date" in closing_date_text.lower():
                                    date_part = closing_date_text.split(":", 1)[1].strip()
                                    closing_date = parse(date_part).strftime("%Y-%m-%d")
                                else:
                                    closing_date = parse(closing_date_text).strftime("%Y-%m-%d")
                            except:
                                closing_date = closing_date_text
                        
                        # Add job to our list
                        jobs_list.append({
                            'title': job_title,
                            'company': company_name,
                            'link': job_url,
                            'location': job_location,
                            'job_type': job_type,
                            'closing_date': closing_date,
                            'disciplines': prosple_discipline.replace('-', ' ').title(),
                            'international': None,
                            'source': 'Prosple'
                        })
                        
                        total_jobs_found += 1
                
                # Report progress
                if jobs_list:
                    yield json.dumps({"progress": 50, "status": f"Found {total_jobs_found} jobs from Prosple employers"})
                
                # Set a threshold to stop searching employers if we found enough jobs
                if total_jobs_found > 20:
                    employer_mode = False
                    break
                
            except Exception as e:
                print(f"Error processing employer {employer_url}: {str(e)}")
                traceback.print_exc()
            
            # Continue to next employer
            continue
        
        # Regular search mode
        base_url = url_formats[url_index]
        
        # Construct URL for current page
        if page_num == 1:
            url = f"{base_url}"
        else:
            url = f"{base_url}?page={page_num}" if '?' in base_url else f"{base_url}&page={page_num}"
        
        # Implement retry mechanism with exponential backoff
        max_retries = 4
        retry_count = 0
        success = False
        
        while retry_count < max_retries and not success:
            try:
                # Calculate progress
                progress_start = 33 if current_progress < 33 else current_progress
                yield json.dumps({"progress": progress_start, "status": f"Connecting to Prosple (attempt {retry_count + 1})..."})
                
                # Create a unique browser profile for each attempt
                current_headers = headers.copy()
                current_headers['User-Agent'] = random.choice(user_agents)
                
                # Sometimes come from search engines, sometimes from other pages
                if retry_count == 0 or random.random() > 0.5:
                    current_headers['Referer'] = random.choice(referrers)
                else:
                    # Internal navigation is more realistic sometimes
                    current_headers['Referer'] = 'https://au.prosple.com/' + random.choice(['', 'about', 'employers', 'jobs'])
                
                # Add cache buster and other query parameters to appear more legitimate
                query_params = {}
                if page_num > 1:
                    query_params['page'] = page_num
                
                # Add random tracking params that real sites would have
                if random.random() > 0.5:
                    query_params.update({
                        'source': random.choice(['direct', 'search', 'linkedin', 'recommendation']),
                        'utm_medium': random.choice(['organic', 'referral', 'social']),
                        '_': str(int(time.time() * 1000))  # Cache busting timestamp
                    })
                
                # Variable delay with jitter - more human-like pattern
                delay_time = 3 + retry_count + (random.random() * 3)
                time.sleep(delay_time)
                
                # Make request with params
                response = session.get(
                    url.split('?')[0] if query_params and '?' in url else url,
                    params=query_params if query_params else None,
                    headers=current_headers, 
                    timeout=30
                )
                
                # Handle different response status codes
                if response.status_code == 403:
                    retry_count += 1
                    yield json.dumps({"warning": f"Access denied by Prosple (403), retrying with different parameters (attempt {retry_count}/{max_retries})..."})
                    
                    # Exponential backoff
                    time.sleep((2 ** retry_count) + random.random() * 2)
                    continue
                elif response.status_code == 429:
                    # Too many requests - need longer backoff
                    retry_count += 1
                    yield json.dumps({"warning": f"Rate limited by Prosple (429), backing off and retrying (attempt {retry_count}/{max_retries})..."})
                    
                    # Longer delay for rate limiting
                    time.sleep((3 ** retry_count) + random.random() * 5)
                    continue
                elif response.status_code == 200:
                    success = True
                else:
                    # Other status codes
                    retry_count += 1
                    yield json.dumps({"warning": f"Received status {response.status_code} from Prosple, retrying (attempt {retry_count}/{max_retries})..."})
                    time.sleep(2 * retry_count)
                
            except requests.exceptions.Timeout:
                retry_count += 1
                yield json.dumps({"warning": f"Timeout connecting to Prosple, retrying (attempt {retry_count}/{max_retries})..."})
                time.sleep(retry_count * 2)
            except Exception as e:
                retry_count += 1
                print(f"Error accessing Prosple (retry {retry_count}): {str(e)}")
                yield json.dumps({"warning": f"Error accessing Prosple: {str(e)}, retrying (attempt {retry_count}/{max_retries})..."})
                time.sleep(2 + retry_count)
        
        # If all retries failed, try the next URL format or employer mode
        if not success:
            url_index += 1
            if url_index < len(url_formats):
                yield json.dumps({"warning": f"Trying alternative Prosple URL format {url_index + 1}/{len(url_formats)}..."})
                page_num = 1  # Reset page number for the new URL format
                continue
            else:
                # Try employer mode as fallback
                yield json.dumps({"warning": "Could not access Prosple job listings. Switching to employer browsing mode..."})
                employer_mode = True
                continue
        
        try:
            # Parse HTML content
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Check for CAPTCHA or login walls
            captcha_indicators = [
                soup.select_one('form[action*="captcha"]'),
                soup.select_one('div[class*="captcha"]'),
                soup.select_one('img[src*="captcha"]'),
                soup.select_one('div[class*="recaptcha"]'),
                soup.find(string=re.compile(r'captcha|robot|verification', re.I))
            ]
            
            login_indicators = [
                soup.select_one('form[action*="login"]'),
                soup.select_one('input[name="password"]'),
                soup.find(string=re.compile(r'please log ?in|sign ?in required', re.I))
            ]
            
            if any(captcha_indicators):
                yield json.dumps({"warning": "Detected CAPTCHA on Prosple. Switching to employer browsing mode..."})
                employer_mode = True
                continue
                
            if any(login_indicators):
                yield json.dumps({"warning": "Login wall detected on Prosple. Switching to employer browsing mode..."})
                employer_mode = True
                continue
            
            # Find job listings with multiple selector patterns
            job_listings = soup.select('.opportunity-list-item, .job-card, .listing-item, article')
            
            if not job_listings:
                job_listings = soup.select('.job-listing, .card, [data-testid="job-card"], .search-result-card')
            
            if not job_listings:
                job_listings = soup.select('a[href*="/job/"], a[href*="/opportunity/"]')
                # Convert to parent containers for easier processing
                if job_listings:
                    job_listings = [link.find_parent('div', class_=lambda c: c and ('card' in c or 'job' in c or 'listing' in c)) for link in job_listings if link.find_parent('div')]
            
            # Check if we've reached the last page
            if len(job_listings) == 0 or (last_page_count == len(job_listings) and page_num > 1):
                print(f"No more job listings found after Prosple page {page_num-1}.")
                yield json.dumps({"warning": f"No more job listings found after Prosple page {page_num-1}."})
                url_index += 1
                if url_index < len(url_formats):
                    yield json.dumps({"warning": f"Trying alternative Prosple URL format {url_index + 1}/{len(url_formats)}..."})
                    page_num = 1  # Reset page number for the new URL format
                    continue
                else:
                    # Try employer mode as fallback
                    yield json.dumps({"warning": "No more job listings. Switching to employer browsing mode..."})
                    employer_mode = True
                    continue
            
            last_page_count = len(job_listings)
            total_jobs_found += len(job_listings)
            yield json.dumps({"progress": progress_start, "status": f"Found {len(job_listings)} jobs on Prosple page {page_num}"})
            
            # Process each job listing
            job_index = 0
            for job in job_listings:
                job_index += 1
                current_progress = 33 + ((page_num - 1) * len(job_listings) + job_index) / (total_jobs_found * 1.5) * 33 
                yield json.dumps({"progress": current_progress, "status": f"Scraping Prosple page {page_num}, job {job_index}/{len(job_listings)}"})
                
                try:
                    # Extract job title
                    title_elem = job.select_one('.job-title, .title, h2, h3, .name')
                    title = title_elem.get_text().strip() if title_elem else "Untitled Position"
                    
                    # Get job URL
                    url_elem = job.select_one('a[href*="/job/"], a[href*="/opportunity/"]') or job.find('a')
                    if not url_elem or not url_elem.has_attr('href'):
                        continue
                        
                    job_url = url_elem['href']
                    if job_url.startswith('/'):
                        job_url = local_url + job_url
                    elif not job_url.startswith('http'):
                        job_url = local_url + '/' + job_url
                    
                    # Get company name
                    company_elem = job.select_one('.company-name, .employer, .organization')
                    company = company_elem.get_text().strip() if company_elem else "Unknown Company"
                    
                    # Get location
                    location_elem = job.select_one('.location, .job-location')
                    job_location = location_elem.get_text().strip() if location_elem else None
                    
                    # Get job type
                    job_type_elem = job.select_one('.job-type, .work-type, .employment-type')
                    job_type = job_type_elem.get_text().strip() if job_type_elem else None
                    
                    # Get closing date
                    closing_date_elem = job.select_one('.closing-date, .deadline')
                    closing_date = None
                    if closing_date_elem:
                        closing_date_text = closing_date_elem.get_text().strip()
                        try:
                            if "closing date" in closing_date_text.lower():
                                date_part = closing_date_text.split(":", 1)[1].strip()
                                closing_date = parse(date_part).strftime("%Y-%m-%d")
                            else:
                                closing_date = parse(closing_date_text).strftime("%Y-%m-%d")
                        except:
                            closing_date = closing_date_text
                    
                    # Add job to results
                    jobs_list.append({
                        'title': title,
                        'company': company,
                        'link': job_url,
                        'location': job_location,
                        'job_type': job_type,
                        'closing_date': closing_date,
                        'disciplines': prosple_discipline.replace('-', ' ').title(),
                        'international': None,
                        'source': 'Prosple'
                    })
                    
                except Exception as e:
                    print(f"Error processing Prosple job: {str(e)}")
                    traceback.print_exc()
            
            # Check pagination to determine max pages
            pagination = soup.select('.pagination a, .page-link, [class*="pager"] a')
            for page_link in pagination:
                try:
                    page_number = int(''.join(filter(str.isdigit, page_link.text.strip())))
                    if page_number > max_pages:
                        # Still limit to 5 pages to avoid excessive requests
                        max_pages = min(page_number, 5)
                except ValueError:
                    pass
            
            # Increment page number with human-like delay
            page_num += 1
            time.sleep(3 + random.random() * 4)  # Variable delay between 3-7 seconds
        
        except Exception as e:
            print(f"Error scraping Prosple page {page_num}: {str(e)}")
            traceback.print_exc()
            yield json.dumps({"error": f"Error scraping Prosple page {page_num}: {str(e)}"})
            url_index += 1
            if url_index < len(url_formats):
                yield json.dumps({"warning": f"Trying alternative Prosple URL format {url_index + 1}/{len(url_formats)}..."})
                page_num = 1  # Reset page number for the new URL format
            else:
                # Switch to employer mode as fallback
                yield json.dumps({"warning": "Error in scraping. Switching to employer browsing mode..."})
                employer_mode = True
    
    # Report final results
    if not jobs_list:
        yield json.dumps({"warning": "Could not retrieve any jobs from Prosple. They may have implemented stronger protections against automated access."})
    
    yield json.dumps({"progress": 66, "status": "Completed Prosple scraping", "results": jobs_list})
    return jobs_list

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    data = request.json
    job_level = data.get('job_level', 'graduate-jobs')
    discipline = data.get('discipline', 'computer-science')
    location = data.get('location', 'australia')
    source = data.get('source', 'both')
    
    # If 'prosple' or 'all' is selected, change to 'both' (only GradConnection and Seek)
    if source in ['prosple', 'all']:
        source = 'both'
    
    def normalize_location(loc):
        """Normalize location strings to group similar locations together"""
        if not loc:
            return None
            
        # Convert to lowercase for case-insensitive comparison
        loc = loc.lower().strip()
        
        # Define city mappings (main city name -> variations)
        city_mappings = {
            'sydney': ['sydney', 'sydney nsw', 'nsw sydney', 'sydney, nsw', 'sydney australia', 'greater sydney'],
            'melbourne': ['melbourne', 'melbourne vic', 'vic melbourne', 'melbourne, vic', 'melbourne australia', 'greater melbourne'],
            'brisbane': ['brisbane', 'brisbane qld', 'qld brisbane', 'brisbane, qld', 'brisbane australia', 'greater brisbane'],
            'perth': ['perth', 'perth wa', 'wa perth', 'perth, wa', 'perth australia', 'greater perth'],
            'adelaide': ['adelaide', 'adelaide sa', 'sa adelaide', 'adelaide, sa', 'adelaide australia', 'greater adelaide'],
            'canberra': ['canberra', 'canberra act', 'act canberra', 'canberra, act', 'canberra australia', 'australian capital territory'],
            'hobart': ['hobart', 'hobart tas', 'tas hobart', 'hobart, tas', 'hobart australia'],
            'darwin': ['darwin', 'darwin nt', 'nt darwin', 'darwin, nt', 'darwin australia'],
            'gold coast': ['gold coast', 'gold coast qld', 'qld gold coast', 'gold coast, qld'],
            'newcastle': ['newcastle', 'newcastle nsw', 'nsw newcastle', 'newcastle, nsw'],
            'wollongong': ['wollongong', 'wollongong nsw', 'nsw wollongong', 'wollongong, nsw'],
        }
        
        # State abbreviations mapping
        state_abbr = {
            'nsw': 'new south wales',
            'vic': 'victoria',
            'qld': 'queensland',
            'wa': 'western australia',
            'sa': 'south australia',
            'tas': 'tasmania',
            'act': 'australian capital territory',
            'nt': 'northern territory'
        }
        
        # Try to find a match in city mappings
        for city, variations in city_mappings.items():
            for variant in variations:
                if variant in loc or loc in variant:
                    return city.title()  # Return standardized city name with title case
        
        # Check if it's just a state
        for abbr, full_name in state_abbr.items():
            if loc == abbr or loc == full_name:
                return full_name.title()
                
        # If location contains multiple locations separated by commas, pipes, or other delimiters
        if any(delim in loc for delim in [',', '|', ';', '/']):
            locations = re.split(r'[,|;/]', loc)
            # Process each location and take the first valid one
            for subloc in locations:
                normalized = normalize_location(subloc)
                if normalized:
                    return normalized
        
        # If it contains a state abbreviation, extract the main location
        for abbr in state_abbr.keys():
            if f" {abbr}" in loc:
                main_loc = loc.replace(f" {abbr}", "").strip()
                return main_loc.title()
        
        # If we can't normalize it, return the original with title case
        return loc.title()
    
    def generate():
        results = []
        
        # Set progress segment based on selected sources
        progress_segment = 100
        if source == 'both':
            progress_segment = 50  # Each source takes 50% when both are selected
        elif source == 'all':
            progress_segment = 50  # Each source takes 50% when all are selected
        
        if source in ['both', 'gradconnection', 'all']:
            try:
                for update in grad_connection_scrape(job_level, discipline, location):
                    update_data = json.loads(update)
                    # Adjust progress calculation based on source
                    if 'progress' in update_data and source == 'all':
                        update_data['progress'] = update_data['progress'] / 2  # Scale to first half
                    elif 'progress' in update_data and source == 'both':
                        update_data['progress'] = update_data['progress'] / 2  # Scale to half
                    
                    if 'results' in update_data:
                        # Normalize locations in results
                        for job in update_data['results']:
                            if 'location' in job and job['location']:
                                job['location'] = normalize_location(job['location'])
                        results.extend(update_data['results'])
                    yield json.dumps(update_data) + '\n'
            except Exception as e:
                print(f"Error in GradConnection scraping: {str(e)}")
                traceback.print_exc()
                yield json.dumps({"error": str(e), "source": "GradConnection"}) + '\n'
        
        if source in ['both', 'seek', 'all']:
            try:
                # Format location for Seek (replace spaces with hyphens)
                seek_location = location.replace(' ', '-')
                if seek_location.lower() == 'australia':
                    seek_location = 'All-Australia'
                
                # Map discipline to classification codes for Seek
                discipline_map = {
                    'computer-science': '1223',  # ICT
                    'data-science-and-analytics': '1223%2C6281',  # ICT and Science&Technology
                    'engineering': '9201',  # Engineering
                    'finance': '1201',  # Accounting
                    'mathematics': '6281',  # Science & Technology
                    'accounting': '1201',  # Accounting
                    'marketing': '1205',  # Marketing & Communications
                    'business': '1202%2C1203',  # Business & Management
                    'information-technology': '1223',  # Information & Communication Technology
                    'health-sciences': '2206%2C2712'  # Healthcare & Medical
                }
                
                seek_discipline = discipline_map.get(discipline, '1223%2C6281')
                
                for update in seek_scrape(job_level, seek_discipline, seek_location):
                    update_data = json.loads(update)
                    # Adjust progress calculation based on source
                    if 'progress' in update_data:
                        if source == 'all':
                            # Scale to second half (50-100%)
                            update_data['progress'] = (update_data['progress'] / 2) + 50
                        elif source == 'both':
                            # Scale to second half (50-100%)
                            update_data['progress'] = (update_data['progress'] / 2) + 50
                    
                    if 'results' in update_data:
                        # Normalize locations in results
                        for job in update_data['results']:
                            if 'location' in job and job['location']:
                                job['location'] = normalize_location(job['location'])
                        results.extend(update_data['results'])
                    yield json.dumps(update_data) + '\n'
            except Exception as e:
                print(f"Error in Seek scraping: {str(e)}")
                traceback.print_exc()
                yield json.dumps({"error": str(e), "source": "Seek"}) + '\n'
        
        # Prosple scraping code removed as requested
        
        # Return final results after normalizing locations
        yield json.dumps({"complete": True, "results": results}) + '\n'
    
    return Response(stream_with_context(generate()), content_type='text/event-stream')

if __name__ == '__main__':
    app.run(debug=True) 