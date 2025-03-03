document.addEventListener('DOMContentLoaded', function() {
    const resumeModal = new bootstrap.Modal(document.getElementById('resumeModal'));
    const modifyResumeBtn = document.getElementById('modify-resume-btn');
    const resumeUploadForm = document.getElementById('resume-upload-form');
    const downloadModifiedBtn = document.getElementById('download-modified-resume');
    const modificationSuggestions = document.getElementById('modification-suggestions');

    // Handle resume modification button click
    modifyResumeBtn.addEventListener('click', function() {
        resumeModal.show();
    });

    // Handle resume upload
    resumeUploadForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        const resumeFile = document.getElementById('resume-file').files[0];
        if (!resumeFile) {
            alert('Please select a resume file');
            return;
        }

        const formData = new FormData();
        formData.append('resume', resumeFile);
        formData.append('job_id', window.location.pathname.split('/').pop());

        try {
            const response = await fetch('/analyze-resume', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error('Failed to analyze resume');
            }

            const data = await response.json();
            displayModificationSuggestions(data.suggestions);
        } catch (error) {
            console.error('Error:', error);
            alert('Failed to analyze resume. Please try again.');
        }
    });

    // Handle modified resume download
    downloadModifiedBtn.addEventListener('click', async function() {
        try {
            const response = await fetch(`/download-modified-resume/${window.location.pathname.split('/').pop()}`);
            if (!response.ok) {
                throw new Error('Failed to download modified resume');
            }
            
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'modified_resume.pdf';
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        } catch (error) {
            console.error('Error:', error);
            alert('Failed to download modified resume. Please try again.');
        }
    });

    // Display modification suggestions
    function displayModificationSuggestions(suggestions) {
        modificationSuggestions.innerHTML = '';
        
        suggestions.forEach(suggestion => {
            const suggestionElement = document.createElement('div');
            suggestionElement.className = 'suggestion-item mb-3';
            suggestionElement.innerHTML = `
                <div class="suggestion-header">
                    <i class="fas fa-lightbulb text-warning me-2"></i>
                    <strong>${suggestion.title}</strong>
                </div>
                <div class="suggestion-content">
                    <p>${suggestion.description}</p>
                    ${suggestion.examples ? `
                        <div class="suggestion-examples">
                            <strong>Examples:</strong>
                            <ul>
                                ${suggestion.examples.map(example => `<li>${example}</li>`).join('')}
                            </ul>
                        </div>
                    ` : ''}
                </div>
            `;
            modificationSuggestions.appendChild(suggestionElement);
        });
    }

    // Load similar jobs
    async function loadSimilarJobs() {
        try {
            const response = await fetch(`/similar-jobs/${window.location.pathname.split('/').pop()}`);
            if (!response.ok) {
                throw new Error('Failed to load similar jobs');
            }

            const jobs = await response.json();
            const similarJobsList = document.querySelector('.similar-jobs-list');
            
            jobs.forEach(job => {
                const jobElement = document.createElement('div');
                jobElement.className = 'similar-job-item mb-3';
                jobElement.innerHTML = `
                    <h6 class="mb-1">${job.title}</h6>
                    <p class="mb-1 text-muted">${job.company}</p>
                    <a href="/job/${job.id}" class="btn btn-sm btn-outline-primary">View Details</a>
                `;
                similarJobsList.appendChild(jobElement);
            });
        } catch (error) {
            console.error('Error:', error);
        }
    }

    // Load similar jobs when page loads
    loadSimilarJobs();
}); 