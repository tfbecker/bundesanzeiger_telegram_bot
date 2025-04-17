import json
import logging
import os
import re
from typing import cast, Dict, Any, TypedDict, Optional

from bs4 import BeautifulSoup
import dotenv
from google import genai
from google.genai import types
from openai import OpenAI

logger = logging.getLogger(__name__)

# Constants
ALLOWED_HTML_ATTRIBUTES = ['href', 'src', 'alt', 'title', 'name']
# Gemini Prompt (updated instructions)
GEMINI_ANALYSIS_PROMPT = """Analyze the financial statement provided in HTML, focusing on extracting key financial figures for the reporting year. Pay close attention to tabular data and note that some amounts might be in units like thousands (kEUR/tEUR) or millions; adjust these amounts accordingly to represent them in EUR. Use the text and logical connections within the document to reliably identify and derive metrics. If a metric cannot be determined, omit it from the response JSON. Net profit should be negative in case of a loss. The profit carried forward can be negative in case of a loss carried forward. All amounts in EUR.\nHTML:\n"""
# OpenAI Prompt (updated instructions and examples)
OPENAI_ANALYSIS_PROMPT = """You are an accounting specialist analyzing public financial information from a German company provided in HTML.
Extract and return ONLY the following key financial figures for the reporting year in a JSON format.
All amounts must be in EUR. Adjust amounts given in thousands (kEUR/tEUR) or millions accordingly.
If a metric cannot be determined, omit it from the response JSON.
Net profit should be negative in case of a loss.
The profit carried forward can be negative in case of a loss carried forward.

Required fields (include only if found):
- net_profit: Net profit or net income/loss (EUR). Negative for loss.
- mitarbeiter: Average number of employees.
- umsatz: Revenue (EUR).
- gewinnvortrag: Profit/loss carried forward (EUR). Negative for loss carried forward.
- bilanzsumme_total: Total assets (or liabilities) (EUR).
- schulden: Total liabilities (debt) (EUR).
- eigenkapital: Equity (EUR).
- guv_zinsen: Interest expense or income (net) (EUR). Negative for interest expense.
- guv_steuern: Income taxes (EUR).
- guv_abschreibungen: Depreciation and amortization (EUR).
- cash: Cash and cash equivalents (EUR).
- dividende: Distribution or dividend (EUR).

Only return the JSON object, nothing else.
Example output (all found): {"net_profit": 150000, "mitarbeiter": 55, "umsatz": 2500000, "gewinnvortrag": 20000, "bilanzsumme_total": 1200000, "schulden": 700000, "eigenkapital": 500000, "guv_zinsen": -5000, "guv_steuern": 45000, "guv_abschreibungen": 80000, "cash": 100000, "dividende": 10000}
Example output (some missing): {"net_profit": -50000, "umsatz": 1800000, "gewinnvortrag": -10000, "bilanzsumme_total": 900000, "schulden": 600000, "eigenkapital": 300000, "guv_abschreibungen": 60000, "cash": 50000, "dividende": 0}

Here's the financial information in HTML:
"""
GEMINI_MODEL_NAME = "gemini-2.0-flash"
OPENAI_MODEL_NAME = "o3-mini"


def clean_html_content(html_content: str) -> str:
    """Removes unnecessary tags, attributes, and whitespace from HTML content.

    Args:
        html_content: The raw HTML string.

    Returns:
        The cleaned HTML string.
    """
    # Remove newline characters to simplify processing
    html_content = re.sub(r'\n', ' ', html_content)
    # Remove comments first
    html_content = re.sub(r'<!--.*?-->', '', html_content, flags=re.DOTALL)
    soup = BeautifulSoup(html_content, 'html.parser')

    # Remove script, style, meta, link tags
    for tag in soup(["script", "style", "meta", "link", "header", "footer", "nav", "aside"]):
        tag.decompose()

    def _clean_tag_attributes(tag):
        """Recursively removes disallowed attributes from a tag and its children."""
        if hasattr(tag, 'attrs'):
            # Create a list of attributes to remove
            attrs_to_remove = [
                attr for attr in tag.attrs if attr not in ALLOWED_HTML_ATTRIBUTES]
            for attr in attrs_to_remove:
                del tag.attrs[attr]

        # Recursively clean child tags only if the tag itself wasn't removed
        if tag.parent:
            # find_all(True) finds all tags
            for child in tag.find_all(True, recursive=False):
                _clean_tag_attributes(child)

    # Clean attributes from all remaining tags
    for tag in soup.find_all(True):
        _clean_tag_attributes(tag)

    # Get cleaned HTML and perform whitespace normalization
    cleaned_html = soup.prettify(formatter=None)
    # Consolidate whitespace
    cleaned_html = re.sub(r'\s+', ' ', cleaned_html).strip()
    # Remove space between tags
    cleaned_html = re.sub(r'>\s+<', '><', cleaned_html)
    # Remove space around content within tags (non-greedy)
    cleaned_html = re.sub(r'>\s+(.*?)\s+<', r'>\1<', cleaned_html)
    # Remove leading/trailing space within tags (handle remaining cases)
    cleaned_html = re.sub(r'>\s+(.*?)<', r'>\1<', cleaned_html)
    # Limit length (e.g., 400k chars) - adjust as needed
    max_len = 400000
    if len(cleaned_html) > max_len:
        logger.warning(
            f"Cleaned HTML length ({len(cleaned_html)}) exceeds max_len ({max_len}). Truncating.")
        cleaned_html = cleaned_html[:max_len]
    return cleaned_html


dotenv.load_dotenv()  # Load environment variables from .env file

# Initialize the Generative AI client (Gemini)
try:
    gemini_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
except Exception as e:
    logging.error(f"Failed to initialize Gemini client: {e}")
    gemini_client = None

# Initialize OpenAI client
try:
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception as e:
    logging.error(f"Failed to initialize OpenAI client: {e}")
    openai_client = None


# Configuration for the Gemini model (removed 'required', updated descriptions)
gemini_generate_content_config = types.GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=types.Schema(
        type=types.Type.OBJECT,
        # removed 'required' list
        properties={
            "net_profit": types.Schema(type=types.Type.NUMBER, description="Net profit or net income/loss for the reporting year in EUR. Negative for loss. Omit if unknown."),
            "mitarbeiter": types.Schema(type=types.Type.NUMBER, description="Average number of employees during the reporting year. Omit if unknown."),
            "umsatz": types.Schema(type=types.Type.NUMBER, description="Revenue for the reporting year in EUR. Omit if unknown."),
            "gewinnvortrag": types.Schema(type=types.Type.NUMBER, description="Profit/loss carried forward at the end of the reporting year in EUR. Negative for loss carried forward. Omit if unknown."),
            "bilanzsumme_total": types.Schema(type=types.Type.NUMBER, description="Total assets (or liabilities) at the end of the reporting year in EUR. Omit if unknown."),
            "schulden": types.Schema(type=types.Type.NUMBER, description="Total liabilities (debt) at the end of the reporting year in EUR. Omit if unknown."),
            "eigenkapital": types.Schema(type=types.Type.NUMBER, description="Equity at the end of the reporting year in EUR. Omit if unknown."),
            "guv_zinsen": types.Schema(type=types.Type.NUMBER, description="Interest expense or income (net) during the reporting year in EUR. Negative for interest expense. Omit if unknown."),
            "guv_steuern": types.Schema(type=types.Type.NUMBER, description="Income taxes for the reporting year in EUR. Omit if unknown."),
            "guv_abschreibungen": types.Schema(type=types.Type.NUMBER, description="Depreciation and amortization on intangible assets and property, plant, and equipment during the reporting year in EUR. Omit if unknown."),
            "cash": types.Schema(type=types.Type.NUMBER, description="Cash and cash equivalents (cash on hand, bank balances, checks) at the end of the reporting year in EUR. Omit if unknown."),
            "dividende": types.Schema(type=types.Type.NUMBER, description="Distribution or dividend for the reporting year in EUR. Often found under 'appropriation of profit' or 'distribution of results'. Omit if unknown.")
        },
    ),
    temperature=0.0,  # Set temperature to 0.0 for deterministic results
)


# Define the structure of the expected financial data (using Optional)
class FinancialData(TypedDict, total=False):  # total=False allows keys to be missing
    net_profit: Optional[float]
    mitarbeiter: Optional[float]
    umsatz: Optional[float]
    gewinnvortrag: Optional[float]
    bilanzsumme_total: Optional[float]
    schulden: Optional[float]
    eigenkapital: Optional[float]
    guv_zinsen: Optional[float]
    guv_steuern: Optional[float]
    guv_abschreibungen: Optional[float]
    cash: Optional[float]
    dividende: Optional[float]


# Define the keys we expect (used for parsing)
EXPECTED_KEYS = list(FinancialData.__annotations__.keys())

# Default structure for error cases (returning None instead of a dict with defaults)
# DEFAULT_FINANCIAL_DATA is no longer needed for filling missing values


def _parse_and_validate_data(raw_data: Dict[str, Any]) -> FinancialData:
    """Parses raw dictionary from AI and validates/converts types."""
    parsed_data: FinancialData = {}
    invalid_keys = []
    for key in EXPECTED_KEYS:
        value = raw_data.get(key)
        if value is None or value == 'null':  # Handle missing key or explicit null
            parsed_data[key] = None  # type: ignore
        elif isinstance(value, (int, float)):
            parsed_data[key] = float(value)  # type: ignore
        else:
            # Attempt conversion if it's a string representing a number, otherwise None
            try:
                # Handle potential formatting issues like thousand separators
                if isinstance(value, str):
                    value_str = value.replace('.', '').replace(
                        ',', '.')  # Assuming German format first
                    try:
                        parsed_data[key] = float(value_str)  # type: ignore
                    except ValueError:
                        # Try standard format if German fails
                        parsed_data[key] = float(value)  # type: ignore
                else:
                    parsed_data[key] = float(value)  # type: ignore
            except (ValueError, TypeError):
                logging.warning(
                    f"Could not convert value '{value}' for key '{key}' to float. Setting to None.")
                parsed_data[key] = None  # type: ignore
                invalid_keys.append(key)

    if invalid_keys:
        logging.warning(
            f"Found invalid types for keys: {invalid_keys}. Used None default.")

    return parsed_data


def _extract_financial_data_gemini(html_report: str) -> Optional[FinancialData]:
    """Analyzes a financial report (HTML) using the Gemini model."""
    if not gemini_client:
        logging.error("Gemini client not initialized. Cannot analyze report.")
        return None

    try:
        cleaned_report = clean_html_content(html_report)
        if not cleaned_report:
            logging.warning("HTML content is empty after cleaning.")
            return None

        prompt = f"{GEMINI_ANALYSIS_PROMPT}{cleaned_report}"
        contents = [
            types.Content(role="user", parts=[
                          types.Part.from_text(text=prompt)]),
        ]
        typed_contents = cast(types.ContentListUnion, contents)

        logging.info(f"Calling Gemini API with model: {GEMINI_MODEL_NAME}")
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL_NAME,
            contents=typed_contents,
            config=gemini_generate_content_config
        )

        if response.text is None:
            logging.warning("Received None response text from Gemini model.")
            # Log safety feedback if available
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                logging.warning(
                    f"Gemini request blocked. Reason: {response.prompt_feedback.block_reason}")
            if response.candidates and response.candidates[0].finish_reason != types.FinishReason.STOP:
                logging.warning(
                    f"Gemini generation finished unexpectedly. Reason: {response.candidates[0].finish_reason}")
            return None

        # Parse the JSON response
        financial_data_raw: Dict[str, Any] = json.loads(response.text)

        # Validate and structure the response
        financial_data = _parse_and_validate_data(financial_data_raw)

        # Log non-None values
        logging.info(
            f"Parsed financial data from Gemini: {json.dumps({k: v for k, v in financial_data.items() if v is not None}, indent=2)}")
        return financial_data

    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON from Gemini response: {e}")
        logging.error(
            f"Response text was: {response.text if 'response' in locals() and hasattr(response, 'text') else 'N/A'}")
        return None
    except Exception as e:
        logging.error(
            f"Error during Gemini financial data extraction: {e}", exc_info=True)
        return None


def _extract_financial_data_openai(html_report: str) -> Optional[FinancialData]:
    """Analyzes a financial report (HTML) using the OpenAI model."""
    if not openai_client:
        logging.error("OpenAI client not initialized. Cannot analyze report.")
        return None

    try:
        cleaned_report = clean_html_content(html_report)
        if not cleaned_report:
            logging.warning("HTML content is empty after cleaning.")
            return None

        prompt = f"{OPENAI_ANALYSIS_PROMPT}\n{cleaned_report}"

        # Estimate token count roughly (4 chars/token) and log if potentially too long
        estimated_tokens = len(prompt) / 4
        # gpt-4o-mini context window is 128k tokens, but setting a lower practical limit
        token_limit = 100000
        if estimated_tokens > token_limit:
            logging.warning(
                f"Estimated token count ({estimated_tokens:.0f}) exceeds practical limit ({token_limit}). API call might fail.")

        logging.info(f"Calling OpenAI API with model: {OPENAI_MODEL_NAME}")
        response = openai_client.chat.completions.create(
            model=OPENAI_MODEL_NAME,
            messages=[
                # System message is now part of the user prompt for simplicity here
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.0,  # For deterministic results
        )

        if not response.choices or not response.choices[0].message or not response.choices[0].message.content:
            logging.error(
                "Invalid response structure or empty content from OpenAI API.")
            # Log finish reason if available
            if response.choices and response.choices[0].finish_reason:
                logging.error(
                    f"OpenAI generation finish reason: {response.choices[0].finish_reason}")
            return None

        response_content = response.choices[0].message.content
        logging.debug(f"OpenAI API raw response content: {response_content}")

        # Parse the JSON response
        financial_data_raw: Dict[str, Any] = json.loads(response_content)

        # Validate and structure the response
        financial_data = _parse_and_validate_data(financial_data_raw)

        # Log non-None values
        logging.info(
            f"Parsed financial data from OpenAI: {json.dumps({k: v for k, v in financial_data.items() if v is not None}, indent=2)}")
        return financial_data

    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON from OpenAI response: {e}")
        logging.error(
            f"Response content was: {response_content if 'response_content' in locals() else 'N/A'}")
        return None
    except Exception as e:
        # Catch potential API errors (e.g., rate limits, invalid requests)
        logging.error(
            f"Error during OpenAI financial data extraction: {e}", exc_info=True)
        if "response" in locals() and hasattr(response, "choices") and response.choices and response.choices[0].message:
            logging.error(
                f"Response content: {response.choices[0].message.content}")
        return None


def extract_financial_data(html_report: str, provider: str = os.getenv("AI_PROVIDER") or "openai") -> Optional[FinancialData]:
    """
    Analyzes a financial report in HTML format using the specified AI provider.

    Cleans the HTML, sends it to the selected AI model with a specific prompt
    and schema/format requirements, and parses the JSON response containing
    extracted financial figures. Fields not found by the AI will be None.

    Args:
        html_report: The financial report as an HTML string.
        provider: The AI provider to use ('gemini' or 'openai').
                 Defaults to the AI_PROVIDER env var, or 'openai' if not set.

    Returns:
        A dictionary containing the extracted financial figures conforming to
        the FinancialData structure (with Optional[float] values), or None if
        the analysis fails, the provider is invalid, or the respective client
        is not initialized.
    """
    logger.info(
        f"Starting financial data extraction using provider: {provider}")

    if provider == 'gemini':
        return _extract_financial_data_gemini(html_report)
    elif provider == 'openai':
        return _extract_financial_data_openai(html_report)
    else:
        logging.error(
            f"Invalid AI provider specified: {provider}. Choose 'gemini' or 'openai'.")
        return None
