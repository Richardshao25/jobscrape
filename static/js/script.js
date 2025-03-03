document.addEventListener('DOMContentLoaded', function() {
    const searchForm = document.getElementById('search-form');
    const resultsContainer = document.getElementById('results-container');
    const loader = document.getElementById('loader');
    const resultFilter = document.getElementById('result-filter');
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-bar');
    const progressStatus = document.getElementById('progress-status');
    const progressPercentage = document.getElementById('progress-percentage');
    const advancedFilters = document.getElementById('advanced-filters');
    const applyFiltersBtn = document.getElementById('apply-filters');
    const resetFiltersBtn = document.getElementById('reset-filters');
    
    // Store all job results
    let allJobs = [];
    let warnings = [];
    
    searchForm.addEventListener('submit', function(e) {
        e.preventDefault();
        performSearch();
    });
    
    resultFilter.addEventListener('input', function() {
        const query = this.value.toLowerCase();
        filterResultsByText(query);
    });
    
    applyFiltersBtn.addEventListener('click', function() {
        applyAdvancedFilters();
    });
    
    resetFiltersBtn.addEventListener('click', function() {
        resetAdvancedFilters();
    });
    
    async function performSearch() {
        // Get form values
        const jobLevel = document.getElementById('job-level').value;
        const discipline = document.getElementById('discipline').value;
        const location = document.getElementById('location').value;
        const source = document.getElementById('source').value;
        
        // Show loader and progress bar, hide any previous results
        loader.classList.remove('d-none');
        progressContainer.classList.remove('d-none');
        advancedFilters.classList.add('d-none');
        resultsContainer.innerHTML = '';
        
        // Reset progress and warnings
        updateProgress(0, 'Starting search...');
        warnings = [];
        allJobs = [];
        
        try {
            // Send search request to backend
            const response = await fetch('/search', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    job_level: jobLevel,
                    discipline: discipline,
                    location: location,
                    source: source
                }),
            });
            
            if (!response.ok) {
                throw new Error(`Server responded with status: ${response.status}`);
            }
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            
            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                
                buffer += decoder.decode(value, { stream: true });
                
                // Split by newlines to handle multiple JSON objects
                const lines = buffer.split('\n');
                buffer = lines.pop(); // Keep the last incomplete line in the buffer
                
                // Process each complete line
                for (const line of lines) {
                    const trimmedLine = line.trim();
                    if (trimmedLine) {
                        try {
                            const data = JSON.parse(trimmedLine);
                            processStreamData(data);
                        } catch (e) {
                            console.error('Error parsing JSON:', e, trimmedLine);
                        }
                    }
                }
            }
            
            // Process any remaining data in the buffer
            if (buffer.trim()) {
                try {
                    const data = JSON.parse(buffer.trim());
                    processStreamData(data);
                } catch (e) {
                    console.error('Error parsing JSON:', e, buffer);
                }
            }
            
            // Hide loader once processing is complete
            loader.classList.add('d-none');
            
            // Show completion message or warnings if no jobs found
            if (allJobs.length === 0) {
                let errorMessage = 'No jobs found matching your criteria.';
                if (warnings.length > 0) {
                    errorMessage += ' There were some issues during the search:<br>';
                    errorMessage += warnings.map(w => `- ${w}`).join('<br>');
                }
                displayError(errorMessage);
            }
            
        } catch (error) {
            console.error('Error performing search:', error);
            loader.classList.add('d-none');
            progressContainer.classList.add('d-none');
            displayError('An error occurred while searching for jobs: ' + error.message);
        }
    }
    
    function processStreamData(data) {
        // Log all data for debugging
        console.log('Stream data:', data);
        
        // Update progress if progress info is available
        if (data.progress !== undefined) {
            updateProgress(data.progress, data.status || 'Processing...');
        }
        
        // Process warnings
        if (data.warning) {
            console.warn('Warning:', data.warning);
            warnings.push(data.warning);
            // Show warning in the progress status
            progressStatus.innerHTML = `<span class="text-warning">${data.warning}</span>`;
        }
        
        // Process errors
        if (data.error) {
            console.error('Error:', data.error);
            warnings.push(`Error: ${data.error}`);
            // Show error in the progress status
            progressStatus.innerHTML = `<span class="text-danger">${data.error}</span>`;
        }
        
        // Process results if they are available
        if (data.results && data.results.length > 0) {
            displayResults(data.results);
        }
        
        // Handle completion
        if (data.complete) {
            updateProgress(100, 'Search completed!');
            progressContainer.classList.add('d-none');
            
            if (allJobs.length > 0) {
                // Show advanced filters
                advancedFilters.classList.remove('d-none');
                
                // Populate filter dropdowns
                populateFilterOptions();
            }
        }
    }
    
    function updateProgress(percentage, status) {
        const roundedPercentage = Math.round(percentage);
        progressBar.style.width = `${roundedPercentage}%`;
        progressBar.setAttribute('aria-valuenow', roundedPercentage);
        progressBar.textContent = `${roundedPercentage}%`;
        progressPercentage.textContent = `${roundedPercentage}%`;
        progressStatus.textContent = status;
    }
    
    function displayResults(jobs) {
        // Add new jobs to the allJobs array, avoiding duplicates
        jobs.forEach(job => {
            // Check if this job is already in the list (by URL)
            const isDuplicate = allJobs.some(existingJob => existingJob.link === job.link);
            if (!isDuplicate) {
                allJobs.push(job);
            }
        });
        
        // Clear the results container if this is the first set of results
        if (resultsContainer.querySelector('.initial-message')) {
            resultsContainer.innerHTML = '';
        }
        
        if (allJobs.length === 0) {
            resultsContainer.innerHTML = `
                <div class="col-12 text-center py-5">
                    <i class="fas fa-exclamation-circle fa-3x mb-3 text-muted"></i>
                    <p class="text-muted">No jobs found matching your criteria. Try adjusting your filters.</p>
                </div>
            `;
            return;
        }
        
        // Only show the results count and toggle button once
        if (!resultsContainer.querySelector('.results-count')) {
            const resultsCount = document.createElement('div');
            resultsCount.className = 'col-12 mb-3 results-count';
            resultsCount.innerHTML = `
                <div class="d-flex justify-content-between align-items-center">
                    <p class="text-muted mb-0">Found ${allJobs.length} jobs matching your criteria</p>
                    <button id="toggle-filters-btn" class="btn btn-sm btn-outline-primary">
                        <i class="fas fa-sliders-h me-1"></i> Advanced Filters
                    </button>
                </div>
            `;
            resultsContainer.appendChild(resultsCount);
            
            // Add sorting controls
            addSortingControls();
            
            // Add toggle filters button functionality
            document.getElementById('toggle-filters-btn').addEventListener('click', function() {
                if (advancedFilters.classList.contains('d-none')) {
                    advancedFilters.classList.remove('d-none');
                    this.innerHTML = '<i class="fas fa-times me-1"></i> Hide Filters';
                } else {
                    advancedFilters.classList.add('d-none');
                    this.innerHTML = '<i class="fas fa-sliders-h me-1"></i> Advanced Filters';
                }
            });
        } else {
            // Update the count if it already exists
            const countElem = resultsContainer.querySelector('.results-count p');
            if (countElem) {
                countElem.textContent = `Found ${allJobs.length} jobs matching your criteria`;
            }
        }
        
        // Create job cards only for new jobs
        jobs.forEach(job => {
            // Check if this job card already exists in the container
            const existingCard = resultsContainer.querySelector(`[data-url="${job.link}"]`);
            if (!existingCard) {
                const jobCard = createJobCard(job);
                resultsContainer.appendChild(jobCard);
            }
        });
        
        // Show advanced filters
        advancedFilters.classList.remove('d-none');
        
        // Populate filter dropdowns
        populateFilterOptions();
        
        // Hide loader as we display results
        loader.classList.add('d-none');
    }
    
    function createJobCard(job) {
        const col = document.createElement('div');
        col.className = 'col-md-6 col-lg-4 job-result-item';
        
        // Set data attributes for filtering
        col.setAttribute('data-title', job.title?.toLowerCase() || '');
        col.setAttribute('data-company', job.company?.toLowerCase() || '');
        col.setAttribute('data-location', job.location?.toLowerCase() || '');
        col.setAttribute('data-job-type', job.job_type?.toLowerCase() || '');
        col.setAttribute('data-source', job.source || '');
        col.setAttribute('data-closing-date', job.closing_date || '');
        col.setAttribute('data-international', job.international?.toLowerCase() || 'no');
        col.setAttribute('data-url', job.link || '');
        col.setAttribute('data-date-posted', job.date_posted || '');
        
        // Determine the source class for styling
        let sourceClass = '';
        if (job.source === 'Seek') {
            sourceClass = 'seek';
        } else if (job.source === 'GradConnection') {
            sourceClass = 'gradconnection';
        } else if (job.source === 'Prosple') {
            sourceClass = 'prosple';
        }
        
        // Start with a structured card HTML
        let html = `
            <div class="card job-card">
                <div class="card-header">
                    <h5 class="card-title">${job.title || 'Untitled Position'}</h5>
                    <h6 class="company-name">${job.company || 'Unknown Company'}</h6>
                    <span class="source-tag ${sourceClass}">${job.source}</span>
                </div>
                <div class="card-body">
                    <div class="job-details-container">
        `;
        
        // Add location if available
        if (job.location) {
            html += `
                <div class="job-detail">
                    <i class="fas fa-map-marker-alt"></i>
                    <span>${job.location}</span>
                </div>
            `;
        }
        
        // Add job type if available
        if (job.job_type) {
            html += `
                <div class="job-detail">
                    <i class="fas fa-briefcase"></i>
                    <span>${job.job_type}</span>
                </div>
            `;
        }
        
        // Add disciplines if available
        if (job.disciplines) {
            html += `
                <div class="job-detail">
                    <i class="fas fa-graduation-cap"></i>
                    <span>${job.disciplines}</span>
                </div>
            `;
        }
        
        // Add closing date if available
        if (job.closing_date) {
            html += `
                <div class="job-detail">
                    <i class="fas fa-calendar-times"></i>
                    <span>Closes: ${job.closing_date}</span>
                </div>
            `;
        } else if (job.date_posted) {
            html += `
                <div class="job-detail">
                    <i class="fas fa-calendar-alt"></i>
                    <span>Posted: ${job.date_posted}</span>
                </div>
            `;
        }
        
        // Add international status if available
        if (job.international && job.international.toLowerCase() !== 'no') {
            html += `
                <div class="job-detail">
                    <i class="fas fa-globe"></i>
                    <span>International students accepted</span>
                </div>
            `;
        }
        
        // Complete the card HTML
        html += `
                    </div>
                    <a href="${job.link}" target="_blank" class="btn btn-apply">
                        <i class="fas fa-external-link-alt me-2"></i>View Job
                    </a>
                </div>
            </div>
        `;
        
        col.innerHTML = html;
        return col;
    }
    
    function populateFilterOptions() {
        // Clear existing options
        const jobTypeFilter = document.getElementById('filter-job-type');
        const companyFilter = document.getElementById('filter-company');
        const cityFilter = document.getElementById('filter-city');
        const sourceFilter = document.getElementById('filter-source');
        
        // Reset to only keep the first "All" option
        jobTypeFilter.innerHTML = '<option value="">All Types</option>';
        companyFilter.innerHTML = '<option value="">All Companies</option>';
        cityFilter.innerHTML = '<option value="">All Cities</option>';
        sourceFilter.innerHTML = '<option value="">All Sources</option><option value="GradConnection">GradConnection</option><option value="Seek">Seek</option>';
        
        // Extract unique values for each filter
        const jobTypes = new Set();
        const companies = new Set();
        const cities = new Set();
        
        allJobs.forEach(job => {
            if (job.job_type) jobTypes.add(job.job_type);
            if (job.company) companies.add(job.company);
            
            // Extract cities from location
            if (job.location) {
                const locationParts = job.location.split(',');
                if (locationParts.length > 0) {
                    const city = locationParts[0].trim();
                    if (city) cities.add(city);
                }
            }
        });
        
        // Sort alphabetically
        const sortedJobTypes = [...jobTypes].sort();
        const sortedCompanies = [...companies].sort();
        const sortedCities = [...cities].sort();
        
        // Add options to the filters
        sortedJobTypes.forEach(jobType => {
            const option = document.createElement('option');
            option.value = jobType;
            option.textContent = jobType;
            jobTypeFilter.appendChild(option);
        });
        
        sortedCompanies.forEach(company => {
            const option = document.createElement('option');
            option.value = company;
            option.textContent = company;
            companyFilter.appendChild(option);
        });
        
        sortedCities.forEach(city => {
            const option = document.createElement('option');
            option.value = city;
            option.textContent = city;
            cityFilter.appendChild(option);
        });
    }
    
    function filterResultsByText(query) {
        const items = document.querySelectorAll('.job-result-item');
        
        items.forEach(item => {
            const title = item.getAttribute('data-title') || '';
            const company = item.getAttribute('data-company') || '';
            const location = item.getAttribute('data-location') || '';
            
            if (title.includes(query) || company.includes(query) || location.includes(query)) {
                item.style.display = 'block';
            } else {
                item.style.display = 'none';
            }
        });
        
        // Update visible count
        updateVisibleCount();
    }
    
    function applyAdvancedFilters() {
        const jobType = document.getElementById('filter-job-type').value;
        const company = document.getElementById('filter-company').value;
        const city = document.getElementById('filter-city').value;
        const source = document.getElementById('filter-source').value;
        const international = document.getElementById('filter-international').checked;
        const closingFrom = document.getElementById('filter-closing-from').value;
        const closingTo = document.getElementById('filter-closing-to').value;
        
        const items = document.querySelectorAll('.job-result-item');
        
        items.forEach(item => {
            let visible = true;
            
            // Filter by job type
            if (jobType && !itemMatches(item, 'data-job-type', jobType, true)) {
                visible = false;
            }
            
            // Filter by company
            if (company && !itemMatches(item, 'data-company', company, false)) {
                visible = false;
            }
            
            // Filter by city
            if (city && !itemContains(item, 'data-location', city)) {
                visible = false;
            }
            
            // Filter by source
            if (source && !itemMatches(item, 'data-source', source, true)) {
                visible = false;
            }
            
            // Filter by international
            if (international && !itemMatches(item, 'data-international', 'yes', false)) {
                visible = false;
            }
            
            // Filter by closing date range
            const closingDate = item.getAttribute('data-closing-date');
            if (closingDate) {
                if (closingFrom && closingDate < closingFrom) {
                    visible = false;
                }
                if (closingTo && closingDate > closingTo) {
                    visible = false;
                }
            }
            
            // Apply visibility
            item.style.display = visible ? 'block' : 'none';
        });
        
        // Update visible count
        updateVisibleCount();
    }
    
    // Helper function to check if item attribute matches value exactly
    function itemMatches(item, attribute, value, exactMatch) {
        const attrValue = item.getAttribute(attribute) || '';
        if (exactMatch) {
            return attrValue.toLowerCase() === value.toLowerCase();
        } else {
            return attrValue.toLowerCase().includes(value.toLowerCase());
        }
    }
    
    // Helper function to check if item attribute contains value
    function itemContains(item, attribute, value) {
        const attrValue = item.getAttribute(attribute) || '';
        return attrValue.toLowerCase().includes(value.toLowerCase());
    }
    
    function resetAdvancedFilters() {
        // Reset all filter form elements
        document.getElementById('filter-job-type').value = '';
        document.getElementById('filter-company').value = '';
        document.getElementById('filter-city').value = '';
        document.getElementById('filter-source').value = '';
        document.getElementById('filter-international').checked = false;
        document.getElementById('filter-closing-from').value = '';
        document.getElementById('filter-closing-to').value = '';
        
        // Show all job items
        const items = document.querySelectorAll('.job-result-item');
        items.forEach(item => {
            item.style.display = 'block';
        });
        
        // Update visible count
        updateVisibleCount();
    }
    
    // Update the count of visible jobs after filtering
    function updateVisibleCount() {
        const countElem = resultsContainer.querySelector('.results-count p');
        if (countElem) {
            const visibleCount = document.querySelectorAll('.job-result-item[style="display: block;"], .job-result-item:not([style*="display"])').length;
            countElem.textContent = `Showing ${visibleCount} of ${allJobs.length} jobs`;
        }
    }
    
    function displayError(message) {
        resultsContainer.innerHTML = `
            <div class="col-12 text-center py-5">
                <i class="fas fa-exclamation-triangle fa-3x mb-3 text-danger"></i>
                <p class="text-danger">${message}</p>
            </div>
        `;
    }
    
    // Add sorting functionality
    function addSortingControls() {
        const resultsCount = document.querySelector('.results-count');
        if (!resultsCount) return;
        
        const sortControls = document.createElement('div');
        sortControls.className = 'sort-controls';
        sortControls.innerHTML = `
            <label for="sort-jobs">Sort by:</label>
            <select id="sort-jobs" class="form-select">
                <option value="closing-soon">Closing Soon</option>
                <option value="closing-later">Closing Later</option>
            </select>
        `;
        
        resultsCount.appendChild(sortControls);
        
        // Add event listener for sorting
        document.getElementById('sort-jobs').addEventListener('change', function(e) {
            const sortBy = e.target.value;
            const jobItems = document.querySelectorAll('.job-result-item');
            const jobArray = Array.from(jobItems);
            
            jobArray.sort((a, b) => {
                switch(sortBy) {
                    case 'closing-soon':
                        return new Date(a.getAttribute('data-closing-date')) - new Date(b.getAttribute('data-closing-date'));
                    case 'closing-later':
                        return new Date(b.getAttribute('data-closing-date')) - new Date(a.getAttribute('data-closing-date'));
                    default:
                        return 0;
                }
            });
            
            // Re-append sorted items
            const resultsContainer = document.getElementById('results-container');
            jobArray.forEach(item => resultsContainer.appendChild(item));
        });
    }
}); 