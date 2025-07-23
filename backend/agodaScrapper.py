import time
import random
import json
import asyncio
from playwright.async_api import async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
import os
from tqdm import tqdm
from datetime import datetime
from typing import Optional, List, Dict, Any

# Inline user agents
USER_AGENTS = {
    "chromium": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
    ],
    "firefox": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7; rv:131.0) Gecko/20100101 Firefox/131.0"
    ]
}


async def random_delay(min_sec=2, max_sec=4):
    """Sleep for a random duration between min_sec and max_sec."""
    await asyncio.sleep(random.uniform(min_sec, max_sec))


async def simulate_human_mouse(page):
    """Simulate random human-like mouse movements."""
    width, height = page.viewport_size['width'], page.viewport_size['height']
    for _ in range(random.randint(3, 4)):  # Perform random moves
        x, y = random.randint(0, width), random.randint(0, height)
        await page.mouse.move(x, y, steps=random.randint(5, 10))
        await asyncio.sleep(random.uniform(0.2, 0.8))  # Random pauses


def validate_date_format(date_string: str) -> bool:
    """
    Validates if the date string is in 'YYYY-MM-DD' format.
    """
    try:
        datetime.strptime(date_string, '%Y-%m-%d')
        return True
    except ValueError:
        return False


async def visit_agoda_homepage(p):
    """
    Initializes the browser, context, and page. Navigates to the Agoda homepage
    with human-like behavior. Returns the tuple (page, context, browser) for further actions.
    """
    browser_name = "chromium"
    print(f"Using browser: {browser_name}")
    user_agent = random.choice(USER_AGENTS[browser_name])
    print(f"Using user agent: {user_agent}")
    browser = await p.chromium.launch(
        headless=False,
        args=['--disable-blink-features=AutomationControlled']
    )
    context = await browser.new_context(
        user_agent=user_agent,
        viewport={'width': 1280, 'height': 800},
        locale='en-US',
        screen={'width': 1920, 'height': 1080}
    )
    await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    page = await context.new_page()
    await page.goto("https://www.agoda.com/", wait_until="networkidle")
    await random_delay(1, 3)
    await page.evaluate("window.scrollBy(0, window.innerHeight/8)")
    await random_delay(1, 2)
    return page, context, browser


async def search_agoda_homepage(page, location: str, check_in_date: str, check_out_date: str, adults: int, star_rating: Optional[int] = None, currency: Optional[str] = None):
    """
    Performs the homepage search by entering the location, selecting check-in and check-out dates,
    setting number of adults, and clicking the search button.
    Now also supports filtering by hotel star rating.
    """
    try:
        # Enter location
        await page.type("xpath=//*[@id='textInput']", location, delay=random.randint(50, 150))
        await random_delay(1, 2)
        print(f"Entered location: {location}")

        # Click away to dismiss suggestions dropdown
        await page.mouse.click(10, 10)
        await random_delay(0.5, 1)
        print("Clicked to dismiss suggestions dropdown")

        # Select check-in date
        await page.click("xpath=//*[@id='check-in-box']")
        await random_delay(1, 2)
        print(f"Clicked check-in box, selecting date: {check_in_date}")

        await page.click(f"xpath=//span[@data-selenium-date='{check_in_date}']")
        await random_delay(1, 2)
        print(f"Selected check-in date: {check_in_date}")

        # Select check-out date
        await page.click(f"xpath=//span[@data-selenium-date='{check_out_date}']")
        await random_delay(1, 2)
        print(f"Selected check-out date: {check_out_date}")

        # Click away to dismiss date picker
        await page.mouse.click(10, 10)
        await random_delay(0.5, 1)
        print("Clicked to dismiss date picker")

        # Set number of adults if different from default (2)
        if adults != 2:
            try:
                # Click on occupancy box
                await page.click("xpath=//*[@id='occupancy-box']")
                await random_delay(1, 2)
                print("Clicked occupancy box")

                # Reset adults to 1 first (click minus button once if current is 2)
                adults_minus_btn = "xpath=//button[@data-selenium='adults-minus-btn']"
                if await page.is_visible(adults_minus_btn):
                    await page.click(adults_minus_btn)
                    await random_delay(0.5, 1)

                # Add adults to reach desired number
                adults_plus_btn = "xpath=//button[@data-selenium='adults-plus-btn']"
                for _ in range(adults - 1):  # -1 because we start with 1 adult
                    if await page.is_visible(adults_plus_btn):
                        await page.click(adults_plus_btn)
                        await random_delay(0.5, 1)

                print(f"Set number of adults to: {adults}")

                # Close occupancy dropdown
                await page.mouse.click(10, 10)
                await random_delay(0.5, 1)
            except Exception as e:
                print(f"Warning: Could not set number of adults: {e}")

        # Simulate human mouse movement and click search
        await simulate_human_mouse(page)
        await page.click("xpath=//*[@id='Tabs-Container']/button//span[contains(text(),'SEARCH')]")
        await random_delay(2, 3)
        print("Clicked search button...")

        # Wait for the results to load with extended timeout and multiple approaches
        print("Waiting for results to load...")
        await random_delay(5, 7)  # Increased delay after search
        await page.wait_for_load_state('networkidle', timeout=30000)

        # Print the current URL for debugging
        current_url = page.url
        print(f"Current URL after initial search: {current_url}")

        # Check if we were redirected to activities page and redirect back to hotels
        if "/activities/" in current_url:
            print("Detected redirect to activities page, redirecting to hotels...")
            # Extract city ID from the activities URL
            import re
            city_id_match = re.search(r'cityId=(\d+)', current_url)
            if city_id_match:
                city_id = city_id_match.group(1)
                # Construct the hotels search URL
                hotels_url = f"https://www.agoda.com/search?city={city_id}&checkIn={check_in_date}&checkOut={check_out_date}&rooms=1&adults={adults}&cid=1908612"
                print(f"Redirecting to hotels URL: {hotels_url}")
                await page.goto(hotels_url, wait_until="networkidle")
                await random_delay(3, 5)
                current_url = page.url  # Update URL after redirect
                print(f"New URL after redirect: {current_url}")
            else:
                print("Could not extract city ID from activities URL, trying alternative approach...")
                # Try to click on "Hotels" tab if it exists
                hotels_tab_selectors = [
                    "//a[contains(text(), 'Hotels')]",
                    "//button[contains(text(), 'Hotels')]",
                    "//span[contains(text(), 'Hotels')]",
                    "[data-selenium='hotels-tab']",
                    ".tab-hotels"
                ]

                hotels_tab_found = False
                for selector in hotels_tab_selectors:
                    try:
                        if await page.is_visible(selector, timeout=2000):
                            await page.click(selector)
                            await random_delay(3, 5)
                            await page.wait_for_load_state('networkidle')
                            current_url = page.url  # Update URL after clicking tab
                            print(f"Clicked hotels tab, new URL: {current_url}")
                            hotels_tab_found = True
                            break
                    except Exception as e:
                        continue

                if not hotels_tab_found:
                    print("Could not find hotels tab, will attempt to search again with more specific location...")
                    # Go back to homepage and try with "Hotels in Kuala Lumpur" format
                    await page.goto("https://www.agoda.com/", wait_until="networkidle")
                    await random_delay(2, 3)

                    # Clear and re-enter location with "Hotels in" prefix
                    location_with_hotels = f"Hotels in {location}"
                    await page.fill("xpath=//*[@id='textInput']", "")
                    await page.type("xpath=//*[@id='textInput']", location_with_hotels, delay=random.randint(50, 150))
                    await random_delay(1, 2)
                    print(f"Re-entered location as: {location_with_hotels}")

                    # Click away to dismiss suggestions dropdown
                    await page.mouse.click(10, 10)
                    await random_delay(0.5, 1)

                    # Re-select dates
                    await page.click("xpath=//*[@id='check-in-box']")
                    await random_delay(1, 2)
                    await page.click(f"xpath=//span[@data-selenium-date='{check_in_date}']")
                    await random_delay(1, 2)
                    await page.click(f"xpath=//span[@data-selenium-date='{check_out_date}']")
                    await random_delay(1, 2)
                    await page.mouse.click(10, 10)
                    await random_delay(0.5, 1)

                    # Click search again
                    await page.click("xpath=//*[@id='Tabs-Container']/button//span[contains(text(),'SEARCH')]")
                    await random_delay(5, 7)
                    await page.wait_for_load_state('networkidle', timeout=30000)
                    current_url = page.url
                    print(f"Final URL after re-search: {current_url}")

        # --- NEW LOGIC: Add hotelAccom=34 and refresh ---
        print("Checking URL for 'hotelAccom=34' parameter...")
        if "hotelAccom=34" not in current_url:
            new_url = current_url
            if "?" in current_url:
                new_url += "&hotelAccom=34"
            else:
                new_url += "?hotelAccom=34"

            print(f"Appending 'hotelAccom=34' and navigating to: {new_url}")
            await page.goto(new_url, wait_until="networkidle")
            await random_delay(3, 5)  # Wait for the page to reload
            current_url = page.url  # Get the updated URL
            print(f"URL after refresh with parameter: {current_url}")
        else:
            print("'hotelAccom=34' already present in the URL. No refresh needed.")

        # --- NEW LOGIC: Add hotelStarRating if star_rating is provided ---
        if star_rating:
            if "hotelStarRating" not in current_url:
                if "?" in current_url:
                    new_url = f"{current_url}&hotelStarRating={star_rating}"
                else:
                    new_url = f"{current_url}?hotelStarRating={star_rating}"
                print(f"Adding hotelStarRating to URL: {new_url}")
                await page.goto(new_url, wait_until="networkidle")
                await random_delay(2, 3)
                current_url = page.url  # Update after reload
            else:
                print(f"hotelStarRating already present in the URL. No update needed.")

        # --- NEW LOGIC: Set currency via UI interaction ---
        try:
            currency_code = currency if currency else "MYR"
            print(f"Attempting to set currency to {currency_code} via UI...")
            await page.click("[data-element-name='currency-container-selected-currency']")
            await random_delay(1, 2)
            await page.click(f"[data-element-name='currency-popup-menu-item'][data-value='{currency_code}']")
            await random_delay(2, 3)
            print(f"Currency set to {currency_code} via UI.")
        except Exception as e:
            print(f"Could not set currency to {currency_code} via UI: {e}")

      
      
        print("Page loaded, proceeding with extraction...")
    except PlaywrightTimeoutError as e:
        print(f"Timeout during search: {e}")
        raise


async def wait_for_results_page(page, timeout=30000):
    """
    Waits for the search results page to load using multiple strategies.
    Returns True if successful, False otherwise.
    """
    print("Waiting for search results page to load...")

    # Multiple selectors to try for the results container
    result_selectors = [
        "//div[@id='contentContainer']",
        "//div[contains(@class, 'SearchResultsContainer')]",
        "//ol[@class='hotel-list-container']",
        "//div[contains(@class, 'property-card')]",
        "//div[@data-selenium='hotel-item']",
        "//li[@data-selenium='hotel-item']",
        "//div[contains(@class, 'PropertyCard')]",
        "#contentContainer",
        "[data-selenium='hotel-item']"
    ]

    # Try each selector with a shorter individual timeout
    individual_timeout = timeout // len(result_selectors)

    for i, selector in enumerate(result_selectors):
        try:
            print(f"Trying selector {i + 1}/{len(result_selectors)}: {selector}")
            await page.wait_for_selector(selector, timeout=individual_timeout)
            print(f"✓ Found results container with selector: {selector}")
            return True
        except PlaywrightTimeoutError:
            print(f"✗ Selector {selector} timed out")
            continue

    # If none of the specific selectors work, check if we're on an error page
    try:
        # Check for "no results" message
        no_results_selectors = [
            "//*[contains(text(), \"We couldn't find any results\")]",
            "//*[contains(text(), 'No results found')]",
            "//*[contains(text(), 'no properties found')]"
        ]

        for selector in no_results_selectors:
            if await page.is_visible(selector, timeout=2000):
                print("Found 'no results' message on page")
                return True

    except Exception as e:
        print(f"Error checking for no results message: {e}")

    # Last resort: check if page has loaded at all
    try:
        await page.wait_for_load_state('domcontentloaded')
        print("Page DOM loaded, but couldn't find expected elements")
        return False
    except Exception as e:
        print(f"Page failed to load completely: {e}")
        return False


async def extract_hotel_info(item):
    """
    Extracts hotel information from a single hotel item element.
    Only returns hotel data if price information is available.
    """
    try:
        # Multiple selectors for hotel name
        hotel_name_selectors = [
            "a[data-selenium='hotel-name'] span",
            "h3[data-selenium='hotel-name']",
            "a[data-selenium='hotel-name']",
            ".PropertyCard__Name",
            "[data-selenium='hotel-name']",
            "h3",
            "a[href*='/hotel/']"
        ]

        hotel_name = "N/A"
        for selector in hotel_name_selectors:
            hotel_name_element = await item.query_selector(selector)
            if hotel_name_element:
                hotel_name = await hotel_name_element.text_content()
                if hotel_name and hotel_name.strip():
                    hotel_name = hotel_name.strip()
                    break

        if hotel_name == "N/A" or not hotel_name:
            print("Could not extract hotel name, skipping...")
            return None

        print(f"\nProcessing hotel: {hotel_name}")

        # Extract rating
        rating_elements = await item.query_selector_all("span")
        rating_text = "N/A"
        for element in rating_elements:
            element_text = await element.text_content()
            if element_text and "stars out of 5" in element_text:
                rating_text = await element.inner_text()
                break

        hotel_rating = "N/A"
        if rating_text != "N/A":
            try:
                hotel_rating = rating_text.split(" ")[0]
            except Exception:
                pass

        # Updated price extraction with more selectors
        price_text = "N/A"

        # Extended list of price selectors
        price_selectors = [
            "div[data-element-name='final-price'] span:nth-child(2)",
            "div[data-element-name='final-price']",
            "span[data-selenium='price-value']",
            "span[data-selenium='price']",
            "div[data-selenium='price']",
            "div[data-element-name='price']",
            ".PropertyCard__Price",
            "[data-testid='price']",
            ".price",
            "span[class*='price']",
            "div[class*='price']"
        ]

        for selector in price_selectors:
            price_element = await item.query_selector(selector)
            if price_element:
                price_text = await price_element.inner_text()
                print(f"Found price with selector {selector}: {price_text}")
                if price_text and price_text != "N/A" and price_text.strip():
                    break

        hotel_price = "N/A"
        if price_text != "N/A" and price_text:
            try:
                # Clean and convert price to float
                # Remove currency symbols and other non-numeric characters except decimal point
                cleaned_price = ''.join(c for c in price_text if c.isdigit() or c == '.')
                if cleaned_price:
                    hotel_price = float(cleaned_price)
                    print(f"Extracted price: {hotel_price}")
            except Exception as e:
                print(f"Error converting price: {e}")

        # Only return hotel data if price is available
        if hotel_price == "N/A":
            print(f"Skipping hotel {hotel_name} - no valid price found")
            return None

        # Extract booking URL
        booking_url_selectors = [
            "a[data-selenium='hotel-name']",
            "a[class*='PropertyCard__Link']",
            "a[href*='/hotel/']"
        ]

        booking_url = "N/A"
        for selector in booking_url_selectors:
            booking_url_element = await item.query_selector(selector)
            if booking_url_element:
                booking_url = await booking_url_element.get_attribute("href")
                if booking_url:
                    break

        # Extract main image URL
        image_selectors = [
            "button[data-element-name='ssrweb-mainphoto'] img",
            "img[data-selenium='hotel-image']",
            ".PropertyCard__Image img",
            "img"
        ]

        main_image_url = "N/A"
        for selector in image_selectors:
            main_image_element = await item.query_selector(selector)
            if main_image_element:
                main_image_url = await main_image_element.get_attribute("src")
                if main_image_url:
                    break

        hotel_data = {
            'hotel_name': hotel_name,
            'hotel_price': hotel_price,
            'hotel_rating': hotel_rating,
            'booking_url': 'https://www.agoda.com' + booking_url if booking_url != "N/A" and not booking_url.startswith(
                'http') else booking_url,
            'image_url': 'https:' + main_image_url if main_image_url != "N/A" and main_image_url.startswith(
                '//') else main_image_url
        }
        print(f"Successfully extracted hotel data: {hotel_data}")
        return hotel_data
    except Exception as e:
        print(f"Error extracting hotel information: {e}")
    return None


async def scrape_first_page_results(page, location):
    """
    Scrolls down the first page and extracts all hotel listings.
    """
    hotel_info = []

    # Use the robust waiting function instead of a single selector
    if not await wait_for_results_page(page):
        print("Could not load results page properly")
        return hotel_info

    print("Results page loaded. Checking for hotels...")

    # Check for no results with multiple selectors
    no_results_selectors = [
        "//*[contains(text(), \"We couldn't find any results that match your search criteria\")]",
        "//*[contains(text(), 'No results found')]",
        "//*[contains(text(), 'no properties found')]",
        "//*[contains(text(), 'Sorry, no properties')]"
    ]

    for selector in no_results_selectors:
        if await page.is_visible(selector, timeout=3000):
            print("No results found for this search")
            return hotel_info

    # Scroll to load all content on the first page
    print("Scrolling through results to load all content...")
    last_height = await page.evaluate("document.body.scrollHeight")
    current_position = 0

    while current_position < last_height:
        remaining_height = last_height - current_position
        scroll_percentage = random.uniform(0.15, 0.25)
        scroll_amount = max(int(remaining_height * scroll_percentage), 200)
        await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
        current_position += scroll_amount
        await random_delay(0.5, 1.5)
        new_height = await page.evaluate("document.body.scrollHeight")
        if new_height > last_height:
            last_height = new_height

    print("Extracting hotel details from first page...")

    # Multiple selectors for hotel items
    hotel_item_selectors = [
        "//ol[@class='hotel-list-container']//li[@data-selenium='hotel-item']",
        "//li[@data-selenium='hotel-item']",
        "//div[@data-selenium='hotel-item']",
        "[data-selenium='hotel-item']",
        ".PropertyCard",
        "div[class*='property-card']"
    ]

    hotel_items = []
    for selector in hotel_item_selectors:
        try:
            if selector.startswith("//") or selector.startswith("(/"):
                hotel_items = await page.query_selector_all(selector)
            else:
                hotel_items = await page.query_selector_all(selector)

            if hotel_items:
                print(f"Found {len(hotel_items)} hotel items with selector: {selector}")
                break
        except Exception as e:
            print(f"Error with selector {selector}: {e}")
            continue

    if not hotel_items:
        print("No hotel items found on the page")
        # Debug: Take a screenshot to see what's on the page
        try:
            await page.screenshot(path="debug_page.png")
            print("Debug screenshot saved as 'debug_page.png'")
        except Exception as e:
            print(f"Could not take debug screenshot: {e}")
        return hotel_info

    hotels_with_prices = 0
    hotels_without_prices = 0

    for item in hotel_items:
        hotel_data = await extract_hotel_info(item)
        if hotel_data:
            hotel_info.append(hotel_data)
            hotels_with_prices += 1
        else:
            hotels_without_prices += 1

    print(f"Hotels with prices: {hotels_with_prices}")
    print(f"Hotels without prices (skipped): {hotels_without_prices}")
    print(f"Total hotels extracted: {len(hotel_info)}")
    return hotel_info


async def agoda_scraper(
        location: str,
        check_in_date: str,
        check_out_date: str,
        adults: int = 2,
        output_folder: Optional[str] = None,
        save_to_file: bool = False,
        star_rating: Optional[int] = None,
        currency: Optional[str] = None  # <-- add this
) -> List[Dict[str, Any]]:
    """
    Scrapes Agoda for hotel listings based on the provided parameters.

    Args:
        location (str): The location/city to search for hotels
        check_in_date (str): Check-in date in 'YYYY-MM-DD' format
        check_out_date (str): Check-out date in 'YYYY-MM-DD' format
        adults (int): Number of adults (default: 2)
        output_folder (str, optional): Folder to save JSON results
        save_to_file (bool): Whether to save results to JSON file

    Returns:
        List[Dict[str, Any]]: List of hotel information dictionaries

    Raises:
        ValueError: If date format is invalid
        Exception: If scraping fails
    """
    # Validate input parameters
    if not location.strip():
        raise ValueError("Location cannot be empty")

    if not validate_date_format(check_in_date):
        raise ValueError(f"Invalid check-in date format: {check_in_date}. Use 'YYYY-MM-DD' format")

    if not validate_date_format(check_out_date):
        raise ValueError(f"Invalid check-out date format: {check_out_date}. Use 'YYYY-MM-DD' format")

    if adults < 1 or adults > 10:
        raise ValueError("Number of adults must be between 1 and 10")

    # Validate date logic
    check_in = datetime.strptime(check_in_date, '%Y-%m-%d')
    check_out = datetime.strptime(check_out_date, '%Y-%m-%d')

    if check_out <= check_in:
        raise ValueError("Check-out date must be after check-in date")

    hotel_results = []

    try:
        print(f"Starting Agoda scraping for:")
        print(f"Location: {location}")
        print(f"Check-in: {check_in_date}")
        print(f"Check-out: {check_out_date}")
        print(f"Adults: {adults}")
        print("-" * 50)

        async with async_playwright() as p:
            page, context, browser = await visit_agoda_homepage(p)
            await search_agoda_homepage(page, location, check_in_date, check_out_date, adults, star_rating=star_rating, currency=currency)
            hotel_results = await scrape_first_page_results(page, location)
            await context.close()
            await browser.close()

    except Exception as e:
        print(f"Error during Agoda scraping: {e}")
        # Don't re-raise the exception immediately, try to return partial results
        print("Attempting to continue with any partial results...")

    # Print results summary
    print("\n" + "=" * 80)
    print(f"HOTEL RESULTS FOR {location.upper()}")
    print(f"Check-in: {check_in_date} | Check-out: {check_out_date} | Adults: {adults}")
    print("=" * 80)

    if hotel_results:
        for i, hotel in enumerate(hotel_results[:5], 1):  # Show first 5 in console
            print(f"\n{i}. Hotel Name: {hotel['hotel_name']}")
            print(f"   Price: ${hotel['hotel_price']}")
            print(f"   Rating: {hotel['hotel_rating']} stars")
            print(f"   Booking URL: {hotel['booking_url']}")
            print("-" * 60)

        if len(hotel_results) > 5:
            print(f"\n... and {len(hotel_results) - 5} more hotels")
    else:
        print("No hotels found.")

    print(f"\nTotal hotels found: {len(hotel_results)}")

    # Save to JSON file if requested
    if save_to_file:
        if not output_folder:
            output_folder = 'hotel_results'

        os.makedirs(output_folder, exist_ok=True)

        # Create filename with search parameters
        safe_location = "".join(c for c in location if c.isalnum() or c in (' ', '-', '_')).rstrip()
        output_filename = f"{safe_location}_{check_in_date}_{check_out_date}_{adults}adults.json"
        output_path = os.path.join(output_folder, output_filename)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                'search_parameters': {
                    'location': location,
                    'check_in_date': check_in_date,
                    'check_out_date': check_out_date,
                    'adults': adults,
                    'search_timestamp': datetime.now().isoformat()
                },
                'total_results': len(hotel_results),
                'hotels': hotel_results
            }, f, indent=4, ensure_ascii=False)

        print(f"Saved results to: {output_path}")

    return hotel_results
