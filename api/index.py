from flask import Flask, render_template, request
import requests
import os
import json
from datetime import date
import re
from dotenv import load_dotenv

# Load .env file
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))

app = Flask(__name__, template_folder='../templates')

# Request tracker file - use absolute path for reliability
TRACKER_DIR = os.path.dirname(os.path.abspath(__file__))
TRACKER_FILE = os.path.join(TRACKER_DIR, 'request_tracker.json')
GOOGLE_DAILY_LIMIT = 1000

# Google Books API key (set as environment variable for production)
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY', '')

def load_tracker():
    """Load request tracker from file"""
    try:
        if os.path.exists(TRACKER_FILE):
            with open(TRACKER_FILE, 'r') as f:
                data = json.load(f)
                # Reset if it's a new day
                if data.get('date') != str(date.today()):
                    return {'date': str(date.today()), 'google_requests': 0, 'openlib_requests': 0}
                return data
    except:
        pass
    return {'date': str(date.today()), 'google_requests': 0, 'openlib_requests': 0}

def save_tracker(tracker):
    """Save request tracker to file"""
    try:
        with open(TRACKER_FILE, 'w') as f:
            json.dump(tracker, f)
    except Exception as e:
        print(f"Error saving tracker: {e}")

def get_tracker_stats():
    """Get current tracker statistics"""
    tracker = load_tracker()
    return {
        'date': tracker['date'],
        'google_requests': tracker['google_requests'],
        'google_remaining': max(0, GOOGLE_DAILY_LIMIT - tracker['google_requests']),
        'google_limit': GOOGLE_DAILY_LIMIT,
        'openlib_requests': tracker['openlib_requests'],
        'total_requests': tracker['google_requests'] + tracker['openlib_requests'],
        'has_google_key': bool(GOOGLE_API_KEY)
    }

def get_book_from_google(isbn):
    """Fetch book data from Google Books API"""
    if not GOOGLE_API_KEY:
        return None, "No Google API key configured"

    tracker = load_tracker()
    if tracker['google_requests'] >= GOOGLE_DAILY_LIMIT:
        return None, "Google API daily limit reached"

    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}&key={GOOGLE_API_KEY}"
    response = requests.get(url, timeout=(3, 5))
    data = response.json()

    # Update tracker
    tracker['google_requests'] += 1
    save_tracker(tracker)

    if 'items' not in data or len(data['items']) == 0:
        return None, "Book not found in Google Books"

    book = data['items'][0]['volumeInfo']

    # Get cover image - use Google's actual sizes (no zoom hack)
    cover_url = ''
    if 'imageLinks' in book:
        # Prefer larger images if available
        cover_url = book['imageLinks'].get('large',
                    book['imageLinks'].get('medium',
                    book['imageLinks'].get('thumbnail', '')))
        cover_url = cover_url.replace('&edge=curl', '')
        cover_url = cover_url.replace('http://', 'https://')

    # Fallback to Open Library cover if no Google cover
    if not cover_url:
        cover_url = f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"

    result = {
        'title': book.get('title', 'Unknown Title'),
        'authors': ', '.join(book.get('authors', ['Unknown Author'])),
        'publishers': book.get('publisher', 'Unknown Publisher'),
        'publish_date': book.get('publishedDate', 'Unknown'),
        'number_of_pages': book.get('pageCount', 'Unknown'),
        'cover_url': cover_url,
        'isbn': isbn,
        'edition': '',
        'copyright': '',
        'volume': '',
        'subjects': book.get('categories', [])[:5],
        'physical_format': book.get('printType', ''),
        'source': 'Google Books'
    }

    # Extract copyright year from publish date
    if result['publish_date'] and result['publish_date'] != 'Unknown':
        year_match = re.search(r'\d{4}', result['publish_date'])
        if year_match:
            result['copyright'] = year_match.group()

    return result, None

def get_book_from_openlibrary(isbn):
    """Fetch book data from Open Library API"""
    tracker = load_tracker()

    url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
    response = requests.get(url, timeout=(3, 5))
    data = response.json()

    # Update tracker
    tracker['openlib_requests'] += 1
    save_tracker(tracker)

    key = f"ISBN:{isbn}"
    if key not in data:
        return None, "Book not found in Open Library"

    book = data[key]

    # Build cover URL
    cover_url = f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"

    # Extract authors
    authors = []
    if 'authors' in book:
        authors = [author.get('name', '') for author in book['authors']]

    # Extract publishers
    publishers = []
    if 'publishers' in book:
        publishers = [pub.get('name', '') for pub in book['publishers']]

    result = {
        'title': book.get('title', 'Unknown Title'),
        'authors': ', '.join(authors) if authors else 'Unknown Author',
        'publishers': ', '.join(publishers) if publishers else 'Unknown Publisher',
        'publish_date': book.get('publish_date', 'Unknown'),
        'number_of_pages': book.get('number_of_pages', 'Unknown'),
        'cover_url': cover_url,
        'isbn': isbn,
        'edition': book.get('edition_name', ''),
        'copyright': '',
        'volume': '',
        'subjects': [],
        'physical_format': book.get('physical_format', ''),
        'source': 'Open Library'
    }

    # Extract subjects
    if 'subjects' in book:
        result['subjects'] = [subj.get('name', '') for subj in book['subjects'][:5]]

    # Extract copyright from publish_date
    if result['publish_date'] and result['publish_date'] != 'Unknown':
        year_match = re.search(r'\d{4}', result['publish_date'])
        if year_match:
            result['copyright'] = year_match.group()

    return result, None

def get_book_data(isbn, api_choice='auto'):
    """Fetch book data based on API choice"""
    isbn = isbn.replace('-', '').replace(' ', '').strip()

    if api_choice == 'google':
        book, error = get_book_from_google(isbn)
        return book, error

    elif api_choice == 'openlib':
        book, error = get_book_from_openlibrary(isbn)
        return book, error

    else:  # auto - try Google first, fall back to Open Library
        book, google_error = get_book_from_google(isbn)
        if book:
            return book, None

        book, openlib_error = get_book_from_openlibrary(isbn)
        if book:
            return book, None

        # Return the most relevant error
        if google_error and "not found" in google_error.lower():
            return None, f"Book not found in either API"
        return None, google_error or openlib_error

@app.route('/', methods=['GET', 'POST'])
def index():
    book = None
    error = None
    api_choice = 'auto'
    stats = get_tracker_stats()

    if request.method == 'POST':
        isbn = request.form.get('isbn', '').strip()
        api_choice = request.form.get('api_choice', 'auto')

        if isbn:
            try:
                book, error = get_book_data(isbn, api_choice)
                if not book and not error:
                    error = f"No book found for ISBN: {isbn}"
                stats = get_tracker_stats()  # Refresh stats after request
            except requests.exceptions.Timeout:
                error = "Request timed out. Please try again."
            except Exception as e:
                error = f"Error fetching book data: {str(e)}"
        else:
            error = "Please enter an ISBN"

    return render_template('index.html', book=book, error=error, stats=stats, api_choice=api_choice)

# For local development
if __name__ == '__main__':
    app.run(debug=True, port=5000)
