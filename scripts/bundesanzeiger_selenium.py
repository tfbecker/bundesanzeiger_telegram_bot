from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time
from openai import OpenAI
import os
import json
import sqlite3
from datetime import datetime
from fuzzywuzzy import fuzz
import logging
import requests
import base64

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FinancialDataCache:
    def __init__(self, db_path="financial_cache.db"):
        self.db_path = db_path
        self.setup_database()
    
    def setup_database(self):
        """Create the database and table if they don't exist"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS financial_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    search_query TEXT NOT NULL,
                    earnings_current_year REAL,
                    total_assets REAL,
                    revenue REAL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
    
    def find_similar_query(self, search_query: str, similarity_threshold: int = 90) -> dict:
        """
        Find a similar query in the cache using fuzzy matching.
        Returns None if no similar query is found.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT search_query, earnings_current_year, total_assets, revenue FROM financial_data")
            results = cursor.fetchall()
            
            for stored_query, earnings, assets, rev in results:
                similarity = fuzz.ratio(search_query.lower(), stored_query.lower())
                if similarity >= similarity_threshold:
                    logger.info(f"Found cached result for similar query: {stored_query} (similarity: {similarity}%)")
                    return {
                        "earnings_current_year": earnings,
                        "total_assets": assets,
                        "revenue": rev
                    }
        return None
    
    def store_result(self, search_query: str, financial_data: dict):
        """Store the search result in the cache only if at least one value is not null"""
        # Check if all values are null
        if all(financial_data.get(key) is None for key in ['earnings_current_year', 'total_assets', 'revenue']):
            logger.info("Skipping cache storage: all financial values are null")
            return

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO financial_data 
                (search_query, earnings_current_year, total_assets, revenue)
                VALUES (?, ?, ?, ?)
            """, (
                search_query,
                financial_data.get('earnings_current_year'),
                financial_data.get('total_assets'),
                financial_data.get('revenue')
            ))
            conn.commit()
            logger.info(f"Stored new result for query: {search_query}")

def process_financial_data(text: str, client: OpenAI) -> dict:
    """
    Process the financial data through OpenAI API to extract structured information.
    """
    prompt = """You are analyzing public financial information from a company. 
    Extract and return ONLY the following information in a JSON format:
    - earnings_current_year (in EUR)
    - total_assets (in EUR)
    - revenue (in EUR)
    
    If a value cannot be found, use null.
    Only return the JSON object, nothing else.
    Example output: {"earnings_current_year": 1000000, "total_assets": 5000000, "revenue": null}
    
    Here's the financial information:
    """
    
    try:
        response = client.chat.completions.create(
            model="o3-mini",
            messages=[
                {"role": "system", "content": "You are an accounting specialist. Only respond with JSON."},
                {"role": "user", "content": prompt + text}
            ],
            response_format={ "type": "json_object" }
        )
        
        # Parse the JSON response
        financial_data = json.loads(response.choices[0].message.content)
        return financial_data
    except Exception as e:
        logger.error(f"Error processing financial data: {e}")
        return {
            "earnings_current_year": None,
            "total_assets": None,
            "revenue": None
        }

# Function to encode the image
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def solve_captcha(image_path: str) -> str:
    base64_image = encode_image(image_path)
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"
    }

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Extract the captcha code from the image. Only answer with the captcha code. Example: ABDLNFH"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 300
    }

    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    
    try:
        response_data = response.json()
        captcha_solution = response_data['choices'][0]['message']['content'].strip()
        return captcha_solution
    except Exception as e:
        print(f"Error processing the captcha: {str(e)}")
        return "Retry or manual check needed"

def main(company_name: str, city: str) -> dict:
    # Initialize cache
    cache = FinancialDataCache()
    
    # Create cache key that includes both company name and city
    search_key = f"{company_name} {city}"
    
    # Check cache first
    cached_result = cache.find_similar_query(search_key)
    if cached_result:
        logger.info(f"Using cached result for query similar to: {search_key}")
        return cached_result

    # If not in cache, proceed with web scraping
    logger.info(f"No cache found for {search_key}, proceeding with web scraping")
    
    max_retries = 3
    retry_count = 0
    last_error = None

    while retry_count < max_retries:
        try:
            # Create screenshots directory if it doesn't exist
            if not os.path.exists('screenshots'):
                os.makedirs('screenshots')

            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            print(f"Starting the bundesanzeiger function (attempt {retry_count + 1}/{max_retries})")
            options = webdriver.ChromeOptions()
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            driver = webdriver.Chrome(options=options)

            try:
                print(f"Navigating to https://www.bundesanzeiger.de/")
                driver.get("https://www.bundesanzeiger.de/")
                time.sleep(2)

                # Close the cookie banner
                print("Closing the cookie banner")
                time.sleep(2)
                try:
                    driver.find_element(By.CSS_SELECTOR, 'button#cc_all.btn.btn-green').click()
                    time.sleep(1)
                except Exception as e:
                    print(f"Failed to close the cookie banner: {e}")

                # Use the search bar to insert both company name and city
                print(f"Filling search bar with company name and city: {company_name} {city}")
                search_bar = driver.find_element(By.XPATH, '/html/body/div[1]/section[1]/div/div/div[1]/div/div[2]/form/div[3]/input')
                search_bar.send_keys(f"{company_name} {city}")
                time.sleep(1)
                search_bar.send_keys(Keys.RETURN)
                time.sleep(2)

                # Extract and clean the results
                print("Extracting search results")
                results = driver.find_elements(By.CSS_SELECTOR, '.result_container .row')
                if not results:
                    print("No results found")
                    driver.quit()
                    retry_count += 1
                    continue

                # Extract the text for each row
                print("Extracting text and links for each result row")
                for i, result in enumerate(results[:5]):
                    try:
                        row_text = result.text.strip()
                        link_element = result.find_element(By.CSS_SELECTOR, '.info a')
                        link = link_element.get_attribute('href')
                    except Exception as e:
                        continue

                # Click on the first link
                print("Clicking on the first working link")
                link_clicked = False
                for result in results:
                    try:
                        link_element = result.find_element(By.CSS_SELECTOR, '.info a')
                        link = link_element.get_attribute('href')
                        if link:
                            link_element.click()
                            link_clicked = True
                            time.sleep(1)
                            break
                    except Exception as e:
                        continue

                if not link_clicked:
                    raise Exception("No valid links found")

                # Wait for the captcha to appear
                print("Waiting for captcha to appear")
                time.sleep(2)
                captcha_image = driver.find_element(By.CSS_SELECTOR, '.captcha_wrapper img')
                captcha_image.screenshot('screenshots/captcha.png')
                time.sleep(1)

                # Solve the captcha
                print("Solving the captcha")
                captcha_solution = solve_captcha('screenshots/captcha.png')
                print(f"Captcha solution: {captcha_solution}")

                if len(captcha_solution) >= 10:
                    print("Captcha solution is too long, extracting the captcha code using another LLM call")
                    headers = {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"
                    }

                    payload = {
                        "model": "gpt-4o-mini",
                        "messages": [
                            {
                                "role": "user",
                                "content": f"Extract the captcha code from the following text: {captcha_solution}. Only answer with the captcha code. Example: ABDLNFH"
                            }
                        ],
                        "max_tokens": 10
                    }

                    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
                    
                    try:
                        response_data = response.json()
                        captcha_solution = response_data['choices'][0]['message']['content'].strip()
                        print(f"Extracted captcha solution: {captcha_solution}")
                    except Exception as e:
                        print(f"Error extracting the captcha: {str(e)}")
                        raise Exception("Failed to process captcha")

                time.sleep(2)
                # Enter the captcha code
                print("Entering the captcha solution")
                driver.find_element(By.XPATH, '/html/body/div[1]/section/div/div/div/div/div[3]/div[2]/div[2]/form/div[2]/div[2]/div/input').send_keys(captcha_solution)
                time.sleep(1)

                # Press submit
                print("Submitting the captcha solution")
                driver.find_element(By.XPATH, '/html/body/div[1]/section/div/div/div/div/div[3]/div[2]/div[2]/form/div[2]/div[3]/div/input').click()
                time.sleep(1)

                # Wait for the final page to load
                print("Waiting for the final page to load")
                time.sleep(2)

                # Get the page content and process it
                print("Processing the financial information")
                body_text = driver.find_element(By.TAG_NAME, 'body').text

                # Check if we're still on the captcha page
                if "captcha" in body_text.lower():
                    raise Exception("Captcha validation failed")

                # Process the text through OpenAI
                financial_data = process_financial_data(body_text, client)
                
                logger.info("\nExtracted Financial Information:")
                logger.info(json.dumps(financial_data, indent=2))
                
                # Only store in cache if at least one value is not null
                if any(financial_data.get(key) is not None for key in ['earnings_current_year', 'total_assets', 'revenue']):
                    cache.store_result(search_key, financial_data)
                else:
                    logger.info("Not storing in cache: all financial values are null")
                
                return financial_data

            finally:
                driver.quit()

        except Exception as e:
            last_error = str(e)
            retry_count += 1
            logger.warning(f"Attempt {retry_count}/{max_retries} failed: {last_error}")
            time.sleep(2)  # Wait before retrying
            
    # If we've exhausted all retries
    error_msg = f"Failed after {max_retries} attempts. Last error: {last_error}"
    logger.error(error_msg)
    return {
        "earnings_current_year": None,
        "total_assets": None,
        "revenue": None,
        "error": error_msg
    }

if __name__ == "__main__":
    result = main("Holzland Becker Obertshausen", "Obertshausen")
    print("\nFinal Result:")
    print(json.dumps(result, indent=2))