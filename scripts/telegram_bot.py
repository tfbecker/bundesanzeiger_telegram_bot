#!/usr/bin/env python3
import os
import logging
import json
import re
from typing import Optional, Union, cast, List, Dict, Any
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from openai import OpenAI
from openai.types.chat import ChatCompletionToolParam
from telegram_config import TELEGRAM_CONFIG
from bundesanzeiger import Bundesanzeiger
import requests
from bs4 import BeautifulSoup, Tag, NavigableString

# Define conversation states
SELECTING_REPORT = 1

# User session data to store reports between messages
user_sessions = {}

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Initialize Bundesanzeiger instance
bundesanzeiger = Bundesanzeiger()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    # Use effective_message which is more robust
    if update.effective_message:
        # Check if user is not None before accessing attributes
        user_name = user.first_name if user else "there"
        await update.effective_message.reply_text(
            f"Hi {user_name}! I'm your Bundesanzeiger Financial Bot. Send me a company name, and I'll fetch its financial data. "
            f"For example: 'Show me financial data for Deutsche Bahn AG' or just 'Siemens AG'."
        )
    else:
        logger.warning("Received /start command without an effective message.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    # Check if update.message is not None
    if update.message:
        # Use detailed help text
        await update.message.reply_text(
            "I can help you find financial information for German companies from the Bundesanzeiger.\n\n"
            "Just send me a message with the company name, like:\n"
            "- Show me data for Deutsche Bahn AG\n"
            "- Siemens AG financials\n"
            "- Holzland Becker Obertshausen\n\n"
            "I'll show you a list of available reports, and you can select one to view detailed financial information.\n\n"
            "Selection options:\n"
            "- Single report: Enter the number (e.g., '4')\n"
            "- Multiple reports: Enter a range (e.g., '4-6') or a comma-separated list (e.g., '4,7,13')\n"
            "- Latest report: Type 'latest'"
        )
    else:
        logger.warning("Received /help command without a message.")


def parse_message_with_openai(message_text: str) -> dict:
    """Use OpenAI with tool calling to parse the user message."""
    try:
        # Define the tool for company name extraction
        tools_data: List[Dict[str, Any]] = [  # Define type for clarity
            {
                "type": "function",
                "function": {
                    "name": "get_company_info",
                    "description": "Get financial information for a company from Bundesanzeiger",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "company_name": {
                                "type": "string",
                                "description": "The name of the company to search for"
                            }
                        },
                        "required": ["company_name"]
                    }
                }
            }
        ]
        # Cast the tools list to the expected type
        tools_param = cast(List[ChatCompletionToolParam], tools_data)

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that extracts company names from user messages. The user wants to get financial information about a company from the Bundesanzeiger database."},
                {"role": "user", "content": message_text}
            ],
            tools=tools_param,  # Use the casted variable
            tool_choice={"type": "function",
                         "function": {"name": "get_company_info"}}
        )

        if not response.choices or not response.choices[0].message or not response.choices[0].message.tool_calls:
            logger.error("Invalid response structure from OpenAI API.")
            return {"error": "Invalid response structure from OpenAI API"}

        tool_call = response.choices[0].message.tool_calls[0]
        if tool_call.function.name == "get_company_info" and tool_call.function.arguments:
            arguments = json.loads(tool_call.function.arguments)
            return {"company_name": arguments.get("company_name")}

        return {"error": "Failed to parse company name"}
    except Exception as e:
        logger.error(f"Error parsing message with OpenAI: {e}")
        return {"error": str(e)}


def format_financial_response(data: dict) -> str:
    """Format the financial data for the Telegram response."""
    if not data.get("found", False):
        return f"❌ No reports found for {data.get('company_name', 'the company')}."

    if "message" in data:
        return f"⚠️ {data.get('message', 'An error occurred')}"

    financial_data = data.get("financial_data", {})

    # Add a cache indicator emoji
    cache_indicator = "🔄 Fresh data" if not data.get(
        "is_cached", False) else "📋 Cached data"

    response = f"📊 *Financial information for {data.get('company_name', 'Unknown')}*\n\n"
    response += f"📅 Report date: {data.get('date', 'Unknown')}\n"
    response += f"📑 Report name: {data.get('report_name', 'Unknown')}\n"
    response += f"{cache_indicator}\n\n"

    # Format financial values with Euro symbol and thousand separators
    earnings = financial_data.get("earnings_current_year")
    if earnings is not None:
        response += f"💰 Earnings: {format_euro(earnings)}\n"
    else:
        response += "💰 Earnings: Not available\n"

    assets = financial_data.get("total_assets")
    if assets is not None:
        response += f"💼 Total assets: {format_euro(assets)}\n"
    else:
        response += "💼 Total assets: Not available\n"

    revenue = financial_data.get("revenue")
    if revenue is not None:
        response += f"📈 Revenue: {format_euro(revenue)}\n"
    else:
        response += "📈 Revenue: Not available\n"

    return response


def format_euro(value):
    """Format a number as Euro currency with thousand separators."""
    if value is None:
        return "N/A"
    try:
        return f"€{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return f"€{value}"


def find_all_financial_reports(company_name):
    """Find all financial reports for a company using direct search"""
    # Initialize session
    session = requests.Session()

    # Get the jsessionid cookie
    session.get("https://www.bundesanzeiger.de")

    # Go to the start page
    session.get("https://www.bundesanzeiger.de/pub/de/start?0")

    # Perform the search
    search_url = f"https://www.bundesanzeiger.de/pub/de/start?0-2.-top%7Econtent%7Epanel-left%7Ecard-form=&fulltext={company_name}&area_select=&search_button=Suchen"
    response = session.get(search_url)

    # Parse the HTML response
    soup = BeautifulSoup(response.text, "html.parser")
    result_container = soup.find("div", {"class": "result_container"})

    # Ensure result_container is a Tag before calling find_all
    if not result_container or not isinstance(result_container, Tag):
        logger.info("No result container found or it's not a valid tag.")
        return []  # No results found

    # List to store all reports
    all_reports = []

    # Find all report rows
    rows = result_container.find_all("div", {"class": "row"})

    # Process each row
    for row in rows:
        # Skip the header row
        if not row.find("div", {"class": "first"}):
            continue

        # Extract company name
        company_element = row.find("div", {"class": "first"})
        company = company_element.text.strip() if company_element else "Unknown"

        # Extract report info
        info_element = row.find("div", {"class": "info"})
        if info_element and info_element.find("a"):
            report_name = info_element.find("a").text.strip()
            report_link = info_element.find("a").get("href")

            # Store the original URL - this is a Wicket component reference
            original_link = report_link

            # For Wicket-based URLs, we need to use the original response
            # and the search page as context - store the search page URL
            search_page_url = response.url

            logger.info(
                f"Found report: {report_name} with link: {report_link}")
        else:
            continue  # Skip if no report link

        # Extract date
        date_element = row.find("div", {"class": "date"})
        date_str = date_element.text.strip() if date_element else ""

        # Convert date string to a comparable format (DD.MM.YYYY)
        date_comparable = date_str
        if date_str:
            # Try to extract the date in DD.MM.YYYY format for better sorting
            date_match = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', date_str)
            if date_match:
                day, month, year = date_match.groups()
                # Format as YYYY-MM-DD for proper sorting
                date_comparable = f"{year}-{month}-{day}"

        # Only include financial reports (check category)
        category_element = row.find("div", {"class": "area"})
        if category_element:
            category = category_element.text.strip()
            # Skip if not a financial report
            if "Rechnungslegung" not in category and "Finanzberichte" not in category:
                continue

        # Skip government organizations
        if any(keyword in company.lower() for keyword in [
            "ministerium", "bundesamt", "bundesanstalt", "behörde",
            "bundeswahlleiterin", "bundeswahlleiter"
        ]):
            continue

        # Add report to list
        all_reports.append({
            "company": company,
            "name": report_name,
            "date": date_str,
            "date_comparable": date_comparable,  # Add sortable date
            "link": report_link,
            "search_page_url": search_page_url,  # Store the search page URL
            "search_response": response,  # Store the search response
            "report": None,  # Will be fetched later if selected
        })

    # Store the session for later use
    for report in all_reports:
        report["session"] = session

    # Filter reports by company name similarity
    if all_reports:
        company_keywords = company_name.lower().split()
        for report in all_reports:
            # Calculate match score
            match_score = 0
            for keyword in company_keywords:
                if len(keyword) > 3 and keyword.lower() in report["company"].lower():
                    match_score += 1
            report["match_score"] = match_score

        # Filter to only show reports with good match score
        matching_reports = [
            r for r in all_reports if r.get("match_score", 0) > 0]

        # If no good matches, just use all reports
        if not matching_reports:
            matching_reports = all_reports

        # Sort by date (newest first) using the comparable date format
        sorted_reports = sorted(matching_reports, key=lambda x: (
            x.get("date_comparable", ""),  # Primary sort by date
            x.get("match_score", 0)        # Secondary sort by match score
        ), reverse=True)

        return sorted_reports

    return []


async def split_and_send_long_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, max_length: int = 4000, **kwargs) -> None:
    """Split a long message into smaller chunks and send them sequentially."""
    # Check if update.message exists before replying
    if not update.message:
        logger.warning(
            "split_and_send_long_message called without update.message")
        return

    if len(text) <= max_length:
        await update.message.reply_text(text, **kwargs)
        return

    # Split the text into chunks
    chunks = []
    current_chunk = ""
    lines = text.split('\n')

    for line in lines:
        if len(current_chunk) + len(line) + 1 > max_length:
            chunks.append(current_chunk)
            current_chunk = line
        else:
            if current_chunk:
                current_chunk += '\n' + line
            else:
                current_chunk = line

    if current_chunk:
        chunks.append(current_chunk)

    # Send each chunk as a separate message
    for i, chunk in enumerate(chunks):
        # Check update.message again for the first chunk
        if i == 0 and update.message:
            await update.message.reply_text(chunk, **kwargs)
        else:
            # Check effective_chat before sending subsequent messages
            if update.effective_chat:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=chunk,
                    **kwargs
                )
            else:
                logger.warning(
                    "split_and_send_long_message: effective_chat is None, cannot send message chunk.")

# Change return type hint to Optional[int] for conversation handler state


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """Process user messages and respond with a list of available reports."""
    # Ensure message and text exist
    if not update.message or not update.message.text:
        logger.warning(
            "handle_message received update without message or text.")
        return None  # Or ConversationHandler.END if appropriate

    message_text = update.message.text

    # Ensure user and chat exist before accessing IDs
    if not update.effective_user:
        logger.warning(
            "handle_message received update without effective_user.")
        return None
    user_id = update.effective_user.id

    if not update.effective_chat:
        logger.warning(
            "handle_message received update without effective_chat.")
        return None
    chat_id = update.effective_chat.id

    # Check if user is in report selection mode
    if user_id in user_sessions and 'reports' in user_sessions[user_id]:
        # Delegate to handle_report_selection, which also needs checks
        selection_result = await handle_report_selection(update, context)
        # Ensure handle_report_selection returns the correct type
        return selection_result if isinstance(selection_result, int) else None

    # Send a typing indicator while processing
    await context.bot.send_chat_action(
        chat_id=chat_id, action="typing"
    )

    # Use OpenAI to parse the message
    parsed_message = parse_message_with_openai(message_text)

    if "error" in parsed_message:
        # Check update.message before replying
        if update.message:
            await update.message.reply_text(
                f"Sorry, I couldn't process your request: {parsed_message['error']}"
            )
        return None

    company_name = parsed_message.get("company_name")

    if not company_name:
        # Check update.message before replying
        if update.message:
            await update.message.reply_text(
                "I couldn't identify a company name in your message. Please try again with a clear company name."
            )
        return None

    # Let the user know we're working on it
    # Check update.message before replying
    if update.message:
        await update.message.reply_text(
            f"Looking for financial reports for *{company_name}*... This may take a moment.",
            parse_mode="Markdown"
        )

    try:
        # Find all financial reports
        all_reports = find_all_financial_reports(company_name)

        if not all_reports:
            # Check update.message before replying
            if update.message:
                await update.message.reply_text(
                    f"❌ No financial reports found for '{company_name}' in the Bundesanzeiger database.",
                    parse_mode="Markdown"
                )
            return None

        # Debug: log the reports that were found
        logger.info(f"Found {len(all_reports)} reports for {company_name}")
        for i, report in enumerate(all_reports):
            logger.info(
                f"Report {i+1}: {report.get('date')} - {report.get('company')} - {report.get('name')}")

        # Store the reports in the user's session
        # Ensure user_id is valid (checked above)
        user_sessions[user_id] = {
            'original_query': company_name,  # Store the original query for re-searching
            'reports': all_reports
        }

        # Format report options
        report_options = f"📋 I found {len(all_reports)} financial reports. Please select one by typing the number:\n\n"
        for i, report in enumerate(all_reports, 1):
            company = report.get("company", "Unknown")
            date = report.get("date", "Unknown date")
            name = report.get("name", "Unknown report")
            report_options += f"{i}) {date} - {company}: {name}\n"

        report_options += "\nSelect options:\n"
        report_options += "• Single report: Enter the number (e.g., '4')\n"
        report_options += "• Multiple reports: Enter a range (e.g., '4-6') or comma-separated list (e.g., '4,7,13')\n"
        report_options += "• Latest report: Type 'latest'"

        # Use the helper function to send potentially long messages
        await split_and_send_long_message(update, context, report_options)
        return SELECTING_REPORT  # Return state

    except Exception as e:
        logger.error(f"Error fetching reports: {e}", exc_info=True)

        # Provide a more specific error message
        error_message = "Sorry, an error occurred while fetching the data."
        if "NoneType" in str(e):
            error_message = f"😕 I couldn't find any information for *{company_name}* in the Bundesanzeiger database. Please check the spelling or try a different company name."
        elif "connection" in str(e).lower() or "timeout" in str(e).lower():
            error_message = "🌐 There seems to be a connection issue with the Bundesanzeiger website. Please try again later."
        else:
            error_message = f"❌ An unexpected error occurred: {str(e)}. Please try again later or with a different company name."

        # Check update.message before replying
        if update.message:
            await update.message.reply_text(
                error_message,
                parse_mode="Markdown"
            )
        return None  # Indicate error or end conversation

# Change return type hint to Optional[int]


async def handle_report_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """Handle user's selection of a specific report."""
    # Ensure user, message, and text exist
    if not update.effective_user:
        logger.warning(
            "handle_report_selection received update without effective_user.")
        # Treat as new query if user missing
        return await handle_message(update, context)

    user_id = update.effective_user.id

    if not update.message or not update.message.text:
        logger.warning(
            "handle_report_selection received update without message or text.")
        if user_id in user_sessions:
            del user_sessions[user_id]  # Clear potentially invalid session
        return await handle_message(update, context)  # Treat as new query

    text = update.message.text.strip()

    if not update.effective_chat:
        logger.warning(
            "handle_report_selection received update without effective_chat.")
        if user_id in user_sessions:
            del user_sessions[user_id]
        return None  # Cannot proceed without chat

    chat_id = update.effective_chat.id

    if user_id not in user_sessions or 'reports' not in user_sessions[user_id]:
        # No active session, treat as new query
        return await handle_message(update, context)

    session = user_sessions[user_id]
    reports = session['reports']

    # Initialize selected_indices
    selected_indices = []

    # Handle "latest" shortcut
    if text.lower() == 'latest':
        selected_indices = [0]  # First report (already sorted newest first)
        logger.info(f"User selected 'latest' report (index 0)")
    else:
        # Parse the selection (single number, range, or comma-separated list)

        # Handle comma-separated values: "4,7,13"
        if "," in text:
            parts = text.split(",")
            for part in parts:
                try:
                    index = int(part.strip()) - 1
                    if 0 <= index < len(reports):
                        selected_indices.append(index)
                    else:
                        # Check update.message before replying
                        if update.message:
                            await update.message.reply_text(
                                f"Invalid selection: {part.strip()}. Please select numbers between 1 and {len(reports)}."
                            )
                        return SELECTING_REPORT
                except ValueError:
                    # Check update.message before replying
                    if update.message:
                        await update.message.reply_text(
                            f"Invalid selection format: '{part.strip()}'. Please enter numbers only."
                        )
                    return SELECTING_REPORT
        # Handle range: "4-6"
        elif "-" in text:
            try:
                start, end = map(str.strip, text.split("-"))
                start_index = int(start) - 1
                end_index = int(end) - 1

                if start_index < 0 or end_index >= len(reports) or start_index > end_index:
                    # Check update.message before replying
                    if update.message:
                        await update.message.reply_text(
                            f"Invalid range: {text}. Please select a valid range between 1 and {len(reports)}."
                        )
                    return SELECTING_REPORT

                selected_indices = list(range(start_index, end_index + 1))
            except ValueError:
                # Check update.message before replying
                if update.message:
                    await update.message.reply_text(
                        f"Invalid range format: '{text}'. Please use format like '4-6'."
                    )
                return SELECTING_REPORT
        # Handle single number: "4"
        else:
            try:
                selected_index = int(text) - 1
                logger.info(
                    f"User selected report #{text} (index {selected_index})")
                if selected_index < 0 or selected_index >= len(reports):
                    # Check update.message before replying
                    if update.message:
                        await update.message.reply_text(
                            f"Please select a number between 1 and {len(reports)}."
                        )
                    return SELECTING_REPORT
                selected_indices = [selected_index]
            except ValueError:
                # Not a number or "latest", treat as new query
                logger.info(
                    f"User entered '{text}' which is not a valid report selection, treating as new query")
                if user_id in user_sessions:
                    del user_sessions[user_id]  # Clear session
                return await handle_message(update, context)

    # Validate we have at least one valid selection
    if not selected_indices:
        # Check update.message before replying
        if update.message:
            await update.message.reply_text("No valid report selections found. Please try again.")
        return SELECTING_REPORT

    # Log the selected reports
    report_ids = [i+1 for i in selected_indices]
    logger.info(f"Processing selected reports: {report_ids}")

    # Send typing indicator
    await context.bot.send_chat_action(
        chat_id=chat_id, action="typing"
    )

    # Process each selected report
    all_responses = []

    for selected_index in selected_indices:
        # Get the selected report
        selected_report = reports[selected_index]
        logger.info(
            f"Processing report: {selected_report.get('company')} - {selected_report.get('name')} - {selected_report.get('date')}")

        try:
            # Get the full report content if not already fetched
            if not selected_report.get("report"):
                # Use the session that was used for search
                if "session" not in selected_report:
                    logger.error("No session available for this report")
                    raise ValueError(
                        "No session available for report fetching")

                # Get the link from the report
                link = selected_report.get("link")
                if not link:
                    logger.error(
                        "No report link available in the selected report")
                    raise ValueError("No report link available")

                # Use the original session from the search
                report_session = selected_report["session"]

                # First, ensure our session is still valid by hitting the main page again
                logger.info("Refreshing session with Bundesanzeiger website")
                report_session.get("https://www.bundesanzeiger.de")
                report_session.get(
                    "https://www.bundesanzeiger.de/pub/de/start?0")

                # Perform the search again to ensure we're in the right context
                search_url = f"https://www.bundesanzeiger.de/pub/de/start?0-2.-top%7Econtent%7Epanel-left%7Ecard-form=&fulltext={session['original_query']}&area_select=&search_button=Suchen"
                logger.info(
                    f"Re-running search to establish context: {search_url}")
                search_response = report_session.get(search_url)

                # Now use the click URL (which is a relative Wicket URL)
                logger.info(f"Clicking on report link: {link}")

                # Use search page as base if this is a relative URL
                if not link.startswith('http'):
                    search_page_url = search_response.url
                    if '?' in search_page_url:
                        base_url = search_page_url.split('?')[0]
                    else:
                        base_url = search_page_url

                    if link.startswith('?'):
                        full_link = base_url + link
                    else:
                        full_link = base_url + '?' + link
                else:
                    full_link = link

                logger.info(f"Final URL for report: {full_link}")

                # Fetch the report content
                response = report_session.get(full_link)

                logger.info(f"Response status code: {response.status_code}")
                logger.debug(f"Response headers: {response.headers}")

                # Save the HTML for debugging
                with open(f"report_response_{selected_index}.html", "w") as f:
                    f.write(response.text)
                logger.info(
                    f"Saved HTML response to report_response_{selected_index}.html for analysis")

                # Extract the report content
                soup = BeautifulSoup(response.text, "html.parser")
                content_element = soup.find(
                    "div", {"class": "publication_container"})

                if not content_element:
                    logger.warning(
                        "No content element found, checking for captcha")
                    captcha_wrapper = soup.find(
                        "div", {"class": "captcha_wrapper"})
                    if captcha_wrapper:
                        logger.info("Captcha detected, attempting to solve")
                        captcha_img = captcha_wrapper.find("img")
                        # Check if captcha_img is a Tag and has 'src'
                        if isinstance(captcha_img, Tag) and captcha_img.has_attr('src'):
                            captcha_src = captcha_img.get("src")
                            # Ensure captcha_src is a string
                            if isinstance(captcha_src, str):
                                if not captcha_src.startswith('http'):
                                    if captcha_src.startswith('/'):
                                        captcha_src = f"https://www.bundesanzeiger.de{captcha_src}"
                                    else:
                                        captcha_src = f"https://www.bundesanzeiger.de/pub/de/{captcha_src}"

                                logger.info(
                                    f"Full captcha image URL: {captcha_src}")
                                img_response = report_session.get(captcha_src)

                                form = soup.find("form", {"id": "captchaForm"}) or (
                                    soup.find_all("form")[1] if len(soup.find_all("form")) > 1 else None)
                                # Check if form is a Tag and has 'action'
                                if isinstance(form, Tag) and form.has_attr('action'):
                                    captcha_url = form.get("action")
                                    # Ensure captcha_url is a string
                                    if isinstance(captcha_url, str):
                                        if not captcha_url.startswith('http'):
                                            if captcha_url.startswith('/'):
                                                captcha_url = f"https://www.bundesanzeiger.de{captcha_url}"
                                            else:
                                                captcha_url = f"https://www.bundesanzeiger.de/pub/de/{captcha_url}"

                                        logger.info(
                                            f"Captcha form action URL: {captcha_url}")

                                        if not hasattr(bundesanzeiger, 'captcha_callback'):
                                            from bundesanzeiger import Bundesanzeiger
                                            captcha_handler = Bundesanzeiger()
                                            captcha_solution = captcha_handler.captcha_callback(
                                                img_response.content)
                                        else:
                                            captcha_solution = bundesanzeiger.captcha_callback(
                                                img_response.content)

                                        logger.info(
                                            f"Generated captcha solution: {captcha_solution}")

                                        captcha_data = {
                                            "solution": captcha_solution, "confirm-button": "OK"}
                                        logger.info(
                                            f"Submitting captcha data: {captcha_data}")
                                        response = report_session.post(
                                            captcha_url, data=captcha_data)

                                        with open(f"captcha_response_{selected_index}.html", "w") as f:
                                            f.write(response.text)
                                        logger.info(
                                            f"Saved captcha response to captcha_response_{selected_index}.html")

                                        soup = BeautifulSoup(
                                            response.text, "html.parser")
                                        content_element = soup.find(
                                            "div", {"class": "publication_container"})
                                    else:
                                        logger.error(
                                            "Captcha form action attribute is not a string.")
                                        raise ValueError(
                                            "Invalid captcha form action attribute.")
                                else:
                                    logger.error(
                                        "Could not find captcha form tag or 'action' attribute.")
                                    raise ValueError(
                                        "Could not find captcha form.")
                            else:
                                logger.error(
                                    "Captcha image src attribute is not a string.")
                                raise ValueError(
                                    "Invalid captcha image source attribute.")
                        else:
                            logger.error(
                                "Could not find captcha image tag or 'src' attribute.")
                            raise ValueError("Could not find captcha image.")
                    else:
                        # Look for alternative content areas
                        logger.warning(
                            "No captcha detected, looking for alternative content elements")
                        possible_content_elements = [
                            soup.find("div", {"class": "content"}),
                            soup.find("div", {"id": "content"}),
                            soup.find("div", {"class": "details"}),
                            soup.find("div", {"id": "details"})
                        ]
                        for element in possible_content_elements:
                            if element:
                                content_element = element
                                logger.info(
                                    f"Found alternative content element: {element.name}")
                                break

                # Extract text content with checks
                if content_element:
                    if isinstance(content_element, Tag):
                        report_text_content = content_element.text
                    elif isinstance(content_element, NavigableString):
                        report_text_content = str(content_element)
                    else:
                        report_text_content = "Could not extract text from content element."
                        logger.error(
                            f"content_element is of unexpected type: {type(content_element)}")

                    logger.info(
                        f"Successfully extracted report content. Length: {len(report_text_content)} characters")
                    selected_report["report"] = report_text_content
                else:
                    logger.error("Failed to extract report content")
                    body_text = soup.find("body")
                    if body_text:
                        logger.info("Using body text as fallback")
                        selected_report["report"] = body_text.text
                    else:
                        selected_report["report"] = "Could not retrieve report content"
            else:
                logger.info(
                    "Report content already fetched, using cached content")

            # Process the report to extract financial data
            report_text = selected_report.get("report", "")
            logger.info(
                f"Starting financial data extraction for report: {selected_report.get('name')}")
            financial_data = process_financial_data(report_text)

            # Format the response data
            response_data = {
                "company_name": selected_report.get("company", "Unknown"),
                "found": True,
                "date": selected_report.get("date", "Unknown"),
                "report_name": selected_report.get("name", "Unknown"),
                "financial_data": financial_data
            }

            # Format the response
            response = format_financial_response(response_data)
            logger.info(
                f"Processed report {selected_index+1}, appending to responses")

            # Add a header to identify this report in multi-select mode
            if len(selected_indices) > 1:
                report_num = selected_index + 1
                response = f"📊 *Report #{report_num}*\n" + response

            all_responses.append(response)

        except Exception as e:
            logger.error(
                f"Error processing report {selected_index+1}: {e}", exc_info=True)
            error_response = f"Sorry, an error occurred while processing report #{selected_index+1}: {str(e)}"
            all_responses.append(error_response)

    # Send all collected responses
    if len(all_responses) == 1:
        # Single report, send as is
        await split_and_send_long_message(update, context, all_responses[0], parse_mode="Markdown")
    else:
        # Multiple reports, send each with a separator
        for i, response in enumerate(all_responses):
            # Add separator between reports
            if i > 0:
                # Check update.message before replying
                if update.message:
                    await update.message.reply_text("---")

            await split_and_send_long_message(update, context, response, parse_mode="Markdown")

    # Clear the session data (check before deleting)
    if user_id in user_sessions:
        del user_sessions[user_id]
    return ConversationHandler.END  # End conversation


def process_financial_data(text):
    """Process report text to extract financial data using OpenAI."""
    try:
        # Limit text length to avoid token limit issues
        max_length = 400000  # Approximating 100K tokens (4 chars per token)
        if len(text) > max_length:
            sample_text = text[:500] + "..."  # Sample for logging
            text = text[:max_length] + "..."
            logger.info(
                f"Report text truncated to {max_length} characters. Sample: {sample_text}")
        else:
            sample_text = text[:500] + "..."  # Sample for logging
            logger.info(
                f"Processing report text. Length: {len(text)} characters. Sample: {sample_text}")

        logger.info(
            f"Calling OpenAI API with model: o3-mini to extract financial data")
        response = client.chat.completions.create(
            model="o3-mini",  # Using o3-mini with larger context window
            messages=[
                {"role": "system", "content": "You are an accounting specialist. Extract financial data from German company reports. Only respond with JSON."},
                {"role": "user", "content": """You are analyzing public financial information from a company. 
                Extract and return ONLY the following information in a JSON format:
                - earnings_current_year (in EUR)
                - total_assets (in EUR)
                - revenue (in EUR)
                
                If a value cannot be found, use null.
                Only return the JSON object, nothing else.
                Example output: {"earnings_current_year": 1000000, "total_assets": 5000000, "revenue": null}
                
                Here's the financial information:
                """ + text}
            ],
            response_format={"type": "json_object"}
        )

        # Log the raw response from OpenAI
        # Check response structure before accessing content
        if not response.choices or not response.choices[0].message or not response.choices[0].message.content:
            logger.error(
                "Invalid response structure or empty content from OpenAI API.")
            return {  # Return default structure on error
                "earnings_current_year": None,
                "total_assets": None,
                "revenue": None
            }

        response_content = response.choices[0].message.content
        logger.info(f"OpenAI API response content: {response_content}")

        # Parse the JSON response
        financial_data = json.loads(response_content)
        logger.info(
            f"Parsed financial data: {json.dumps(financial_data, indent=2)}")
        return financial_data
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from OpenAI response: {e}")
        logger.error(
            f"Response content was: {response_content if 'response_content' in locals() else 'N/A'}")
        return {  # Return default structure on error
            "earnings_current_year": None,
            "total_assets": None,
            "revenue": None
        }
    except Exception as e:
        logger.error(f"Error processing financial data: {e}")
        if "response" in locals() and hasattr(response, "choices") and response.choices and response.choices[0].message:
            logger.error(
                f"Response content: {response.choices[0].message.content}")
        return {
            "earnings_current_year": None,
            "total_assets": None,
            "revenue": None
        }


def main() -> None:
    """Start the bot."""
    # Configure more detailed logging
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
        handlers=[
            logging.FileHandler("telegram_bot.log"),
            logging.StreamHandler()
        ]
    )

    # Set specific module logging levels
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.INFO)
    logging.getLogger("__main__").setLevel(logging.DEBUG)

    logger.info("Starting Bundesanzeiger Telegram Bot")

    # Get bot token and check if it exists
    bot_token = TELEGRAM_CONFIG.get('BOT_TOKEN')
    if not bot_token:
        logger.critical("BOT_TOKEN not found in telegram_config.py. Exiting.")
        return  # Or raise an exception

    # Create the Application
    application = Application.builder().token(bot_token).build()

    # Add conversation handler for report selection
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(
            filters.TEXT & ~filters.COMMAND, handle_message)],
        states={
            SELECTING_REPORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_report_selection)],
        },
        fallbacks=[],
    )

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(conv_handler)  # Add the conversation handler

    # Run the bot until the user presses Ctrl-C
    logger.info("Bot is running. Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
