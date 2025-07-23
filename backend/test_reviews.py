import asyncio
import aiohttp
from parsel import Selector
from urllib.parse import urlencode, urlparse, parse_qs, urljoin
import json
from typing import List, Dict
import time

def extract_hotel_id_from_url(url: str) -> str:
    """Extract hotel ID from a Booking.com URL"""
    parsed = urlparse(url)
    path_parts = parsed.path.split('/')
    if len(path_parts) >= 3:
        hotel_name = path_parts[-1].replace('.html', '')
        if hotel_name:
            return hotel_name
    return None

async def parse_reviews_from_main_page(html: str) -> List[dict]:
    """Parse reviews from the main hotel page"""
    sel = Selector(text=html)
    parsed = []
    
    # Find all review blocks
    for review in sel.css('[data-testid="review"]'):
        # Get the review score
        score = review.css('[data-testid="review-score"]::text').get('').strip()
        
        # Get review title
        title = review.css('[data-testid="review-title"]::text').get('').strip()
        
        # Get reviewer name
        reviewer = review.css('[data-testid="review-reviewer-name"]::text').get('').strip()
        
        # Get review date
        date = review.css('[data-testid="review-date"]::text').get('').strip()
        
        # Get review text
        pos_text = ' '.join(review.css('[data-testid="review-positive"]::text').getall()).strip()
        neg_text = ' '.join(review.css('[data-testid="review-negative"]::text').getall()).strip()
        
        # Get reviewer country
        country = review.css('[data-testid="review-reviewer-country"]::text').get('').strip()
        
        # Get room type
        room_type = review.css('[data-testid="review-stayed-room-info"]::text').get('').strip()
        
        # Get stay duration
        stay_info = review.css('[data-testid="review-stay-info"]::text').get('').strip()
        
        review_data = {
            "score": score,
            "title": title,
            "reviewer_name": reviewer,
            "date": date,
            "positive_text": pos_text,
            "negative_text": neg_text,
            "country": country,
            "room_type": room_type,
            "stay_info": stay_info
        }
        
        # Only add reviews that have some content
        if any(review_data.values()):
            parsed.append(review_data)
            
    return parsed

async def get_raw_reviews(html: str):
    """Get raw content from review divs"""
    sel = Selector(text=html)
    reviews = []
    
    # Find all review divs in the modal/reviews page
    review_divs = sel.css('[data-testid="review-card"]')
    print(f"Found {len(review_divs)} review divs")
    
    for review in review_divs:
        # Get all text content within the review div
        all_text = review.css('*::text').getall()
        # Get all HTML content
        raw_html = review.get()
        
        reviews.append({
            "text_content": [text.strip() for text in all_text if text.strip()],
            "html": raw_html
        })
        
    return reviews

async def extract_reviews(html: str) -> List[Dict]:
    """Extract specific review elements from the page"""
    sel = Selector(text=html)
    reviews = []
    
    # Process each review
    for review in sel.css('.review_item'):
        review_data = {
            "reviewer_name": review.css('.reviewer_name span::text').get('').strip(),
            "reviewer_country": review.css('.reviewer_country span[itemprop="name"]::text').get('').strip(),
            "review_count": review.css('.review_item_user_review_count::text').get('').strip(),
            "review_title": review.css('.review_item_header_content span[itemprop="name"]::text').get('').strip(),
            "review_positive": review.css('.review_pos span[itemprop="reviewBody"]::text').getall(),
            "review_negative": review.css('.review_neg span[itemprop="reviewBody"]::text').getall(),
            "review_date": review.css('.review_item_date::text').get('').strip(),
            "review_score": review.css('.review-score-badge::text').get('').strip()
        }
        
        # Clean up the positive and negative review bodies - join multiple paragraphs and strip whitespace
        review_data["review_positive"] = ' '.join([text.strip() for text in review_data["review_positive"] if text.strip()])
        review_data["review_negative"] = ' '.join([text.strip() for text in review_data["review_negative"] if text.strip()])
        
        # Only add reviews that have some content
        if any(review_data.values()):
            reviews.append(review_data)
    
    return reviews

async def scrape_hotel_reviews(base_url: str, session):
    """Scrape reviews from the reviews page"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://www.booking.com/',
    }
    
    try:
        # First get the main hotel page
        print(f"Fetching hotel page: {base_url}")
        async with session.get(base_url, headers=headers) as response:
            if response.status != 200:
                print(f"Error: Got status code {response.status}")
                return []
                
            html = await response.text()
            
            # Parse the URL to get country code and hotel identifier
            parsed_url = urlparse(base_url)
            path_parts = parsed_url.path.split('/')
            
            # Extract country code and hotel identifier
            country_code = path_parts[2] if len(path_parts) > 2 else None
            hotel_identifier = path_parts[-1].replace('.html', '') if path_parts[-1].endswith('.html') else None
            
            if not country_code or not hotel_identifier:
                print("Could not extract country code or hotel identifier from URL")
                return []
                
            print(f"Country code: {country_code}")
            print(f"Hotel identifier: {hotel_identifier}")
            
            # Try to find the reviews link in the page
            sel = Selector(text=html)
            reviews_link = sel.css('a[data-testid="reviews-link"]::attr(href)').get()
            
            if reviews_link:
                # If we found a direct reviews link, use it
                reviews_url = urljoin(base_url, reviews_link)
            else:
                # Construct the reviews URL using the standard format
                reviews_url = f"https://www.booking.com/reviews/{country_code}/hotel/{hotel_identifier}.html"
            
            print(f"Fetching reviews from: {reviews_url}")
            
            # Fetch the reviews page
            async with session.get(reviews_url, headers=headers) as response:
                if response.status != 200:
                    print(f"Error: Got status code {response.status}")
                    # Try alternate URL format if first attempt fails
                    alternate_url = f"https://www.booking.com/reviewlist.html?cc1={country_code};pagename={hotel_identifier}"
                    print(f"Trying alternate URL: {alternate_url}")
                    async with session.get(alternate_url, headers=headers) as alt_response:
                        if alt_response.status != 200:
                            print("Both URL formats failed")
                            return []
                        html = await alt_response.text()
                else:
                    html = await response.text()
                
                # Save the HTML for inspection
                with open('reviews_page.html', 'w', encoding='utf-8') as f:
                    f.write(html)
                print("Saved reviews page HTML to reviews_page.html")
                
                # Extract reviews
                reviews = await extract_reviews(html)
                
                # If no reviews found with first method, try parsing with alternate method
                if not reviews:
                    reviews = await parse_reviews_from_main_page(html)
                
                # Save reviews to JSON file
                with open('reviews.json', 'w', encoding='utf-8') as f:
                    json.dump(reviews, f, indent=2, ensure_ascii=False)
                print(f"Saved {len(reviews)} reviews to reviews.json")
                
                return reviews
            
    except Exception as e:
        print(f"Error scraping reviews: {str(e)}")
        return []

async def main():
    # Get hotel URL from user input
    print("Please enter the Booking.com hotel URL:")
    hotel_url = input().strip()
    
    if not hotel_url:
        print("No URL provided. Using default test URL...")
        hotel_url = "https://www.booking.com/hotel/pk/pearl-continental.html"
    
    print(f"\nStarting review scraping for: {hotel_url}")
    
    async with aiohttp.ClientSession() as session:
        reviews = await scrape_hotel_reviews(hotel_url, session)
        
        if reviews:
            print(f"\nFound {len(reviews)} reviews!")
            print("\nFirst review as example:")
            print(json.dumps(reviews[0], indent=2, ensure_ascii=False))
            print(f"\nAll reviews have been saved to 'reviews.json'")
        else:
            print("No reviews found")

if __name__ == "__main__":
    asyncio.run(main()) 