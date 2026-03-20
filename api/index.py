from flask import Flask, render_template, request
import requests
import os

app = Flask(__name__, template_folder='../templates')

def get_book_data(isbn):
    """Fetch book data from Open Library API"""
    isbn = isbn.replace('-', '').replace(' ', '').strip()

    # Try Open Library Books API
    url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
    response = requests.get(url, timeout=10)
    data = response.json()

    key = f"ISBN:{isbn}"
    if key not in data:
        return None

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

    # Extract publication info
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
    }

    # Extract subjects
    if 'subjects' in book:
        result['subjects'] = [subj.get('name', '') for subj in book['subjects'][:5]]

    # Try to get more details from Works API
    if 'identifiers' in book:
        identifiers = book['identifiers']
        if 'openlibrary' in identifiers:
            work_id = identifiers['openlibrary'][0]
            try:
                work_url = f"https://openlibrary.org/works/{work_id}.json"
                work_response = requests.get(work_url, timeout=5)
                work_data = work_response.json()

                # Check for edition/volume in description
                if 'description' in work_data:
                    desc = work_data['description']
                    if isinstance(desc, dict):
                        desc = desc.get('value', '')
            except:
                pass

    # Try to extract copyright from publish_date
    if result['publish_date'] and result['publish_date'] != 'Unknown':
        # Extract year for copyright
        import re
        year_match = re.search(r'\d{4}', result['publish_date'])
        if year_match:
            result['copyright'] = year_match.group()

    return result

@app.route('/', methods=['GET', 'POST'])
def index():
    book = None
    error = None

    if request.method == 'POST':
        isbn = request.form.get('isbn', '').strip()
        if isbn:
            try:
                book = get_book_data(isbn)
                if not book:
                    error = f"No book found for ISBN: {isbn}"
            except requests.exceptions.Timeout:
                error = "Request timed out. Please try again."
            except Exception as e:
                error = f"Error fetching book data: {str(e)}"
        else:
            error = "Please enter an ISBN"

    return render_template('index.html', book=book, error=error)

# For local development
if __name__ == '__main__':
    app.run(debug=True, port=5000)
