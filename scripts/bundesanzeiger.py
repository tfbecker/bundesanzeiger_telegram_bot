from io import BytesIO

import dateparser
import numpy as np
import requests
from bs4 import BeautifulSoup
import os
import json
from openai import OpenAI
import logging
from datetime import datetime
import sqlite3
from fuzzywuzzy import fuzz
from dotenv import load_dotenv

from deutschland.config import Config, module_config

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bundesanzeiger.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Enable more detailed debugging for this module
logger.setLevel(logging.DEBUG)

# Load environment variables
load_dotenv()

class FinancialDataCache:
    def __init__(self, db_path=None):
        self.db_path = db_path or os.getenv('DB_PATH', "financial_cache.db")
        self.setup_database()
    
    def setup_database(self):
        """Create the database and table if they don't exist"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Original table for search queries
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS financial_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    search_query TEXT NOT NULL,
                    company_name TEXT,
                    report_name TEXT,
                    report_date TEXT,
                    earnings_current_year REAL,
                    total_assets REAL,
                    revenue REAL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # New table for storing full reports
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reports_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_name TEXT NOT NULL,
                    report_name TEXT NOT NULL,
                    report_date TEXT,
                    report_content TEXT,
                    report_url TEXT,
                    earnings_current_year REAL,
                    total_assets REAL,
                    revenue REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_accessed DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(company_name, report_name, report_date)
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
            # Check if the table exists and has the expected columns
            try:
                cursor.execute("PRAGMA table_info(financial_data)")
                columns = [col[1] for col in cursor.fetchall()]
                
                # Build a query based on available columns
                select_fields = []
                if "search_query" in columns:
                    select_fields.append("search_query")
                if "company_name" in columns:
                    select_fields.append("company_name")
                else:
                    # Fall back to search_query for company name if company_name column doesn't exist
                    select_fields.append("search_query as company_name")
                if "report_name" in columns:
                    select_fields.append("report_name")
                if "report_date" in columns:
                    select_fields.append("report_date")
                else:
                    select_fields.append("timestamp as report_date")
                if "earnings_current_year" in columns:
                    select_fields.append("earnings_current_year")
                if "total_assets" in columns:
                    select_fields.append("total_assets")
                if "revenue" in columns:
                    select_fields.append("revenue")
                
                # Execute the query
                query = f"SELECT {', '.join(select_fields)} FROM financial_data"
                cursor.execute(query)
                results = cursor.fetchall()
                
                for row in results:
                    # Get stored_query (should be the first field)
                    stored_query = row[0]
                    similarity = fuzz.ratio(search_query.lower(), stored_query.lower())
                    if similarity >= similarity_threshold:
                        logger.info(f"Found cached result for similar query: {stored_query} (similarity: {similarity}%)")
                        
                        # Create result dict dynamically based on columns
                        result = {
                            "found": True,
                            "is_cached": True,
                        }
                        
                        # Map result fields
                        for i, field in enumerate(select_fields):
                            field_name = field.split(" as ")[-1]  # Handle aliases
                            if field_name == "company_name":
                                result["company_name"] = row[i]
                            elif field_name == "report_name":
                                result["report_name"] = row[i]
                            elif field_name == "report_date":
                                result["date"] = row[i]
                            elif field_name in ["earnings_current_year", "total_assets", "revenue"]:
                                if "financial_data" not in result:
                                    result["financial_data"] = {}
                                result["financial_data"][field_name] = row[i]
                        
                        return result
            except sqlite3.Error as e:
                logger.error(f"Database error in find_similar_query: {e}")
                # If there's an error, recreate the table
                self.setup_database()
                
        return None
    
    def store_result(self, search_query: str, data: dict):
        """Store the search result in the cache only if financial data is available"""
        financial_data = data.get("financial_data", {})
        
        # Check if all values are null
        if all(financial_data.get(key) is None for key in ['earnings_current_year', 'total_assets', 'revenue']):
            logger.info("Skipping cache storage: all financial values are null")
            return

        # Check if the table structure matches our expectations
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get the current table structure
            cursor.execute("PRAGMA table_info(financial_data)")
            columns = [col[1] for col in cursor.fetchall()]
            
            # If we need to add columns that don't exist yet
            if "company_name" not in columns:
                logger.info("Adding company_name column to financial_data table")
                cursor.execute("ALTER TABLE financial_data ADD COLUMN company_name TEXT")
            
            if "report_name" not in columns:
                logger.info("Adding report_name column to financial_data table")
                cursor.execute("ALTER TABLE financial_data ADD COLUMN report_name TEXT")
                
            if "report_date" not in columns:
                logger.info("Adding report_date column to financial_data table")
                cursor.execute("ALTER TABLE financial_data ADD COLUMN report_date TEXT")
            
            conn.commit()
            
            # Now insert the data
            cursor.execute("""
                INSERT INTO financial_data 
                (search_query, company_name, report_name, report_date, 
                 earnings_current_year, total_assets, revenue)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                search_query,
                data.get("company_name"),
                data.get("report_name"),
                data.get("date"),
                financial_data.get("earnings_current_year"),
                financial_data.get("total_assets"),
                financial_data.get("revenue")
            ))
            conn.commit()
            logger.info(f"Stored new result for query: {search_query}")

    def get_cached_report(self, company_name: str, report_name: str, report_date: str = None) -> dict:
        """
        Check if a report exists in the cache and return it
        Returns None if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            query = """
                SELECT company_name, report_name, report_date, report_content, 
                       earnings_current_year, total_assets, revenue, report_url
                FROM reports_cache 
                WHERE company_name = ? AND report_name = ?
            """
            
            params = [company_name, report_name]
            
            if report_date:
                query += " AND report_date = ?"
                params.append(report_date)
            
            cursor.execute(query, params)
            result = cursor.fetchone()
            
            if result:
                logger.info(f"Found cached report for: {company_name} - {report_name}")
                
                # Update last_accessed timestamp
                cursor.execute("""
                    UPDATE reports_cache 
                    SET last_accessed = CURRENT_TIMESTAMP
                    WHERE company_name = ? AND report_name = ?
                """, (company_name, report_name))
                conn.commit()
                
                # Return report data as dictionary
                return {
                    "company": result[0],
                    "name": result[1],
                    "date": result[2],
                    "report": result[3],
                    "financial_data": {
                        "earnings_current_year": result[4],
                        "total_assets": result[5],
                        "revenue": result[6]
                    },
                    "link": result[7],
                    "is_cached": True
                }
            
            return None
    
    def store_report(self, report_data: dict):
        """
        Store a full report and its financial data in the cache
        """
        company_name = report_data.get("company")
        report_name = report_data.get("name")
        report_date = report_data.get("date")
        report_content = report_data.get("report")
        report_url = report_data.get("link")
        
        # No point caching if we don't have the report content
        if not report_content:
            logger.info(f"Skipping cache storage for {company_name} - {report_name}: no report content")
            return
        
        financial_data = report_data.get("financial_data", {})
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO reports_cache
                    (company_name, report_name, report_date, report_content, report_url,
                     earnings_current_year, total_assets, revenue)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    company_name,
                    report_name,
                    report_date,
                    report_content,
                    report_url,
                    financial_data.get("earnings_current_year"),
                    financial_data.get("total_assets"),
                    financial_data.get("revenue")
                ))
                conn.commit()
                logger.info(f"Stored report in cache: {company_name} - {report_name}")
            except sqlite3.Error as e:
                logger.error(f"Error storing report in cache: {e}")


class Report:
    __slots__ = ["date", "name", "content_url", "company", "report", "financial_data"]

    def __init__(self, date, name, content_url, company, report=None, financial_data=None):
        self.date = date
        self.name = name
        self.content_url = content_url
        self.company = company
        self.report = report
        self.financial_data = financial_data

    def to_dict(self):
        return {
            "date": self.date.strftime('%Y-%m-%d') if isinstance(self.date, datetime) else self.date,
            "name": self.name,
            "company": self.company,
            "report": self.report,
            "financial_data": self.financial_data
        }


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
        # Log a sample of the text for debugging
        text_sample = text[:500] + "..." if len(text) > 500 else text
        logger.info(f"Processing financial data with text length: {len(text)} characters")
        logger.debug(f"Text sample: {text_sample}")
        
        # Check if we need to truncate the text
        max_length = 400000  # Approximating 100K tokens (4 chars per token)
        if len(text) > max_length:
            logger.info(f"Truncating text from {len(text)} to {max_length} characters for API call")
            text = text[:max_length] + "..."
        
        # Use o3-mini model with large context window
        logger.info("Calling OpenAI API to extract financial data using o3-mini model")
        response = client.chat.completions.create(
            model="gpt-4.1-mini",  # Using o3-mini with larger context window
            messages=[
                {"role": "system", "content": "You are an accounting specialist focused on German financial reports. Extract financial data in EUR. Only respond with JSON."},
                {"role": "user", "content": prompt + text}
            ],
            response_format={ "type": "json_object" }
        )
        
        # Log the full response for debugging
        response_content = response.choices[0].message.content
        logger.info(f"OpenAI API raw response: {response_content}")
        
        # Parse the JSON response
        financial_data = json.loads(response_content)
        logger.info(f"Extracted financial data: {json.dumps(financial_data, indent=2)}")
        
        # Log a summary of what was found and what wasn't
        found_fields = [k for k, v in financial_data.items() if v is not None]
        missing_fields = [k for k, v in financial_data.items() if v is None]
        logger.info(f"Fields found: {found_fields}")
        logger.info(f"Fields missing: {missing_fields}")
        
        return financial_data
    except Exception as e:
        logger.error(f"Error processing financial data: {e}", exc_info=True)
        if "response" in locals() and hasattr(response, "choices"):
            logger.error(f"Response content that caused error: {response.choices[0].message.content}")
        return {
            "earnings_current_year": None,
            "total_assets": None,
            "revenue": None
        }


class Bundesanzeiger:
    __slots__ = ["session", "model", "captcha_callback", "_config", "openai_client", "cache"]

    def __init__(self, on_captach_callback=None, config: Config = None):
        if config is None:
            self._config = module_config
        else:
            self._config = config

        self.session = requests.Session()
        if self._config.proxy_config is not None:
            self.session.proxies.update(self._config.proxy_config)
        if on_captach_callback:
            self.callback = on_captach_callback
        else:
            import deutschland.bundesanzeiger.model

            self.model = deutschland.bundesanzeiger.model.load_model()
            self.captcha_callback = self.__solve_captcha
            
        # Initialize OpenAI client
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Initialize cache
        self.cache = FinancialDataCache()

    def __solve_captcha(self, image_data: bytes):
        import deutschland.bundesanzeiger.model

        image = BytesIO(image_data)
        image_arr = deutschland.bundesanzeiger.model.load_image_arr(image)
        image_arr = image_arr.reshape((1, 50, 250, 1)).astype(np.float32)

        prediction = self.model.run(None, {"captcha": image_arr})[0][0]
        prediction_str = deutschland.bundesanzeiger.model.prediction_to_str(prediction)

        return prediction_str

    def __is_captcha_needed(self, entry_content: str):
        soup = BeautifulSoup(entry_content, "html.parser")
        return not bool(soup.find("div", {"class": "publication_container"}))

    def __find_all_entries_on_page(self, page_content: str):
        soup = BeautifulSoup(page_content, "html.parser")
        wrapper = soup.find("div", {"class": "result_container"})
        
        # Check if wrapper exists (if no results were found, wrapper will be None)
        if wrapper is None:
            logger.info("No results found in the search response")
            return []
            
        rows = wrapper.find_all("div", {"class": "row"})
        for row in rows:
            # Look for category information (Bereich)
            category_element = row.find("div", {"class": "area"})
            if category_element and category_element.text.strip():
                category = category_element.text.strip()
                # Only process financial reports
                if "Rechnungslegung" not in category and "Finanzberichte" not in category:
                    logger.debug(f"Skipping non-financial report with category: {category}")
                    continue
            
            info_element = row.find("div", {"class": "info"})
            if not info_element:
                continue

            link_element = info_element.find("a")
            if not link_element:
                continue

            entry_link = link_element.get("href")
            entry_name = link_element.contents[0].strip()

            date_element = row.find("div", {"class": "date"})
            if not date_element:
                continue

            date = dateparser.parse(date_element.contents[0], languages=["de"])

            company_name_element = row.find("div", {"class": "first"})
            if not company_name_element:
                continue

            # Check if the element has contents before accessing it
            if not company_name_element.contents:
                company_name = "Unknown Company"
            else:
                company_name = company_name_element.contents[0].strip()

            logger.info(f"Found financial report: {entry_name} for {company_name} dated {date}")
            yield Report(date, entry_name, entry_link, company_name)

    def __generate_result(self, content: str):
        """iterate trough all results and try to fetch single reports"""
        result = {}
        # Collect all reports first, but don't process the reports yet
        all_reports = list(self.__find_all_entries_on_page(content))
        
        # Sort reports by date with newest first
        all_reports.sort(key=lambda x: x.date if x.date else datetime.min, reverse=True)
        
        for element in all_reports:
            get_element_response = self.session.get(element.content_url)

            if self.__is_captcha_needed(get_element_response.text):
                soup = BeautifulSoup(get_element_response.text, "html.parser")
                captcha_image_src = soup.find("div", {"class": "captcha_wrapper"}).find(
                    "img"
                )["src"]
                img_response = self.session.get(captcha_image_src)
                captcha_result = self.captcha_callback(img_response.content)
                captcha_endpoint_url = soup.find_all("form")[1]["action"]
                get_element_response = self.session.post(
                    captcha_endpoint_url,
                    data={"solution": captcha_result, "confirm-button": "OK"},
                )

            content_soup = BeautifulSoup(get_element_response.text, "html.parser")
            content_element = content_soup.find(
                "div", {"class": "publication_container"}
            )

            if not content_element:
                continue

            element.report = content_element.text
            
            # Process financial data using OpenAI, but only for the report we're interested in
            if element.report:
                financial_data = process_financial_data(element.report, self.openai_client)
                element.financial_data = financial_data
                
                # If we found financial data in this report, add it to the result and stop processing
                if any(financial_data.get(k) is not None for k in ['earnings_current_year', 'total_assets', 'revenue']):
                    result[element.name] = element.to_dict()
                    # We found a valid report with financial data, so we can stop processing
                    logger.info(f"Found valid financial data in report: {element.name}. Stopping processing.")
                    break
                
                # Even if we didn't find valid financial data, add this report to the results
                # This way we at least return the most recent report
                result[element.name] = element.to_dict()
                # Only process the most recent report, regardless of financial data
                logger.info(f"Processed most recent report: {element.name}. Stopping processing.")
                break

        return result

    def get_reports(self, company_name: str):
        """
        fetch all reports for this company name
        :param company_name:
        :return" : "Dict of all reports
        """
        self.session.cookies["cc"] = "1628606977-805e172265bfdbde-10"
        self.session.headers.update(
            {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7,et;q=0.6,pl;q=0.5",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "DNT": "1",
                "Host": "www.bundesanzeiger.de",
                "Pragma": "no-cache",
                "Referer": "https://www.bundesanzeiger.de/",
                "sec-ch-ua-mobile": "?0",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36",
            }
        )
        # get the jsessionid cookie
        response = self.session.get("https://www.bundesanzeiger.de")
        # go to the start page
        response = self.session.get("https://www.bundesanzeiger.de/pub/de/start?0")
        # perform the search
        response = self.session.get(
            f"https://www.bundesanzeiger.de/pub/de/start?0-2.-top%7Econtent%7Epanel-left%7Ecard-form=&fulltext={company_name}&area_select=&search_button=Suchen"
        )
        return self.__generate_result(response.text)

    def get_company_financial_info(self, company_name: str):
        """
        A simplified method that returns just the financial information and company details
        :param company_name:
        :return: Dictionary with company name, financial data, and date
        """
        # Check cache first
        cached_result = self.cache.find_similar_query(company_name)
        if cached_result:
            logger.info(f"Using cached result for query similar to: {company_name}")
            return cached_result
            
        # If not in cache, get fresh data
        reports = self.get_reports(company_name)
        
        if not reports:
            return {
                "company_name": company_name,
                "found": False,
                "message": "No reports found for this company"
            }
        
        # Since we now only process the latest report, we can just take the first (and only) report
        if reports:
            report_name = next(iter(reports))
            report = reports[report_name]
            
            # Check if we have any financial data
            has_financial_data = report.get('financial_data', {}) and any(
                report.get('financial_data', {}).get(k) is not None 
                for k in ['earnings_current_year', 'total_assets', 'revenue']
            )
            
            result = {}
            
            if has_financial_data:
                result = {
                    "company_name": report.get('company'),
                    "found": True,
                    "is_cached": False,
                    "date": report.get('date'),
                    "financial_data": report.get('financial_data'),
                    "report_name": report.get('name')
                }
            else:
                result = {
                    "company_name": report.get('company', company_name),
                    "found": True,
                    "is_cached": False,
                    "date": report.get('date', 'Unknown'),
                    "report_name": report.get('name', 'Unknown'),
                    "message": "Found report but couldn't extract financial data"
                }
            
            # Store in cache if we have financial data
            if has_financial_data:
                self.cache.store_result(company_name, result)
                
            return result


if __name__ == "__main__":
    ba = Bundesanzeiger()
    reports = ba.get_reports("Deutsche Bahn AG")
    print(reports.keys(), len(reports))
    
    # Test the new function
    financial_info = ba.get_company_financial_info("Deutsche Bahn AG")
    print("Company Financial Info:", json.dumps(financial_info, indent=2))
