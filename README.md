# JobScrape - Multi-Source Job Search Platform

JobScrape is a web application that searches for job listings from multiple sources including GradConnection and Seek. It allows users to filter jobs by discipline, location, and job level.

## Features

- Search for jobs from GradConnection and Seek simultaneously
- Filter by job level (graduate, internship, entry-level)
- Filter by discipline (Computer Science, Data Science, Engineering, etc.)
- Filter by location
- Colorful and responsive user interface
- Real-time filtering of search results

## Installation

1. Clone this repository:
```
git clone https://github.com/yourusername/jobscrape.git
cd jobscrape
```

2. Create a virtual environment (optional but recommended):
```
python -m venv venv
```

3. Activate the virtual environment:
   - On Windows:
   ```
   venv\Scripts\activate
   ```
   - On macOS/Linux:
   ```
   source venv/bin/activate
   ```

4. Install the required dependencies:
```
pip install -r requirements.txt
```

## Usage

1. Start the Flask application:
```
python app.py
```

2. Open your web browser and navigate to:
```
http://127.0.0.1:5000/
```

3. Use the filter options to search for jobs that match your criteria.

## Project Structure

```
jobscrape/
├── app.py                  # Flask application
├── requirements.txt        # Dependencies
├── templates/              # HTML templates
│   └── index.html          # Main page
├── static/                 # Static files
│   ├── css/
│   │   └── style.css       # CSS styles
│   └── js/
│       └── script.js       # JavaScript functions
└── README.md               # This file
```

## Notes

- The application respects website scraping policies by implementing appropriate delays between requests
- The search is limited to 3 pages from each source to avoid long wait times
- For production use, consider implementing caching or a scheduled job to update the database periodically

## License

MIT

## Acknowledgements

- This application uses data from GradConnection and Seek
- Built with Flask, Bootstrap, and BeautifulSoup 