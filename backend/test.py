import asyncio
import json
import re
from urllib.parse import urljoin
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.extraction_strategy import JsonXPathExtractionStrategy
from typing import List, Dict, Any


# --- Data Cleaning Helper Functions ---

def clean_rating(raw_rating: str) -> Dict[str, Any]:
    """Parses the raw rating text to extract the score and number of reviews."""
    if not raw_rating:
        return {"score": None, "reviews": None}
    score_match = re.search(r'([\d.]+)', raw_rating)
    reviews_match = re.search(r'(\d[\d,]*)\s+reviews', raw_rating)
    return {
        "score": float(score_match.group(1)) if score_match else None,
        "reviews": int(reviews_match.group(1).replace(',', '')) if reviews_match else None
    }


def extract_star_count(stars_html: str) -> int:
    """Counts the number of star icons from the raw HTML."""
    if not stars_html:
        return 0
    return stars_html.count("<span")


def process_hotel_data(hotel: Dict[str, Any], base_url: str) -> Dict[str, Any]:
    """Cleans and structures the raw scraped data for a single hotel."""
    url = hotel.get("url", "")
    return {
        "name": hotel.get("name"),
        "price": hotel.get("price"),
        "rating": clean_rating(hotel.get("rating", "")),
        "stars": extract_star_count(hotel.get("stars", "")),
        "location": hotel.get("location"),
        "url": urljoin(base_url, url) if url else None,
        "distance": hotel.get("distance"),
    }


# --- Main Scraping Function ---

async def scrape_booking_hotels():
    """
    Main function to scrape a fixed Booking.com URL.
    """
    # The fixed URL you provided
    SEARCH_URL = "https://www.booking.com/searchresults.en-gb.html?label=gen173nr-1FCAQoggJCE3NlYXJjaF9rdWFsYSBsdW1wdXJIM1gEaLUBiAEBmAEJuAEXyAEM2AEB6AEB-AEDiAIBqAIDuAKakYzCBsACAdICJGQzOWY2YmFiLTk5MjMtNDk4Yy1hMzQ4LWU1NjBjMjg3N2NjYtgCBeACAQ&aid=304142&ss=Kuala+Lumpur&ssne=Kuala+Lumpur&ssne_untouched=Kuala+Lumpur&lang=en-gb&src=searchresults&dest_id=-2403010&dest_type=city&checkin=2025-06-07&checkout=2025-06-08&group_adults=1&no_rooms=1&group_children=0&nflt=distance%3D3000%3Bht_id%3D204"
    BASE_URL = "https://www.booking.com"

    # XPath schema to define what data to extract from each hotel card
    schema = {
        "name": "Booking Hotel Listings",
        "baseSelector": "//div[@data-testid='property-card']",
        "fields": [
            {"name": "name", "selector": ".//div[@data-testid='title']", "type": "text"},
            {"name": "price", "selector": ".//span[@data-testid='price-and-discounted-price']", "type": "text"},
            {"name": "rating", "selector": ".//div[@data-testid='review-score']", "type": "text"},
            {"name": "location", "selector": ".//span[@data-testid='address']", "type": "text"},
            {"name": "distance", "selector": ".//span[@data-testid='distance']", "type": "text"},
            {"name": "url", "selector": ".//a[@data-testid='title-link']", "type": "attribute", "attribute": "href"},
            {"name": "stars", "selector": ".//div[@data-testid='rating-stars' or @data-testid='rating-squares']",
             "type": "html"},
        ]
    }

    # This JavaScript function will be polled by the crawler. It scrolls the page
    # and returns 'true' only when the page height stops increasing, ensuring
    # all content is loaded before scraping.
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
        extraction_strategy=JsonXPathExtractionStrategy(schema, verbose=False),
        wait_for=f"js:{scroll_and_wait_script}"
    )

    print(f"Navigating to Booking.com for Kuala Lumpur...")
    print("🚀 Scrolling page to load all hotel results. This may take a moment...")

    # Initialize and run the crawler
    async with AsyncWebCrawler(headless=True, timeout=180000) as crawler:
        result = await crawler.arun(url=SEARCH_URL, config=config)

    # --- Process and Print Results ---
    if not result.success or not result.extracted_content:
        print("\n❌ Crawl failed or no content was extracted:", result.error_message)
        return

    try:
        raw_data = json.loads(result.extracted_content)
        if not raw_data:
            print("\n⚠️ No hotel data was found on the page after scrolling.")
            return
    except json.JSONDecodeError:
        print("\n❌ Failed to parse extracted content as JSON.")
        return

    # Clean the raw data
    cleaned_hotels = [process_hotel_data(hotel, BASE_URL) for hotel in raw_data]

    print(f"\n✅ Scraping complete. Found {len(cleaned_hotels)} hotels.")

    # --- MODIFICATION: Save output to a JSON file ---
    output_filename = "booking_results.json"
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(cleaned_hotels, f, ensure_ascii=False, indent=2)

    print(f"💾 Results have been saved to {output_filename}")


# --- Entry point to run the script ---
if __name__ == "__main__":
    # To run this script, save it as a .py file (e.g., scrap.py)
    # and execute it from your terminal: python scrap.py
    asyncio.run(scrape_booking_hotels())
