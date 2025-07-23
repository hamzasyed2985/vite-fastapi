import asyncio
import json
import re
from urllib.parse import urlencode, urljoin, parse_qs, urlparse
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.extraction_strategy import JsonXPathExtractionStrategy
import aiohttp
from parsel import Selector
from typing import List, Dict
import math


class ModernBookingScraper:
    def __init__(self):
        self.base_url = "https://www.booking.com"
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    def build_search_url(self, location, check_in, check_out, adults, filters, currency):
        query_params = {
            "ss": location,
            "checkin": check_in,
            "checkout": check_out,
            "group_adults": adults,
            "selected_currency": currency,
            "order": "popularity",
            "nflt": "ht_id=204"
        }

        # Handle additional filters
        if filters:
            # Convert distance filter to the correct format
            formatted_filters = []
            for filter_item in filters:
                if filter_item.startswith('distance='):
                    # Convert distance to the format expected by Booking.com
                    distance_meters = int(filter_item.split('=')[1])
                    formatted_filters.append(f"distance={distance_meters}")
                else:
                    formatted_filters.append(filter_item)

            # Add all filters to nflt parameter, combining with existing ht_id filter
            if formatted_filters:
                query_params["nflt"] = ";".join([query_params["nflt"], *formatted_filters])

        return f"{self.base_url}/searchresults.html?{urlencode(query_params)}"

    async def check_no_properties_found(self, url):
        """
        Check if the search results page contains a 'No Properties Found' message
        specifically within an <h1> tag.
        Returns True if no properties found (based on H1 content), False otherwise.
        """
        print("🔍 Checking if properties are available based on H1 content...")

        config = CrawlerRunConfig(
            # Just wait for the page to load initially, no need for scrolling
            wait_for="js:() => document.readyState === 'complete'"
        )


        async with AsyncWebCrawler(headless=True, timeout=30000) as crawler:
            result = await crawler.arun(url=url, config=config)

            if not result.success:
                print(f"❌ Failed to check page: {result.error_message}")
                return False  # Assume properties exist if we can't check

            html_content = result.html

            # Define various "no results" indicators
            no_results_indicators = [
                "No Properties Found",
                "No properties found",
                "no properties found",
                "We couldn't find any properties",
                "No results found",
                ": 0 properties found",
                "Sorry, no properties are available",
                ": No properties found",
                ": No Properties Found",
                "- No properties found",
                "- No Properties Found",": No exact matches"
            ]

            # Check in h1 tags specifically
            h1_pattern = r'<h1[^>]*>(.*?)</h1>'
            h1_matches = re.findall(h1_pattern, html_content, re.IGNORECASE | re.DOTALL)

            for h1_content in h1_matches:
                # Remove HTML tags from h1 content and strip whitespace
                clean_h1 = re.sub(r'<[^>]+>', '', h1_content).strip()
                print(f"📝 Found H1 content: '{clean_h1}'")

                # Check if any of the no_results_indicators are a substring of the clean H1 content
                for indicator in no_results_indicators:
                    if indicator.lower() in clean_h1.lower():
                        print(f"🚫 No properties found! H1 content matches indicator: '{indicator}'")
                        return True

            print("✅ Properties found or no 'no properties found' indicator in H1. Proceeding with scraping...")
            return False

    def get_xpath_schema(self):
        return {
            "name": "Booking Hotel Listings",
            "baseSelector": "//div[@data-testid='property-card']",
            "fields": [
                {
                    "name": "name",
                    "selector": ".//div[@data-testid='title']",
                    "type": "text"
                },
                {
                    "name": "price",
                    "selector": ".//span[@data-testid='price-and-discounted-price']",
                    "type": "text"
                },
                {
                    "name": "rating",
                    "selector": ".//div[@data-testid='review-score']",
                    "type": "text"
                },
                {
                    "name": "location",
                    "selector": ".//span[@data-testid='address']",
                    "type": "text"
                },
                {
                    "name": "distance",
                    "selector": ".//span[@data-testid='distance']",
                    "type": "text"
                },
                {
                    "name": "url",
                    "selector": ".//a[@data-testid='title-link']",
                    "type": "attribute",
                    "attribute": "href"
                },
                {
                    "name": "availability_message",
                    "selector": ".//div[contains(@class, 'b7d3eb6716')]",
                    "type": "text"
                },
                {
                    "name": "stars",
                    "selector": ".//div[@data-testid='rating-stars' or @data-testid='rating-squares']",
                    "type": "html"
                },
                {
                    "name": "coordinates",
                    "selector": ".//div[contains(@class, 'f909661b82') and @data-testid='MapEntryPointDesktop-wrapper']",
                    "type": "attribute",
                    "attribute": "data-atlas-latlng"
                }
            ]
        }

    def clean_rating(self, raw_rating):
        score_match = re.search(r'Scored\s+([\d.]+)', raw_rating)
        reviews_match = re.search(r'(\d[\d,]*)\s+reviews', raw_rating)

        return {
            "score": float(score_match.group(1)) if score_match else None,
            "reviews": int(reviews_match.group(1).replace(',', '')) if reviews_match else None
        }

    def extract_star_count(self, stars_html):
        if not stars_html:
            return None
        # Count span elements and divide by 2 since there are 2 spans per star
        span_count = stars_html.count("<span")
        return span_count // 2 if span_count > 0 else None

    def extract_hotel_id(self, url):
        if not url:
            return None
        parsed = urlparse(url)
        path_parts = parsed.path.split('/')

        # Try to find the hotel ID in the URL path
        for part in path_parts:
            if part.startswith('hotel'):
                return part
            # Some URLs have the hotel ID in a different format
            if part.startswith('ac-'):
                return part
            # Try to find numeric IDs
            if part.isdigit():
                return part

        # If not found in path, try query parameters
        query_params = parse_qs(parsed.query)
        for param in ['hotel_id', 'aid', 'id']:
            if param in query_params:
                return query_params[param][0]

        # Try to extract from the hostname (some URLs have the hotel ID there)
        hostname_parts = parsed.hostname.split('.')
        for part in hostname_parts:
            if part.startswith('hotel') and len(part) > 5:  # avoid just 'hotel'
                return part

        return None

    async def get_hotel_reviews(self, hotel_url: str, limit: int = 5) -> list:
        """Fetch reviews for a specific hotel using improved scraping logic"""
        if not self.session:
            self.session = aiohttp.ClientSession()

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.booking.com/',
        }

        try:
            # First get the main hotel page
            async with self.session.get(hotel_url, headers=headers) as response:
                if response.status != 200:
                    return []

                html = await response.text()

                # Parse the URL to get country code and hotel identifier
                parsed_url = urlparse(hotel_url)
                path_parts = parsed_url.path.split('/')

                # Extract country code and hotel identifier
                country_code = path_parts[2] if len(path_parts) > 2 else None
                hotel_identifier = path_parts[-1].replace('.html', '') if path_parts[-1].endswith('.html') else None

                if not country_code or not hotel_identifier:
                    return []

                # Try to find the reviews link in the page
                sel = Selector(text=html)
                reviews_link = sel.css('a[data-testid="reviews-link"]::attr(href)').get()

                if reviews_link:
                    # If we found a direct reviews link, use it
                    reviews_url = urljoin(hotel_url, reviews_link)
                else:
                    # Construct the reviews URL using the standard format
                    reviews_url = f"{self.base_url}/reviews/{country_code}/hotel/{hotel_identifier}.html"

                # Fetch the reviews page
                async with self.session.get(reviews_url, headers=headers) as response:
                    if response.status != 200:
                        # Try alternate URL format if first attempt fails
                        alternate_url = f"{self.base_url}/reviewlist.html?cc1={country_code};pagename={hotel_identifier}"
                        async with self.session.get(alternate_url, headers=headers) as alt_response:
                            if alt_response.status != 200:
                                return []
                            html = await alt_response.text()
                    else:
                        html = await response.text()

                    # Extract reviews using both methods
                    reviews = await self.extract_reviews(html)

                    # If no reviews found with first method, try alternate parsing
                    if not reviews:
                        reviews = await self.parse_reviews_from_main_page(html)

                    # Limit the number of reviews
                    reviews = reviews[:limit]

                    return reviews

        except Exception as e:
            return []

    async def parse_reviews_from_main_page(self, html: str) -> List[dict]:
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

            review_data = {
                "reviewer_name": reviewer,
                "reviewer_country": country,
                "review_score": score,
                "review_title": title,
                "review_date": date,
                "review_positive": pos_text,
                "review_negative": neg_text,
                "room_type": room_type
            }

            # Only add reviews that have some content
            if any(review_data.values()):
                parsed.append(review_data)

        return parsed

    async def extract_reviews(self, html: str) -> List[Dict]:
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

            # Clean up the positive and negative review bodies
            review_data["review_positive"] = ' '.join(
                [text.strip() for text in review_data["review_positive"] if text.strip()])
            review_data["review_negative"] = ' '.join(
                [text.strip() for text in review_data["review_negative"] if text.strip()])

            # Only add reviews that have some content
            if any(review_data.values()):
                reviews.append(review_data)

        return reviews

    def extract_coordinates(self, coords_str):
        """Extract and validate coordinates from the data-atlas-latlng attribute"""
        if not coords_str:
            return None
        try:
            # Split the coordinates string and convert to float
            lat, lng = map(float, coords_str.split(','))

            # Basic validation of coordinates
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                return {"latitude": lat, "longitude": lng}
            return None
        except (ValueError, TypeError):
            return None

    def calculate_distance(self, coords1, coords2):
        """Calculate distance between two coordinates in kilometers using Haversine formula"""
        if not coords1 or not coords2:
            return None

        from math import radians, sin, cos, sqrt, atan2

        lat1, lon1 = coords1["latitude"], coords1["longitude"]
        lat2, lon2 = coords2["latitude"], coords2["longitude"]

        R = 6371  # Earth's radius in kilometers

        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        distance = R * c

        return round(distance, 2)

    async def get_hotel_coordinates(self, hotel_url: str) -> str:
        """Fetch raw coordinates string from hotel's detail page"""
        if not self.session:
            self.session = aiohttp.ClientSession()

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.booking.com/',
        }

        try:
            async with self.session.get(hotel_url, headers=headers) as response:
                if response.status != 200:
                    print(f"Failed to fetch page: {response.status}")
                    return None

                html = await response.text()
                print("\nSearching for coordinates in HTML...")

                # Simple regex to find data-atlas-latlng content
                import re
                matches = re.findall(r'data-atlas-latlng="([^"]+)"', html)
                if matches:
                    print(f"Found raw coordinates: {matches[0]}")
                    return matches[0]
                else:
                    print("No coordinates found in the page")
                    return None

        except Exception as e:
            print(f"Error: {str(e)}")
            return None

    async def search_hotels(self, location, check_in, check_out, adults=2, filters=None, currency="USD",
                            include_reviews=False, review_limit=5):
        search_url = self.build_search_url(location, check_in, check_out, adults, filters, currency)

        print("\nGenerated Search URL:", search_url)
        print("Filters being applied:", filters)

        # First check if any properties are found
        no_properties = await self.check_no_properties_found(search_url)

        if no_properties:
            print("🛑 No properties found for the given criteria. Stopping scraping.")
            return []

        # If properties exist, proceed with normal scraping
        schema = self.get_xpath_schema()

        # Auto-scroll JavaScript function from test.py
        scroll_and_wait_script = """
            () => {
                if (typeof window.lastHeight === 'undefined') {
                    window.lastHeight = 0;
                    window.retries = 5;
                }
                const currentHeight = document.body.scrollHeight;
                window.scrollTo(0, currentHeight);
                if (currentHeight === window.lastHeight) {
                    window.retries--;
                    if (window.retries <= 0) {
                        return true;
                    }
                } else {
                    window.retries = 5;
                }
                window.lastHeight = currentHeight;
                return false;
            }
        """

        config = CrawlerRunConfig(
            extraction_strategy=JsonXPathExtractionStrategy(schema, verbose=True),
            wait_for="css:body",  # Wait for the body tag to be loaded
            js_code=scroll_and_wait_script  # Your scrolling script will execute after wait_for
        )
        print("🚀 Scrolling page to load all hotel results. This may take a moment...")

        async with AsyncWebCrawler(headless=True, timeout=180000) as crawler:
            result = await crawler.arun(url=search_url, config=config)

            if not result.success:
                print("Crawl failed:", result.error_message)
                return []

            raw_data = json.loads(result.extracted_content)

            # Process hotels in parallel
            async def process_hotel(hotel):
                url = hotel.get("url", "")
                if url:
                    full_url = urljoin(self.base_url, url)
                    print(f"\nHotel: {hotel.get('name')}")
                    print(f"URL: {full_url}")
                    raw_coords = await self.get_hotel_coordinates(full_url)
                    coords = self.extract_coordinates(raw_coords) if raw_coords else None
                else:
                    coords = None

                cleaned_hotel = {
                    "id": self.extract_hotel_id(url),
                    "name": hotel.get("name"),
                    "price": hotel.get("price"),
                    "rating": self.clean_rating(hotel.get("rating", "")),
                    "stars": self.extract_star_count(hotel.get("stars", "")),
                    "location": hotel.get("location"),
                    "url": urljoin(self.base_url, url),
                    "availability": hotel.get("availability_message") or None,
                    "coordinates": coords,
                    # "distance_from_center": hotel.get("distance"),
                }

                # Fetch reviews if requested
                if include_reviews:
                    cleaned_hotel["reviews"] = await self.get_hotel_reviews(cleaned_hotel["url"], review_limit)

                return cleaned_hotel

            # Process all hotels in parallel
            cleaned_data = await asyncio.gather(*[process_hotel(hotel) for hotel in raw_data], return_exceptions=True)

            # Filter out any failed requests
            cleaned_data = [data for data in cleaned_data if not isinstance(data, Exception)]

            print(f"\n✅ Scraping complete. Found {len(cleaned_data)} hotels.")
            for hotel in cleaned_data:
                print(f"- {hotel['name']} (Rating: {hotel.get('rating', {}).get('score', 'N/A')})")

            # Find center coordinates (using first hotel with valid coordinates)
            center_coords = None
            for hotel in cleaned_data:
                if hotel["coordinates"]:
                    center_coords = hotel["coordinates"]
                    print(f"\nUsing center coordinates: {center_coords}")
                    break

            # Calculate distances from center but don't sort by it
            if center_coords:
                for hotel in cleaned_data:
                    if hotel["coordinates"]:
                        hotel["distance_from_center"] = self.calculate_distance(center_coords, hotel["coordinates"])
                        print(f"\nHotel: {hotel['name']}")
                        print(f"Distance from center: {hotel['distance_from_center']} km")

            # Maintain the original order from Booking.com (price-based)
            return cleaned_data


async def main():
    scraper = ModernBookingScraper()

    filters = [
        "class=4",  # 4-star hotels
        # "mealplan=1",  # Uncomment if you want "breakfast included"
        "distance=3000"  # within 3 km
    ]

    hotels = await scraper.search_hotels(
        location="Makkah",
        check_in="2025-06-01",
        check_out="2025-06-05",
        adults=2,
        filters=filters
    )

    if hotels:
        print("\nFiltered hotels:")
        print(json.dumps(hotels, indent=2, ensure_ascii=False))
    else:
        print("\nNo hotels found matching the criteria.")


if __name__ == "__main__":
    asyncio.run(main())