from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time
from typing import List, Dict, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BookingScraper:
    def __init__(self):
        self.setup_driver()

    def setup_driver(self):
        """Set up Chrome driver with appropriate options"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Run in headless mode
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait = WebDriverWait(self.driver, 10)

    def get_reviews(self, hotel_url: str) -> List[Dict[Any, Any]]:
        """
        Scrape reviews from a Booking.com hotel page
        """
        try:
            self.driver.get(hotel_url)
            reviews = []
            
            # Wait for reviews to load
            self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "review_list_new_item_block")))
            
            # Scroll to load more reviews (if available)
            last_height = self.driver.execute_script("return document.body.scrollHeight")
            while True:
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height

            # Find all review elements
            review_elements = self.driver.find_elements(By.CLASS_NAME, "review_list_new_item_block")
            
            for review in review_elements:
                try:
                    review_data = {
                        "reviewer_name": review.find_element(By.CLASS_NAME, "bui-avatar-block__title").text,
                        "review_date": review.find_element(By.CLASS_NAME, "c-review-block__date").text,
                        "score": review.find_element(By.CLASS_NAME, "bui-review-score__badge").text,
                        "review_text": review.find_element(By.CLASS_NAME, "c-review").text,
                        "room_type": review.find_element(By.CLASS_NAME, "bui-list__body").text if review.find_elements(By.CLASS_NAME, "bui-list__body") else "N/A",
                        "stay_duration": review.find_element(By.CLASS_NAME, "bui-list__body").text if review.find_elements(By.CLASS_NAME, "bui-list__body") else "N/A"
                    }
                    reviews.append(review_data)
                except Exception as e:
                    logger.error(f"Error extracting review data: {str(e)}")
                    continue

            return reviews

        except TimeoutException:
            logger.error("Timeout waiting for reviews to load")
            return []
        except Exception as e:
            logger.error(f"Error scraping reviews: {str(e)}")
            return []

    def close(self):
        """Close the browser"""
        if self.driver:
            self.driver.quit()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close() 