#!/usr/bin/env python3
import os
import logging
import json
import re
import io
import matplotlib.pyplot as plt
import matplotlib
import numpy as np
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from telegram_config import TELEGRAM_CONFIG
from bundesanzeiger import Bundesanzeiger, Report, FinancialDataCache
from datetime import datetime
from collections import defaultdict
import requests
from bs4 import BeautifulSoup

# Set matplotlib to non-interactive mode since we're running headless
matplotlib.use('Agg')

# Define conversation states
SELECTING_REPORT = 1
CONFIRMING_TIMELINE = 2

# User session data to store reports between messages
user_sessions = {}

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# OpenRouter API configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

# Initialize Bundesanzeiger instance
bundesanzeiger = Bundesanzeiger()

# Initialize database cache
db_cache = FinancialDataCache(os.getenv('DB_PATH', "financial_cache.db"))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_text(
        f"Hi {user.first_name}! I'm your Bundesanzeiger Financial Bot. Send me a company name, and I'll fetch its financial data. "
        f"For example: 'Show me financial data for Deutsche Bahn AG' or just 'Siemens AG'."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
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
        "- Latest report: Type 'latest'\n"
        "- Financial timeline: Type 'timeline 10' to analyze up to 10 reports\n"
        "- Specific reports timeline: Type 'timeline 10 1,2,5,6' or 'timeline 10 1-4'\n"
        "- Filter by company: Type 'timeline 10 HolzLand Becker GmbH'\n"
        "- Timeline for specific report: '2 timeline 10' for a specific company\n"
        "The timeline analysis examines financial trends over time and generates graphs."
    )

def parse_message_with_deepseek(message_text: str) -> dict:
    """Use DeepSeek via OpenRouter with tool calling to parse the user message."""
    try:
        # Define the tool for company name extraction
        tools = [
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

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/yourusername/bundesanzeiger_telegram_bot",  # Replace with your repo
            "X-Title": "Bundesanzeiger Telegram Bot"
        }

        payload = {
            "model": "deepseek/deepseek-chat-v3-0324",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant that extracts company names from user messages. The user wants to get financial information about a company from the Bundesanzeiger database."},
                {"role": "user", "content": message_text}
            ],
            "tools": tools,
            "tool_choice": {"type": "function", "function": {"name": "get_company_info"}}
        }

        response = requests.post(OPENROUTER_BASE_URL, json=payload, headers=headers)
        response.raise_for_status()
        
        response_data = response.json()
        tool_call = response_data["choices"][0]["message"]["tool_calls"][0]
        
        if tool_call["function"]["name"] == "get_company_info":
            arguments = json.loads(tool_call["function"]["arguments"])
            return {"company_name": arguments.get("company_name")}
        
        return {"error": "Failed to parse company name"}
    except Exception as e:
        logger.error(f"Error parsing message with DeepSeek: {e}")
        return {"error": str(e)}

def format_financial_response(data: dict) -> str:
    """Format the financial data for the Telegram response."""
    if not data.get("found", False):
        return f"❌ No reports found for {data.get('company_name', 'the company')}."
    
    if "message" in data:
        return f"⚠️ {data.get('message', 'An error occurred')}"
    
    financial_data = data.get("financial_data", {})
    
    # Add a cache indicator emoji
    cache_indicator = "🔄 Fresh data" if not data.get("is_cached", False) else "📋 Cached data"
    
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
    
    if not result_container:
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
            
            logger.info(f"Found report: {report_name} with link: {report_link}")
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
                date_comparable = f"{year}-{month}-{day}"  # Format as YYYY-MM-DD for proper sorting
        
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
        matching_reports = [r for r in all_reports if r.get("match_score", 0) > 0]
        
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
        if i == 0:
            await update.message.reply_text(chunk, **kwargs)
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=chunk,
                **kwargs
            )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages."""
    message_text = update.message.text.strip()
    user_id = update.effective_user.id
    
    # Check if the user has active reports
    user_data = context.user_data
    
    # Check if this is a direct timeline command
    timeline_match = re.match(r'^timeline\s+(\d+)$', message_text, re.IGNORECASE)
    if timeline_match and 'reports' in user_data and user_data['reports']:
        max_reports = int(timeline_match.group(1))
        entity_name = user_data.get('original_query', 'Unknown')
        await handle_timeline_analysis_with_reports(update, context, entity_name, max_reports, user_data['reports'])
        return
        
    # Check if the user has active reports and is selecting one
    if 'reports' in user_data and user_data['reports']:
        return await handle_report_selection(update, context)

    # Send a typing indicator while processing
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )
    
    # Use DeepSeek via OpenRouter to parse the message
    parsed_message = parse_message_with_deepseek(message_text)
    
    if "error" in parsed_message:
        await update.message.reply_text(
            f"Sorry, I couldn't process your request: {parsed_message['error']}"
        )
        return
    
    company_name = parsed_message.get("company_name")
    
    if not company_name:
        await update.message.reply_text(
            "I couldn't identify a company name in your message. Please try again with a clear company name."
        )
        return
    
    # Let the user know we're working on it
    await update.message.reply_text(
        f"Looking for financial reports for *{company_name}*... This may take a moment.",
        parse_mode="Markdown"
    )
    
    try:
        # Find all financial reports
        all_reports = find_all_financial_reports(company_name)
        
        if not all_reports:
            await update.message.reply_text(
                f"❌ No financial reports found for '{company_name}' in the Bundesanzeiger database.",
                parse_mode="Markdown"
            )
            return
        
        # Debug: log the reports that were found
        logger.info(f"Found {len(all_reports)} reports for {company_name}")
        for i, report in enumerate(all_reports):
            logger.info(f"Report {i+1}: {report.get('date')} - {report.get('company')} - {report.get('name')}")
        
        # Store the reports in the user's context data
        context.user_data['original_query'] = company_name
        context.user_data['reports'] = all_reports
        
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
        report_options += "• Latest report: Type 'latest'\n"
        report_options += "• Financial timeline: Type 'timeline 10' to analyze up to 10 reports\n"
        report_options += "• Specific reports timeline: Type 'timeline 10 1,2,5,6' or 'timeline 10 1-4'\n"
        report_options += "• Filter by company: Type 'timeline 10 HolzLand Becker GmbH'\n"
        report_options += "• Timeline for specific report: '2 timeline 10' for a specific company\n"
        report_options += "The timeline analysis examines financial trends over time and generates graphs."
        
        # Use the helper function to send potentially long messages
        await split_and_send_long_message(update, context, report_options)
        return SELECTING_REPORT
        
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
        
        await update.message.reply_text(
            error_message,
            parse_mode="Markdown"
        )

async def handle_report_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle user's selection of a specific report."""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if 'reports' not in context.user_data:
        # No active session, treat as new query
        return await handle_message(update, context)
    
    reports = context.user_data['reports']
    original_query = context.user_data.get('original_query', 'Unknown')
    
    # Check for timeline command with company name filter (e.g., 'timeline 10 company:"HolzLand Becker GmbH Obertshausen"')
    company_timeline_match = re.match(r'^timeline\s+(\d+)\s+company:"([^"]+)"$', text, re.IGNORECASE)
    if company_timeline_match:
        max_reports = int(company_timeline_match.group(1))
        company_filter = company_timeline_match.group(2).strip()
        
        # Normalize company names and the filter
        def normalize_company_name(name):
            # Replace newlines and multiple spaces with single spaces
            return re.sub(r'\s+', ' ', name).strip().lower()
        
        normalized_filter = normalize_company_name(company_filter)
        logger.info(f"Filtering reports for company name containing: '{normalized_filter}'")
        
        # Filter reports by company name
        filtered_reports = []
        for report in reports:
            company_name = report.get("company", "")
            normalized_name = normalize_company_name(company_name)
            
            # Check if filter is a substring of the normalized company name
            if normalized_filter in normalized_name:
                filtered_reports.append(report)
                logger.info(f"Matched report with company: '{company_name}' (normalized: '{normalized_name}')")
        
        if not filtered_reports:
            await update.message.reply_text(
                f"❌ No reports found with company name containing '{company_filter}'.",
                parse_mode="Markdown"
            )
            return SELECTING_REPORT
        
        # Limit to max_reports
        if len(filtered_reports) > max_reports:
            filtered_reports = filtered_reports[:max_reports]
        
        # Get the matched company name for better user feedback
        first_company = filtered_reports[0].get("company", "").replace("\n", " ").strip()
        
        # Store selected reports for confirmation
        context.user_data['timeline_data'] = {
            'entity_name': first_company,
            'max_reports': max_reports,
            'selected_reports': filtered_reports
        }
        
        # Ask for confirmation
        await update.message.reply_text(
            f"Selected {len(filtered_reports)} reports for company *{first_company}* - Continue? (Yes/No)",
            parse_mode="Markdown"
        )
        
        return CONFIRMING_TIMELINE
    
    # Check for advanced timeline command with simple text as company name filter (e.g., "timeline 10 HolzLand Becker")
    simple_company_match = re.match(r'^timeline\s+(\d+)\s+([a-zA-Z].+)$', text, re.IGNORECASE)
    if simple_company_match:
        max_reports = int(simple_company_match.group(1))
        company_text = simple_company_match.group(2).strip()
        
        # If the text can be parsed as report selection (numbers, ranges, etc.), don't process as company name
        if re.match(r'^[\d,\- ]+$', company_text):
            # This looks like a report selection, not a company name
            # Let the next condition handle it
            pass
        else:
            # This is a company name filter
            logger.info(f"Using text as company filter: '{company_text}'")
            
            # Normalize company names and the filter
            def normalize_company_name(name):
                # Replace newlines and multiple spaces with single spaces
                return re.sub(r'\s+', ' ', name).strip().lower()
            
            normalized_filter = normalize_company_name(company_text)
            
            # Filter reports by company name
            filtered_reports = []
            for report in reports:
                company_name = report.get("company", "")
                normalized_name = normalize_company_name(company_name)
                
                # Check if filter is a substring of the normalized company name
                if normalized_filter in normalized_name:
                    filtered_reports.append(report)
                    logger.info(f"Matched report with company: '{company_name}' (normalized: '{normalized_name}')")
            
            if not filtered_reports:
                await update.message.reply_text(
                    f"❌ No reports found with company name containing '{company_text}'.",
                    parse_mode="Markdown"
                )
                return SELECTING_REPORT
            
            # Limit to max_reports
            if len(filtered_reports) > max_reports:
                filtered_reports = filtered_reports[:max_reports]
            
            # Get the matched company name for better user feedback
            first_company = filtered_reports[0].get("company", "").replace("\n", " ").strip()
            
            # Store selected reports for confirmation
            context.user_data['timeline_data'] = {
                'entity_name': first_company,
                'max_reports': max_reports,
                'selected_reports': filtered_reports
            }
            
            # Ask for confirmation
            await update.message.reply_text(
                f"Selected {len(filtered_reports)} reports for company *{first_company}* - Continue? (Yes/No)",
                parse_mode="Markdown"
            )
            
            return CONFIRMING_TIMELINE
    
    # Check for advanced timeline command (e.g., "timeline 10 1,2,5,6" or "timeline 10 1-4 5,6")
    advanced_timeline_match = re.match(r'^timeline\s+(\d+)\s+(.+)$', text, re.IGNORECASE)
    if advanced_timeline_match:
        max_reports = int(advanced_timeline_match.group(1))
        selection_text = advanced_timeline_match.group(2)
        
        # Parse the selection (can include numbers, ranges with dash, comma-separated values, and spaces)
        selected_indices = []
        for part in selection_text.split():
            # Handle comma-separated values within each part: "1,2,5,6"
            if "," in part:
                for subpart in part.split(","):
                    if not subpart:  # Skip empty parts (e.g., trailing comma)
                        continue
                    # Handle ranges within comma: "1-3,5-7"
                    if "-" in subpart:
                        try:
                            start, end = map(str.strip, subpart.split("-"))
                            start_index = int(start) - 1
                            end_index = int(end) - 1
                            
                            if start_index < 0 or end_index >= len(reports) or start_index > end_index:
                                await update.message.reply_text(
                                    f"Invalid range: {subpart}. Please select a valid range between 1 and {len(reports)}."
                                )
                                return SELECTING_REPORT
                            
                            selected_indices.extend(list(range(start_index, end_index + 1)))
                        except ValueError:
                            await update.message.reply_text(
                                f"Invalid range format: '{subpart}'. Please use format like '1-3'."
                            )
                            return SELECTING_REPORT
                    else:
                        # Handle single numbers within comma: "1,3,5"
                        try:
                            index = int(subpart.strip()) - 1
                            if 0 <= index < len(reports):
                                selected_indices.append(index)
                            else:
                                await update.message.reply_text(
                                    f"Invalid selection: {subpart.strip()}. Please select numbers between 1 and {len(reports)}."
                                )
                                return SELECTING_REPORT
                        except ValueError:
                            await update.message.reply_text(
                                f"Invalid selection format: '{subpart.strip()}'. Please enter numbers only."
                            )
                            return SELECTING_REPORT
            # Handle ranges: "1-3"
            elif "-" in part:
                try:
                    start, end = map(str.strip, part.split("-"))
                    start_index = int(start) - 1
                    end_index = int(end) - 1
                    
                    if start_index < 0 or end_index >= len(reports) or start_index > end_index:
                        await update.message.reply_text(
                            f"Invalid range: {part}. Please select a valid range between 1 and {len(reports)}."
                        )
                        return SELECTING_REPORT
                    
                    selected_indices.extend(list(range(start_index, end_index + 1)))
                except ValueError:
                    await update.message.reply_text(
                        f"Invalid range format: '{part}'. Please use format like '1-3'."
                    )
                    return SELECTING_REPORT
            # Handle single numbers: "1"
            else:
                try:
                    index = int(part.strip()) - 1
                    if 0 <= index < len(reports):
                        selected_indices.append(index)
                    else:
                        await update.message.reply_text(
                            f"Invalid selection: {part.strip()}. Please select numbers between 1 and {len(reports)}."
                        )
                        return SELECTING_REPORT
                except ValueError:
                    await update.message.reply_text(
                        f"Invalid selection format: '{part.strip()}'. Please enter numbers only."
                    )
                    return SELECTING_REPORT
        
        # Remove duplicates and sort
        selected_indices = sorted(list(set(selected_indices)))
        
        # Make sure we have at least one valid selection
        if not selected_indices:
            await update.message.reply_text(
                f"No valid report selections found. Please try again."
            )
            return SELECTING_REPORT
        
        # Get the selected reports
        selected_reports = [reports[i] for i in selected_indices]
        
        # Limit to max_reports
        if len(selected_reports) > max_reports:
            selected_reports = selected_reports[:max_reports]
            await update.message.reply_text(
                f"Limiting analysis to {max_reports} reports as requested."
            )
        
        # Generate report list for display
        report_list = ", ".join([f"#{i+1}" for i in selected_indices[:max_reports]])
        
        # Store selected reports for confirmation
        context.user_data['timeline_data'] = {
            'entity_name': original_query,
            'max_reports': max_reports,
            'selected_reports': selected_reports
        }
        
        # Ask for confirmation
        await update.message.reply_text(
            f"Selected {len(selected_reports)} reports ({report_list}) - Continue? (Yes/No)",
            parse_mode="Markdown"
        )
        
        return CONFIRMING_TIMELINE
    
    # Check for direct timeline command (e.g., "timeline 10")
    direct_timeline_match = re.match(r'^timeline\s+(\d+)$', text, re.IGNORECASE)
    if direct_timeline_match:
        max_reports = int(direct_timeline_match.group(1))
        
        # Limit reports to max_reports
        reports_to_analyze = reports[:max_reports]
        
        # Store selected reports for confirmation
        context.user_data['timeline_data'] = {
            'entity_name': original_query,
            'max_reports': max_reports,
            'selected_reports': reports_to_analyze
        }
        
        # Ask for confirmation
        await update.message.reply_text(
            f"Selected {len(reports_to_analyze)} reports - Continue? (Yes/No)",
            parse_mode="Markdown"
        )
        
        return CONFIRMING_TIMELINE
    
    # Check for timeline command with specific report (e.g., "2 timeline 10")
    timeline_match = re.match(r'(\d+)\s+timeline\s+(\d+)', text)
    if timeline_match:
        report_num = int(timeline_match.group(1))
        max_reports = int(timeline_match.group(2))
        
        if report_num < 1 or report_num > len(reports):
            await update.message.reply_text(
                f"Please select a valid report number between 1 and {len(reports)}."
            )
            return SELECTING_REPORT
        
        # Get the selected report to extract the entity name
        selected_report = reports[report_num - 1]
        entity_name = selected_report.get("company", "")
        
        # Store selected reports for confirmation
        context.user_data['timeline_data'] = {
            'entity_name': entity_name,
            'max_reports': max_reports,
            'selected_reports': reports
        }
        
        # Ask for confirmation
        await update.message.reply_text(
            f"Selected starting from report #{report_num} (up to {max_reports} reports) - Continue? (Yes/No)",
            parse_mode="Markdown"
        )
        
        return CONFIRMING_TIMELINE
    
    # Handle "latest" shortcut
    if text.lower() == 'latest':
        selected_indices = [0]  # First report (already sorted newest first)
        logger.info(f"User selected 'latest' report (index 0)")
    else:
        # Parse the selection (single number, range, or comma-separated list)
        selected_indices = []
        
        # Handle comma-separated values: "4,7,13"
        if "," in text:
            parts = text.split(",")
            for part in parts:
                try:
                    index = int(part.strip()) - 1
                    if 0 <= index < len(reports):
                        selected_indices.append(index)
                    else:
                        await update.message.reply_text(
                            f"Invalid selection: {part.strip()}. Please select numbers between 1 and {len(reports)}."
                        )
                        return SELECTING_REPORT
                except ValueError:
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
                    await update.message.reply_text(
                        f"Invalid range: {text}. Please select a valid range between 1 and {len(reports)}."
                    )
                    return SELECTING_REPORT
                
                selected_indices = list(range(start_index, end_index + 1))
            except ValueError:
                await update.message.reply_text(
                    f"Invalid range format: '{text}'. Please use format like '4-6'."
                )
                return SELECTING_REPORT
        # Handle single number: "4"
        else:
            try:
                selected_index = int(text) - 1
                logger.info(f"User selected report #{text} (index {selected_index})")
                if selected_index < 0 or selected_index >= len(reports):
                    await update.message.reply_text(
                        f"Please select a number between 1 and {len(reports)}."
                    )
                    return SELECTING_REPORT
                selected_indices = [selected_index]
            except ValueError:
                # Not a number or "latest", treat as new query
                logger.info(f"User entered '{text}' which is not a valid report selection, treating as new query")
                context.user_data.clear()
                return await handle_message(update, context)
    
    # Validate we have at least one valid selection
    if not selected_indices:
        await update.message.reply_text("No valid report selections found. Please try again.")
        return SELECTING_REPORT
    
    # Log the selected reports
    report_ids = [i+1 for i in selected_indices]
    logger.info(f"Processing selected reports: {report_ids}")
    
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )
    
    # Process each selected report
    all_responses = []
    
    for selected_index in selected_indices:
        # Get the selected report
        selected_report = reports[selected_index]
        company_name = selected_report.get("company", "")
        report_name = selected_report.get("name", "")
        report_date = selected_report.get("date", "")
        
        logger.info(f"Processing report: {company_name} - {report_name} - {report_date}")
        
        try:
            # Check if the report is in cache first
            cached_report = db_cache.get_cached_report(company_name, report_name, report_date)
            
            if cached_report:
                # Use cached report data
                logger.info(f"Using cached report for {company_name} - {report_name}")
                selected_report.update(cached_report)
                
                # Format the response data with cached info
                response_data = {
                    "company_name": selected_report.get("company", "Unknown"),
                    "found": True,
                    "date": selected_report.get("date", "Unknown"),
                    "report_name": selected_report.get("name", "Unknown"),
                    "financial_data": selected_report.get("financial_data", {}),
                    "is_cached": True
                }
                
                # Format the response with cached data
                response = format_financial_response(response_data)
                logger.info(f"Retrieved cached data for report {selected_index+1}")
                
                # Add a header to identify this report in multi-select mode
                if len(selected_indices) > 1:
                    report_num = selected_index + 1
                    response = f"📊 *Report #{report_num}*\n" + response
                
                all_responses.append(response)
                continue  # Skip the rest of the loop for this cached report
            
            # If not in cache, proceed with fetching
            # Get the full report content if not already fetched
            if not selected_report.get("report"):
                # Use the session that was used for search
                if "session" not in selected_report:
                    logger.error("No session available for this report")
                    raise ValueError("No session available for report fetching")
                
                # Get the link from the report
                link = selected_report.get("link")
                if not link:
                    logger.error("No report link available in the selected report")
                    raise ValueError("No report link available")
                
                # Use the original session from the search
                report_session = selected_report["session"]
                
                # First, ensure our session is still valid by hitting the main page again
                logger.info("Refreshing session with Bundesanzeiger website")
                report_session.get("https://www.bundesanzeiger.de")
                report_session.get("https://www.bundesanzeiger.de/pub/de/start?0")
                
                # Perform the search again to ensure we're in the right context
                search_url = f"https://www.bundesanzeiger.de/pub/de/start?0-2.-top%7Econtent%7Epanel-left%7Ecard-form=&fulltext={original_query}&area_select=&search_button=Suchen"
                logger.info(f"Re-running search to establish context: {search_url}")
                search_response = report_session.get(search_url)
                
                # Now use the click URL (which is a relative Wicket URL)
                # For Wicket components, we need to use the full URL
                # which includes the search page as a base
                logger.info(f"Clicking on report link: {link}")
                
                # Use search page as base if this is a relative URL
                if not link.startswith('http'):
                    # Get the search page URL from the response
                    search_page_url = search_response.url
                    if '?' in search_page_url:
                        base_url = search_page_url.split('?')[0]
                    else:
                        base_url = search_page_url
                    
                    # Construct full URL including the component path
                    if link.startswith('?'):
                        full_link = base_url + link
                    else:
                        full_link = base_url + '?' + link
                else:
                    full_link = link
                    
                logger.info(f"Final URL for report: {full_link}")
                
                # Fetch the report content
                response = report_session.get(full_link)
                
                # Log response info
                logger.info(f"Response status code: {response.status_code}")
                logger.debug(f"Response headers: {response.headers}")
                
                # Save the HTML for debugging
                with open("report_response.html", "w") as f:
                    f.write(response.text)
                logger.info("Saved HTML response to report_response.html for analysis")
                
                # Extract the report content
                soup = BeautifulSoup(response.text, "html.parser")
                content_element = soup.find("div", {"class": "publication_container"})
                
                if not content_element:
                    logger.warning("No content element found, checking for captcha")
                    # Check if we need to solve a captcha
                    captcha_wrapper = soup.find("div", {"class": "captcha_wrapper"})
                    if captcha_wrapper:
                        logger.info("Captcha detected, attempting to solve")
                        # Solve the captcha as before
                        captcha_img = captcha_wrapper.find("img")
                        if captcha_img:
                            captcha_src = captcha_img.get("src")
                            logger.info(f"Captcha image source: {captcha_src}")
                            if not captcha_src.startswith('http'):
                                if captcha_src.startswith('/'):
                                    captcha_src = f"https://www.bundesanzeiger.de{captcha_src}"
                                else:
                                    captcha_src = f"https://www.bundesanzeiger.de/pub/de/{captcha_src}"
                        
                            logger.info(f"Full captcha image URL: {captcha_src}")
                            img_response = report_session.get(captcha_src)
                            
                            # Solve the captcha
                            form = soup.find("form", {"id": "captchaForm"}) or (soup.find_all("form")[1] if len(soup.find_all("form")) > 1 else None)
                            if not form:
                                logger.error("Could not find captcha form")
                                raise ValueError("Could not find captcha form")
                                
                            captcha_url = form.get("action")
                            if not captcha_url.startswith('http'):
                                if captcha_url.startswith('/'):
                                    captcha_url = f"https://www.bundesanzeiger.de{captcha_url}"
                                else:
                                    captcha_url = f"https://www.bundesanzeiger.de/pub/de/{captcha_url}"
                        
                            logger.info(f"Captcha form action URL: {captcha_url}")
                            
                            # Import and initialize Bundesanzeiger if not already done
                            if not hasattr(bundesanzeiger, 'captcha_callback'):
                                # Create a new instance with captcha handling
                                from bundesanzeiger import Bundesanzeiger
                                captcha_handler = Bundesanzeiger()
                                captcha_solution = captcha_handler.captcha_callback(img_response.content)
                            else:
                                captcha_solution = bundesanzeiger.captcha_callback(img_response.content)
                                
                            logger.info(f"Generated captcha solution: {captcha_solution}")
                            
                            # Submit the captcha solution
                            captcha_data = {"solution": captcha_solution, "confirm-button": "OK"}
                            logger.info(f"Submitting captcha data: {captcha_data}")
                            response = report_session.post(
                                captcha_url,
                                data=captcha_data,
                            )
                            
                            # Save the captcha response for debugging
                            with open("captcha_response.html", "w") as f:
                                f.write(response.text)
                            logger.info("Saved captcha response to captcha_response.html")
                            
                            # Try to get the content again
                            soup = BeautifulSoup(response.text, "html.parser")
                            content_element = soup.find("div", {"class": "publication_container"})
                    else:
                        # Look for alternative content areas
                        logger.warning("No captcha detected, looking for alternative content elements")
                        
                        # Try different possible content elements
                        possible_content_elements = [
                            soup.find("div", {"class": "content"}),
                            soup.find("div", {"id": "content"}),
                            soup.find("div", {"class": "details"}),
                            soup.find("div", {"id": "details"})
                        ]
                        
                        for element in possible_content_elements:
                            if element:
                                content_element = element
                                logger.info(f"Found alternative content element: {element.name}")
                                break
                
                if content_element:
                    logger.info(f"Successfully extracted report content. Length: {len(content_element.text)} characters")
                    selected_report["report"] = content_element.text
                else:
                    logger.error("Failed to extract report content")
                    # Try to get any text from the body as a last resort
                    body_text = soup.find("body")
                    if body_text:
                        logger.info("Using body text as fallback")
                        selected_report["report"] = body_text.text
                    else:
                        selected_report["report"] = "Could not retrieve report content"
            else:
                logger.info("Report content already fetched, using cached content")
            
            # Process the report to extract financial data
            report_text = selected_report.get("report", "")
            logger.info(f"Starting financial data extraction for report: {selected_report.get('name')}")
            financial_data = process_financial_data(report_text)
            
            # Store the extracted data in the report
            selected_report["financial_data"] = financial_data
            
            # Store the report in cache for future use
            db_cache.store_report(selected_report)
            
            # Format the response data
            response_data = {
                "company_name": selected_report.get("company", "Unknown"),
                "found": True,
                "date": selected_report.get("date", "Unknown"),
                "report_name": selected_report.get("name", "Unknown"),
                "financial_data": financial_data,
                "is_cached": False
            }
            
            # Format the response
            response = format_financial_response(response_data)
            logger.info(f"Processed report {selected_index+1}, appending to responses")
            
            # Add a header to identify this report in multi-select mode
            if len(selected_indices) > 1:
                report_num = selected_index + 1
                response = f"📊 *Report #{report_num}*\n" + response
            
            all_responses.append(response)
            
        except Exception as e:
            logger.error(f"Error processing report {selected_index+1}: {e}", exc_info=True)
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
                await update.message.reply_text("---")
            
            await split_and_send_long_message(update, context, response, parse_mode="Markdown")
    
    # Clear the session data
    context.user_data.clear()
    return ConversationHandler.END

async def handle_timeline_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the user's response to the timeline confirmation prompt."""
    user_id = update.effective_user.id
    text = update.message.text.strip().lower()
    
    # Check if user confirmed
    if text in ['yes', 'y', 'continue', 'ok', 'yeah', 'yep', 'sure', 'confirm']:
        # Get stored timeline data
        timeline_data = context.user_data.get('timeline_data', {})
        
        if not timeline_data:
            await update.message.reply_text(
                "Session data was lost. Please try your request again."
            )
            context.user_data.clear()
            return ConversationHandler.END
        
        entity_name = timeline_data.get('entity_name')
        max_reports = timeline_data.get('max_reports')
        selected_reports = timeline_data.get('selected_reports')
        
        await update.message.reply_text(
            f"Analyzing timeline for *{entity_name}*... This may take a moment.",
            parse_mode="Markdown"
        )
        
        # Process the timeline analysis
        return await handle_timeline_analysis_with_reports(update, context, entity_name, max_reports, selected_reports)
    else:
        # User declined
        await update.message.reply_text(
            "Timeline analysis cancelled. You can select different reports or try another command."
        )
        # Don't clear user_data so they can still make another selection
        return SELECTING_REPORT

async def handle_timeline_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE, entity_name: str, max_reports: int) -> None:
    """Handle timeline analysis for a specific entity, generating graphs for financial trends."""
    user_id = update.effective_user.id
    
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )
    
    try:
        # Find all reports for this specific entity
        all_entity_reports = find_all_financial_reports(entity_name)
        
        # Log what we found
        logger.info(f"Found {len(all_entity_reports)} total reports for query '{entity_name}'")
        for i, r in enumerate(all_entity_reports[:5]):  # Log first 5 for debugging
            logger.info(f"Report {i+1}: {r.get('company', 'Unknown')} - {r.get('date', 'Unknown')}")
        
        # By default, use all reports without additional filtering
        # This gives us the broadest possible dataset for timeline analysis
        reports_to_analyze = all_entity_reports
        
        # Optional: Extract the core company name for logging purposes only
        core_name_parts = entity_name.lower().split()
        base_name = next((part for part in core_name_parts if len(part) > 3 and not part.startswith("gmbh")), entity_name.lower())
        logger.info(f"Using reports associated with search term '{entity_name}' (base name: '{base_name}')")
        
        # Sort reports by date (newest first)
        sorted_reports = sorted(
            reports_to_analyze, 
            key=lambda x: x.get("date_comparable", ""),
            reverse=True
        )
        
        # Limit to the requested maximum number
        reports_to_analyze = sorted_reports[:max_reports]
        
        if not reports_to_analyze:
            await update.message.reply_text(
                f"❌ No financial reports found for '{entity_name}'.",
                parse_mode="Markdown"
            )
            return ConversationHandler.END
        
        await update.message.reply_text(
            f"📋 Found {len(reports_to_analyze)} reports for *{entity_name}*. Analyzing financial data...",
            parse_mode="Markdown"
        )
        
        # Process each report to extract financial data
        analyzed_reports = []
        
        for i, report in enumerate(reports_to_analyze):
            # Show progress
            if i % 2 == 0 and i > 0:
                await context.bot.send_chat_action(
                    chat_id=update.effective_chat.id, action="typing"
                )
                
            report_date = report.get("date", "Unknown")
            report_name = report.get("name", "Unknown")
            
            logger.info(f"Processing timeline report {i+1}/{len(reports_to_analyze)}: {report_date} - {report_name}")
            
            # Check if this report is in cache first
            cached_report = db_cache.get_cached_report(entity_name, report_name, report_date)
            
            if cached_report:
                # Use cached report
                logger.info(f"Using cached report data for {report_date}")
                report_data = cached_report
                report_data["source"] = "Cache"
            else:
                # Fetch and process the report
                try:
                    # Get the full report content
                    report_content = await fetch_report_content(report, entity_name)
                    if report_content:
                        report["report"] = report_content
                        
                        # Extract financial data
                        financial_data = process_financial_data(report_content)
                        report["financial_data"] = financial_data
                        
                        # Store in cache for future use
                        db_cache.store_report(report)
                        
                        report_data = report.copy()
                        report_data["source"] = "Fresh"
                    else:
                        logger.warning(f"Could not retrieve content for report {report_date}")
                        continue
                except Exception as e:
                    logger.error(f"Error processing report {report_date}: {e}")
                    continue
            
            # Extract key financial metrics
            financial_data = report_data.get("financial_data", {})
            
            # Get year from report date and name using a combination of strategies
            report_date = report_data.get("date", "")
            report_name = report_data.get("name", "")
            
            # Strategy 1: Look for ending year in report name when it has a period format
            report_year = None
            
            # First try to extract year range from "von YYYY bis zum YYYY" pattern
            period_match = re.search(r'vom.*?(\d{4}).*?bis zum.*?(\d{4})', report_name)
            if period_match:
                # Use the end year of the period
                report_year = period_match.group(2)
                logger.info(f"Extracted year {report_year} from period in report name")
            
            # If that fails, look for any year in the report name
            if not report_year:
                year_match = re.search(r'(\d{4})', report_name)
                if year_match:
                    report_year = year_match.group(1)
                    logger.info(f"Extracted year {report_year} from report name")
            
            # If still no year, try to get it from the report date
            if not report_year:
                date_year_match = re.search(r'(\d{4})', report_date)
                if date_year_match:
                    report_year = date_year_match.group(1)
                    logger.info(f"Extracted year {report_year} from report date")
            
            # Last resort: use "Unknown" as the year
            if not report_year:
                report_year = "Unknown"
                logger.warning(f"Could not extract year from report: {report_name}")
            
            # Create a structured representation of the report's financial data
            analyzed_report = {
                "date": report_date,
                "year": report_year,
                "report_name": report_name,
                "earnings": financial_data.get("earnings_current_year"),
                "revenue": financial_data.get("revenue"),
                "assets": financial_data.get("total_assets"),
                "source": report_data.get("source", "Unknown")
            }
            
            analyzed_reports.append(analyzed_report)
        
        if not analyzed_reports:
            await update.message.reply_text(
                f"❌ Could not analyze any reports for '{entity_name}'. Try again with a different entity.",
                parse_mode="Markdown"
            )
            return ConversationHandler.END
        
        # Sort reports by year (oldest to newest) for visualization
        analyzed_reports.sort(key=lambda x: int(x["year"]) if x["year"] != "Unknown" else 0)
        
        # Generate summary text
        summary = f"📊 *Financial Timeline for {entity_name}*\n\n"
        
        for report in analyzed_reports:
            year_display = report['year'] if report['year'] != "Unknown" else "Unknown Year"
            company_display = report.get('company', entity_name).split('\n')[0]  # Get first line only
            summary += f"📅 *{year_display}* - {company_display}\n"
            summary += f"  • Revenue: {format_euro(report['revenue'])}\n"
            summary += f"  • Earnings: {format_euro(report['earnings'])}\n"
            summary += f"  • Assets: {format_euro(report['assets'])}\n"
            summary += f"  • Report: {report['report_name'][:50]}...\n"  # Truncate long report names
            summary += f"  • Source: {report['source']}\n\n"
        
        await split_and_send_long_message(update, context, summary, parse_mode="Markdown")
        
        # Generate and send graphs
        await generate_and_send_graphs(update, context, analyzed_reports, entity_name)
        
    except Exception as e:
        logger.error(f"Error in timeline analysis: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ An error occurred during timeline analysis: {str(e)}",
            parse_mode="Markdown"
        )
    
    # Clear the session data
    del user_sessions[user_id]
    return ConversationHandler.END

async def fetch_report_content(report, entity_name):
    """Fetch the content of a report from the Bundesanzeiger website."""
    try:
        # Check if report already has content
        if report.get("report"):
            return report.get("report")
        
        # If no session in report or link missing, we can't fetch
        if "session" not in report or not report.get("link"):
            logger.error("Missing session or link for report fetching")
            return None
        
        # Use the session to fetch the report
        report_session = report["session"]
        link = report.get("link")
        
        # Refresh session
        report_session.get("https://www.bundesanzeiger.de")
        report_session.get("https://www.bundesanzeiger.de/pub/de/start?0")
        
        # Re-run search to establish context
        search_url = f"https://www.bundesanzeiger.de/pub/de/start?0-2.-top%7Econtent%7Epanel-left%7Ecard-form=&fulltext={entity_name}&area_select=&search_button=Suchen"
        logger.info(f"Re-running search to establish context: {search_url}")
        search_response = report_session.get(search_url)
        
        # Construct full URL for the report
        if not link.startswith('http'):
            # Get the search page URL from the response
            search_page_url = search_response.url
            if '?' in search_page_url:
                base_url = search_page_url.split('?')[0]
            else:
                base_url = search_page_url
            
            # Construct full URL including the component path
            if link.startswith('?'):
                full_link = base_url + link
            else:
                full_link = base_url + '?' + link
        else:
            full_link = link
        
        # Fetch the report content
        response = report_session.get(full_link)
        
        # Extract the report content
        soup = BeautifulSoup(response.text, "html.parser")
        content_element = soup.find("div", {"class": "publication_container"})
        
        if not content_element:
            # Check for captcha
            captcha_wrapper = soup.find("div", {"class": "captcha_wrapper"})
            if captcha_wrapper:
                # Solve captcha
                captcha_img = captcha_wrapper.find("img")
                if captcha_img:
                    captcha_src = captcha_img.get("src")
                    if not captcha_src.startswith('http'):
                        if captcha_src.startswith('/'):
                            captcha_src = f"https://www.bundesanzeiger.de{captcha_src}"
                        else:
                            captcha_src = f"https://www.bundesanzeiger.de/pub/de/{captcha_src}"
                        
                    img_response = report_session.get(captcha_src)
                    
                    # Solve captcha
                    form = soup.find("form", {"id": "captchaForm"}) or (soup.find_all("form")[1] if len(soup.find_all("form")) > 1 else None)
                    if not form:
                        logger.error("Could not find captcha form")
                        return None
                    
                    captcha_url = form.get("action")
                    if not captcha_url.startswith('http'):
                        if captcha_url.startswith('/'):
                            captcha_url = f"https://www.bundesanzeiger.de{captcha_url}"
                        else:
                            captcha_url = f"https://www.bundesanzeiger.de/pub/de/{captcha_url}"
                        
                    # Solve captcha
                    if not hasattr(bundesanzeiger, 'captcha_callback'):
                        from bundesanzeiger import Bundesanzeiger
                        captcha_handler = Bundesanzeiger()
                        captcha_solution = captcha_handler.captcha_callback(img_response.content)
                    else:
                        captcha_solution = bundesanzeiger.captcha_callback(img_response.content)
                    
                    # Submit captcha solution
                    captcha_data = {"solution": captcha_solution, "confirm-button": "OK"}
                    response = report_session.post(
                        captcha_url,
                        data=captcha_data,
                    )
                    
                    # Try to get content again
                    soup = BeautifulSoup(response.text, "html.parser")
                    content_element = soup.find("div", {"class": "publication_container"})
            else:
                # Try alternative content elements
                possible_content_elements = [
                    soup.find("div", {"class": "content"}),
                    soup.find("div", {"id": "content"}),
                    soup.find("div", {"class": "details"}),
                    soup.find("div", {"id": "details"})
                ]
                
                for element in possible_content_elements:
                    if element:
                        content_element = element
                        break
        
        if content_element:
            return content_element.text
        
        # Try to get any text from the body as a last resort
        body_text = soup.find("body")
        if body_text:
            return body_text.text
        
        return None
    
    except Exception as e:
        logger.error(f"Error fetching report content: {e}")
        return None

async def generate_and_send_graphs(update: Update, context: ContextTypes.DEFAULT_TYPE, reports, entity_name):
    """Generate and send financial trend graphs."""
    try:
        # Sort reports by year numerically to ensure correct order on the x-axis
        reports.sort(key=lambda x: int(x["year"]) if x["year"] != "Unknown" else 0)
        
        # Extract data for plotting
        years = [int(r["year"]) if r["year"] != "Unknown" else 0 for r in reports]
        earnings = [r["earnings"] if r["earnings"] is not None else 0 for r in reports]
        revenues = [r["revenue"] if r["revenue"] is not None else 0 for r in reports]
        assets = [r["assets"] if r["assets"] is not None else 0 for r in reports]
        
        # Calculate earnings/revenue ratio
        earnings_revenue_ratio = []
        for i in range(len(reports)):
            if reports[i]["revenue"] is not None and reports[i]["revenue"] > 0 and reports[i]["earnings"] is not None:
                ratio = reports[i]["earnings"] / reports[i]["revenue"]
                earnings_revenue_ratio.append(ratio)
            else:
                earnings_revenue_ratio.append(0)
        
        # Only generate graphs if we have at least two data points
        if len(years) < 2:
            await update.message.reply_text(
                "⚠️ Need at least 2 years of data to generate meaningful graphs.",
                parse_mode="Markdown"
            )
            return
        
        # Set a consistent style for all plots
        plt.style.use('seaborn-v0_8-darkgrid')
        
        # Function to create and send a graph
        async def create_and_send_graph(y_data, title, y_label, formatter=None, color='#1f77b4'):
            plt.figure(figsize=(10, 6))
            
            # Plot with connected line and markers
            plt.plot(years, y_data, marker='o', linestyle='-', color=color, linewidth=2.5, markersize=8)
            
            # Add data labels above points
            for i, value in enumerate(y_data):
                if formatter == 'euro':
                    label = f"€{value:,.0f}".replace(',', '.') if value else "N/A"
                elif formatter == 'percent':
                    label = f"{value:.1%}" if value else "N/A"
                else:
                    label = f"{value}" if value else "N/A"
                
                plt.annotate(
                    label,
                    (years[i], y_data[i]),
                    textcoords="offset points",
                    xytext=(0, 10),
                    ha='center',
                    fontsize=9
                )
            
            # Improve grid and styling
            plt.grid(True, linestyle='--', alpha=0.7)
            plt.title(f"{title} - {entity_name}", fontsize=16, pad=20)
            plt.xlabel("Year", fontsize=14, labelpad=10)
            plt.ylabel(y_label, fontsize=14, labelpad=10)
            
            # Use numerical years directly for x-axis 
            plt.xticks(years, [str(y) for y in years])
            
            # Format y-axis labels
            if formatter == 'euro':
                plt.gca().yaxis.set_major_formatter(
                    plt.FuncFormatter(lambda x, loc: "€{:,.0f}".format(x).replace(',', '.') if x != 0 else "0")
                )
            elif formatter == 'percent':
                plt.gca().yaxis.set_major_formatter(
                    plt.FuncFormatter(lambda x, loc: "{:.1%}".format(x))
                )
            
            # Add version and date stamp
            now = datetime.now().strftime("%Y-%m-%d")
            plt.figtext(0.99, 0.01, f"Generated: {now}", ha='right', fontsize=8, color='gray')
            
            plt.tight_layout()
            
            # Save the plot to a buffer
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=120)
            buf.seek(0)
            
            # Close the plot to free memory
            plt.close()
            
            # Send the graph
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=buf,
                caption=f"📊 {title} for {entity_name}"
            )
        
        # Send a message indicating graph generation
        await update.message.reply_text(
            "📈 Generating financial trend graphs...",
            parse_mode="Markdown"
        )
        
        # Generate and send each graph with different colors
        await create_and_send_graph(earnings, "Earnings Over Time", "Earnings (EUR)", 'euro', '#2ca02c')  # Green
        await create_and_send_graph(earnings_revenue_ratio, "Earnings/Revenue Ratio", "Ratio", 'percent', '#ff7f0e')  # Orange
        await create_and_send_graph(revenues, "Revenue Over Time", "Revenue (EUR)", 'euro', '#1f77b4')  # Blue
        await create_and_send_graph(assets, "Total Assets Over Time", "Assets (EUR)", 'euro', '#d62728')  # Red
        
        await update.message.reply_text(
            "✅ Financial trend analysis complete!",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Error generating graphs: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Error generating graphs: {str(e)}",
            parse_mode="Markdown"
        )

def process_financial_data(text):
    """Process report text to extract financial data using DeepSeek via OpenRouter."""
    try:
        # Limit text length to avoid token limit issues
        max_length = 400000  # Approximating 100K tokens (4 chars per token)
        if len(text) > max_length:
            sample_text = text[:500] + "..." # Sample for logging
            text = text[:max_length] + "..."
            logger.info(f"Report text truncated to {max_length} characters. Sample: {sample_text}")
        else:
            sample_text = text[:500] + "..." # Sample for logging
            logger.info(f"Processing report text. Length: {len(text)} characters. Sample: {sample_text}")
        
        logger.info(f"Calling DeepSeek via OpenRouter API to extract financial data")
        
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/yourusername/bundesanzeiger_telegram_bot",  # Replace with your repo
            "X-Title": "Bundesanzeiger Telegram Bot"
        }

        payload = {
            "model": "deepseek/deepseek-chat-v3-0324",
            "messages": [
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
            ]
        }

        response = requests.post(OPENROUTER_BASE_URL, json=payload, headers=headers)
        response.raise_for_status()
        
        response_data = response.json()
        content = response_data["choices"][0]["message"]["content"]
        
        # Log the raw response from DeepSeek
        logger.info(f"DeepSeek API response: {content}")
        
        # Parse the JSON response
        financial_data = json.loads(content)
        logger.info(f"Parsed financial data: {json.dumps(financial_data, indent=2)}")
        return financial_data
    except Exception as e:
        logger.error(f"Error processing financial data: {e}")
        if "response_data" in locals():
            logger.error(f"Response content: {response_data}")
        return {
            "earnings_current_year": None,
            "total_assets": None,
            "revenue": None
        }

async def handle_timeline_analysis_with_reports(update: Update, context: ContextTypes.DEFAULT_TYPE, entity_name: str, max_reports: int, existing_reports: list) -> None:
    """Handle timeline analysis using existing reports without a new search."""
    
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )
    
    try:
        # Log the existing reports
        logger.info(f"Using {len(existing_reports)} existing reports for timeline analysis of '{entity_name}'")
        for i, r in enumerate(existing_reports[:5]):  # Log first 5 for debugging
            logger.info(f"Report {i+1}: {r.get('company', 'Unknown')} - {r.get('date', 'Unknown')}")
        
        # Sort reports by date (newest first)
        sorted_reports = sorted(
            existing_reports, 
            key=lambda x: x.get("date_comparable", ""),
            reverse=True
        )
        
        # Limit to the requested maximum number
        reports_to_analyze = sorted_reports[:max_reports]
        
        if not reports_to_analyze:
            await update.message.reply_text(
                f"❌ No financial reports found for '{entity_name}'.",
                parse_mode="Markdown"
            )
            return ConversationHandler.END
        
        await update.message.reply_text(
            f"📋 Found {len(reports_to_analyze)} reports for *{entity_name}*. Analyzing financial data...",
            parse_mode="Markdown"
        )
        
        # Process each report to extract financial data
        analyzed_reports = []
        
        for i, report in enumerate(reports_to_analyze):
            # Show progress
            if i % 2 == 0 and i > 0:
                await context.bot.send_chat_action(
                    chat_id=update.effective_chat.id, action="typing"
                )
                
            report_date = report.get("date", "Unknown")
            report_name = report.get("name", "Unknown")
            company_name = report.get("company", "Unknown")
            
            logger.info(f"Processing timeline report {i+1}/{len(reports_to_analyze)}: {report_date} - {report_name}")
            
            # Check if this report is in cache first
            cached_report = db_cache.get_cached_report(company_name, report_name, report_date)
            
            if cached_report:
                # Use cached report
                logger.info(f"Using cached report data for {report_date}")
                report_data = cached_report
                report_data["source"] = "Cache"
            else:
                # Fetch and process the report
                try:
                    # Get the full report content
                    report_content = await fetch_report_content(report, entity_name)
                    if report_content:
                        report["report"] = report_content
                        
                        # Extract financial data
                        financial_data = process_financial_data(report_content)
                        report["financial_data"] = financial_data
                        
                        # Store in cache for future use
                        db_cache.store_report(report)
                        
                        report_data = report.copy()
                        report_data["source"] = "Fresh"
                    else:
                        logger.warning(f"Could not retrieve content for report {report_date}")
                        continue
                except Exception as e:
                    logger.error(f"Error processing report {report_date}: {e}")
                    continue
            
            # Extract key financial metrics
            financial_data = report_data.get("financial_data", {})
            
            # Get year from report date and name using a combination of strategies
            report_date = report_data.get("date", "")
            report_name = report_data.get("name", "")
            
            # Strategy 1: Look for ending year in report name when it has a period format
            report_year = None
            
            # First try to extract year range from "von YYYY bis zum YYYY" pattern
            period_match = re.search(r'vom.*?(\d{4}).*?bis zum.*?(\d{4})', report_name)
            if period_match:
                # Use the end year of the period
                report_year = period_match.group(2)
                logger.info(f"Extracted year {report_year} from period in report name")
            
            # If that fails, look for any year in the report name
            if not report_year:
                year_match = re.search(r'(\d{4})', report_name)
                if year_match:
                    report_year = year_match.group(1)
                    logger.info(f"Extracted year {report_year} from report name")
            
            # If still no year, try to get it from the report date
            if not report_year:
                date_year_match = re.search(r'(\d{4})', report_date)
                if date_year_match:
                    report_year = date_year_match.group(1)
                    logger.info(f"Extracted year {report_year} from report date")
            
            # Last resort: use "Unknown" as the year
            if not report_year:
                report_year = "Unknown"
                logger.warning(f"Could not extract year from report: {report_name}")
            
            # Create a structured representation of the report's financial data
            analyzed_report = {
                "date": report_date,
                "year": report_year,
                "report_name": report_name,
                "company": company_name,
                "earnings": financial_data.get("earnings_current_year"),
                "revenue": financial_data.get("revenue"),
                "assets": financial_data.get("total_assets"),
                "source": report_data.get("source", "Unknown")
            }
            
            analyzed_reports.append(analyzed_report)
        
        if not analyzed_reports:
            await update.message.reply_text(
                f"❌ Could not analyze any reports for '{entity_name}'. Try again with a different entity.",
                parse_mode="Markdown"
            )
            return ConversationHandler.END
        
        # Sort reports by year (oldest to newest) for visualization
        analyzed_reports.sort(key=lambda x: int(x["year"]) if x["year"] != "Unknown" else 0)
        
        # Generate summary text
        summary = f"📊 *Financial Timeline for {entity_name}*\n\n"
        
        for report in analyzed_reports:
            year_display = report['year'] if report['year'] != "Unknown" else "Unknown Year"
            company_display = report.get('company', entity_name).split('\n')[0]  # Get first line only
            summary += f"📅 *{year_display}* - {company_display}\n"
            summary += f"  • Revenue: {format_euro(report['revenue'])}\n"
            summary += f"  • Earnings: {format_euro(report['earnings'])}\n"
            summary += f"  • Assets: {format_euro(report['assets'])}\n"
            summary += f"  • Report: {report['report_name'][:50]}...\n"  # Truncate long report names
            summary += f"  • Source: {report['source']}\n\n"
        
        await split_and_send_long_message(update, context, summary, parse_mode="Markdown")
        
        # Generate and send graphs
        await generate_and_send_graphs(update, context, analyzed_reports, entity_name)
        
    except Exception as e:
        logger.error(f"Error in timeline analysis: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ An error occurred during timeline analysis: {str(e)}",
            parse_mode="Markdown"
        )
    
    # Clear the session data
    context.user_data.clear()
    return ConversationHandler.END

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
    
    # Create the Application
    application = Application.builder().token(TELEGRAM_CONFIG['BOT_TOKEN']).build()

    # Add conversation handler for report selection
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)],
        states={
            SELECTING_REPORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_report_selection)],
            CONFIRMING_TIMELINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_timeline_confirmation)],
        },
        fallbacks=[],
    )

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(conv_handler)

    # Run the bot until the user presses Ctrl-C
    logger.info("Bot is running. Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main() 