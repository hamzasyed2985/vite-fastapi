from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.extraction_strategy import JsonXPathExtractionStrategy
import json
import asyncio

def get_review_xpath_schema():
    return {
        "name": "Booking Hotel Reviews",
        "baseSelector": "//div[@data-testid='review-card']",
        "fields": [
            {
                "name": "review_date",
                "selector": './/span[@data-testid="review-date"]',
                "type": "text"
            },
            {
                "name": "review_title",
                "selector": './/h4[@data-testid="review-title"]',
                "type": "text"
            },
            {
                "name": "positive_review",
                "selector": './/div[@data-testid="review-positive-text"]',
                "type": "text"
            },
            {
                "name": "negative_review",
                "selector": './/div[@data-testid="review-negative-text"]',
                "type": "text"
            }
        ]
    }

async def extract_reviews(hotel_url):
    session_id = "reviews-session"
    schema = get_review_xpath_schema()

    print("[INFO] Starting crawler session")

    async with AsyncWebCrawler() as crawler:
        print("[INFO] Step 1: Loading hotel page:", hotel_url)
        await crawler.arun(
            url=hotel_url,
            config=CrawlerRunConfig(
                wait_for='css:button[data-testid="fr-read-all-reviews"]',
                session_id=session_id
            )
        )
        print("[INFO] Step 1 complete: Hotel page loaded.")

        # Step 2: Click "Read all reviews" and extract review section
        print("[INFO] Step 2: Clicking 'Read all reviews' button...")
        click_and_wait_config = CrawlerRunConfig(
            js_code=[
                "window.scrollTo(0, document.body.scrollHeight);",
                "document.querySelector('button[data-testid=\"fr-read-all-reviews\"]')?.click();"
            ],
            wait_for="""
                js:() => {
                    return document.querySelectorAll('[data-testid="review-card"]').length > 0;
                }
            """,
            js_only=True,
            session_id=session_id,
            extraction_strategy=JsonXPathExtractionStrategy(schema)
        )

        print("[INFO] Step 2: Waiting for review section to appear...")
        result = await crawler.arun(
            url=hotel_url,
            config=click_and_wait_config
        )
        with open("debug_reviews.html", "w", encoding="utf-8") as f:
            f.write(result.raw_html or "")
        print("[DEBUG] Saved raw HTML to debug_reviews.html")


        if not result.success:
            print(f"[WARN] Failed to extract reviews from {hotel_url}")
            print("[DEBUG] Result details:", result)
            return []

        print("[INFO] Step 3: Reviews loaded. Attempting to parse extracted content...")

        try:
            raw_reviews = json.loads(result.extracted_content)
            print(f"[INFO] Step 4: Parsed {len(raw_reviews)} raw review blocks.")

            final_reviews = [
                {
                    "review_date": r.get("review_date"),
                    "review_title": r.get("review_title"),
                    "positive_review": r.get("positive_review"),
                    "negative_review": r.get("negative_review"),
                }
                for r in raw_reviews
                if any(r.get(key) for key in ["positive_review", "negative_review"])
            ]

            print(f"[INFO] Step 5: Filtered down to {len(final_reviews)} reviews with content.")
            return final_reviews

        except Exception as e:
            print("[ERROR] Parsing reviews failed:", e)
            print("[DEBUG] Raw extracted content:", result.extracted_content)
            return []

# For testing
if __name__ == "__main__":
    hotel_url = "https://www.booking.com/hotel/sa/novotel-residences-makkah.html"
    print("[INFO] Starting review extraction for:", hotel_url)
    reviews = asyncio.run(extract_reviews(hotel_url))
    print("[INFO] Extraction completed. Final reviews:")
    print(json.dumps(reviews, indent=2, ensure_ascii=False))


