from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Dict
import logging
import sys
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
import asyncio
from parsel import Selector
from urllib.parse import urlencode
import aiohttp

# Import your scrapers
from bookingScrapperWithFilters import ModernBookingScraper
from agodaScrapper import agoda_scraper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("hotel-api")

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # This allows all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
#...

# Coordinates model
class Coordinates(BaseModel):
    lat: float
    lng: float

# Request model
class HotelSearchRequest(BaseModel):
    location: str
    check_in: str
    check_out: str
    adults: int = 2
    filters: Optional[List[str]] = None
    currency: Optional[str] = "USD"
    coordinates: Optional[Coordinates] = None
    include_reviews: Optional[bool] = False
    review_limit: Optional[int] = 5

# Review model
class Review(BaseModel):
    reviewer_name: str
    reviewer_country: Optional[str] = None
    review_count: Optional[str] = None
    review_title: Optional[str] = None
    review_date: str
    review_score: str
    review_positive: Optional[str] = None
    review_negative: Optional[str] = None
    room_type: Optional[str] = None

# Nested rating model
class HotelRating(BaseModel):
    score: Optional[float] = None
    reviews: Optional[int] = None

# Response model
class Hotel(BaseModel):
    name: Optional[str] = None
    price: Optional[str] = None
    rating: Optional[HotelRating] = None
    stars: Optional[int] = None
    location: Optional[str] = None
    url: Optional[str] = None
    availability: Optional[str] = None
    reviews: Optional[List[Review]] = None  # Added reviews field
    distance_from_center: Optional[float] = None  # Added distance field
    coordinates: Optional[Dict[str, float]] = None  # Added coordinates field

# Geocoding endpoint
@app.post("/geocode")
async def geocode_coordinates(coordinates: Coordinates):
    try:
        geolocator = Nominatim(user_agent="hotel_finder")
        location = geolocator.reverse(f"{coordinates.lat}, {coordinates.lng}")
        if location:
            address = location.raw.get('address', {})
            city = (
                address.get('city') or 
                address.get('town') or 
                address.get('village') or 
                address.get('suburb') or 
                address.get('locality')
            )
            if not city:
                raise HTTPException(status_code=400, detail="Could not determine city from coordinates")
            return {"address": city}
        raise HTTPException(status_code=400, detail="Location not found")
    except GeocoderTimedOut:
        raise HTTPException(status_code=408, detail="Geocoding service timed out")
    except Exception as e:
        logger.error(f"Error in geocoding: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to geocode coordinates")

# New endpoint to get coordinates from location name
@app.get("/location-to-coordinates/{location_name}")
async def get_location_coordinates(location_name: str):
    try:
        geolocator = Nominatim(user_agent="hotel_finder")
        location = geolocator.geocode(location_name)
        if location:
            return {
                "latitude": location.latitude,
                "longitude": location.longitude,
                "address": location.address
            }
        raise HTTPException(status_code=400, detail="Location not found")
    except GeocoderTimedOut:
        raise HTTPException(status_code=408, detail="Geocoding service timed out")
    except Exception as e:
        logger.error(f"Error in geocoding: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to geocode location")

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "API is running"}

# Hotel search endpoint
@app.post("/search-hotels", response_model=List[Hotel])
async def search_hotels(request: HotelSearchRequest):
    try:
        logger.info(f"Received search request for location: {request.location}")
        original_location = request.location  # Store the original location

        # If coordinates are provided, get the location name for reference only
        if request.coordinates:
            try:
                geolocator = Nominatim(user_agent="hotel_finder")
                location = geolocator.reverse(f"{request.coordinates.lat}, {request.coordinates.lng}")
                if location:
                    address = location.raw.get('address', {})
                    city = (
                        address.get('city') or 
                        address.get('town') or 
                        address.get('village') or 
                        address.get('suburb') or 
                        address.get('locality')
                    )
                    if city:
                        logger.info(f"Geocoded location: {city}")
            except Exception as e:
                logger.error(f"Error in geocoding: {str(e)}", exc_info=True)

        # Always set include_reviews to True since we want to fetch reviews
        request.include_reviews = True
        request.review_limit = 5  # You can adjust this number

        # Create tasks for both scrapers
        async def get_booking_hotels():
            async with ModernBookingScraper() as scraper:
                return await scraper.search_hotels(
                    location=original_location,
                    check_in=request.check_in,
                    check_out=request.check_out,
                    adults=request.adults,
                    filters=request.filters,
                    currency=request.currency,
                    include_reviews=request.include_reviews,
                    review_limit=request.review_limit
                )

        async def get_agoda_hotels():
            try:
                # Extract star rating from filters (e.g., 'class=3')
                star_rating = None
                if request.filters:
                    for f in request.filters:
                        if f.startswith("class="):
                            try:
                                star_rating = int(f.split("=")[1])
                            except Exception:
                                pass
                # Convert Agoda results to match Hotel model
                agoda_results = await agoda_scraper(
                    location=original_location,
                    check_in_date=request.check_in,
                    check_out_date=request.check_out,
                    adults=request.adults,
                    star_rating=star_rating,  # Pass star_rating to Agoda scraper
                    currency=request.currency  # Pass currency from frontend
                )
                
                # Transform Agoda results to match Hotel model
                transformed_hotels = []
                for hotel in agoda_results:
                    # Try to parse hotel_rating as integer for stars
                    stars = None
                    if hotel['hotel_rating'] != "N/A":
                        try:
                            stars = int(float(hotel['hotel_rating']))
                        except Exception:
                            stars = None
                    transformed_hotel = Hotel(
                        name=hotel['hotel_name'],
                        price=str(hotel['hotel_price']),
                        rating=None,  # Agoda does not provide review score, only stars
                        stars=stars,  # Set stars from hotel_rating
                        location=original_location,
                        url=hotel['booking_url'],
                        availability=None,
                        reviews=None,  # Agoda scraper doesn't provide reviews
                        distance_from_center=None,
                        coordinates=None
                    )
                    transformed_hotels.append(transformed_hotel)
                return transformed_hotels
            except Exception as e:
                logger.error(f"Error in Agoda scraping: {str(e)}", exc_info=True)
                return []

        # Run both scrapers concurrently
        booking_hotels, agoda_hotels = await asyncio.gather(
            get_booking_hotels(),
            get_agoda_hotels()
        )

        # Combine results
        all_hotels = booking_hotels + agoda_hotels
        logger.info(f"Found {len(all_hotels)} total hotels ({len(booking_hotels)} from Booking.com, {len(agoda_hotels)} from Agoda)")
        
        return all_hotels
    except Exception as e:
        logger.error(f"Error searching hotels: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch hotel listings.")

async def parse_reviews(html: str) -> List[dict]:
    """parse review page for review data """
    sel = Selector(text=html)
    parsed = []
    for review_box in sel.css('.review_list_new_item_block'):
        get_css = lambda css: review_box.css(css).get("").strip()
        parsed.append({
            "id": review_box.xpath('@data-review-url').get(),
            "score": get_css('.bui-review-score__badge::text'),
            "title": get_css('.c-review-block__title::text'),
            "date": get_css('.c-review-block__date::text'),
            "user_name": get_css('.bui-avatar-block__title::text'),
            "user_country": get_css('.bui-avatar-block__subtitle::text'),
            "text": ''.join(review_box.css('.c-review__body ::text').getall()),
            "lang": review_box.css('.c-review__body::attr(lang)').get(),
        })
    return parsed

async def scrape_reviews(hotel_id: str) -> List[dict]:
    """scrape all reviews of a hotel"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    async with aiohttp.ClientSession() as session:
        async def scrape_page(page, page_size=25):
            # First try with the hotel ID directly
            params = {
                "type": "total",
                "lang": "en-us",
                "sort": "f_recent_desc",
                "cc1": "gb",
                "dist": 1,
                "rows": page_size,
                "offset": page * page_size,
            }
            
            # Try different parameter names for the hotel ID
            if hotel_id.startswith('hotel'):
                params['pagename'] = hotel_id
            else:
                params['hotel_id'] = hotel_id
                
            url = "https://www.booking.com/reviewlist.html?" + urlencode(params)
            
            async with session.get(url, headers=headers) as response:
                return await response.text()

        try:
            first_page = await scrape_page(1)
            total_pages = Selector(text=first_page).css(".bui-pagination__link::attr(data-page-number)").getall()
            if not total_pages:
                total_pages = [1]
            total_pages = max(int(page) for page in total_pages)
            
            # Only fetch additional pages if we found reviews on the first page
            if total_pages > 1 and len(await parse_reviews(first_page)) > 0:
                other_pages = await asyncio.gather(*[scrape_page(i) for i in range(2, min(total_pages + 1, 5))])  # Limit to 5 pages
                results = []
                for response in [first_page, *other_pages]:
                    results.extend(await parse_reviews(response))
                return results
            else:
                # If no reviews found with first approach, try alternate URL format
                params = {
                    "type": "total",
                    "lang": "en-us",
                    "sort": "f_recent_desc",
                    "cc1": "gb",
                    "dist": 1,
                    "hotel_id": hotel_id,
                    "rows": 25,
                    "offset": 0,
                }
                url = "https://www.booking.com/reviews/index.html?" + urlencode(params)
                async with session.get(url, headers=headers) as response:
                    return await parse_reviews(await response.text())
        except Exception as e:
            logger.error(f"Error scraping reviews: {str(e)}")
            return []

# Add new endpoint for fetching reviews
@app.get("/hotel-reviews/{hotel_id}")
async def get_hotel_reviews(hotel_id: str):
    try:
        logger.info(f"Fetching reviews for hotel: {hotel_id}")
        reviews = await scrape_reviews(hotel_id)
        logger.info(f"Found {len(reviews)} reviews for hotel {hotel_id}")
        return reviews
    except Exception as e:
        logger.error(f"Error fetching reviews: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch hotel reviews.")

# Run the server
if __name__ == "__main__":
    import uvicorn
    logger.info("Starting the Hotel API Server...")
    uvicorn.run(app, host="localhost", port=8000)
