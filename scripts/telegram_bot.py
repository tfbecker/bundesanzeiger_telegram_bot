#!/usr/bin/env python3
import os
import logging
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI
from telegram_config import TELEGRAM_CONFIG
from bundesanzeiger import Bundesanzeiger

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Retrieve OpenAI API key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# Initialize Bundesanzeiger instance
bundesanzeiger = Bundesanzeiger()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_text(
        f"Hi {user.first_name}! I'm your Bundesanzeiger bot. Send me a company name, and I'll fetch its financial data. For example, try 'Deutsche Bahn AG'."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        "Send me a company name, and I'll fetch its financial data from Bundesanzeiger.\n"
        "Examples:\n"
        "- Deutsche Bahn AG\n"
        "- Siemens AG\n"
        "- BMW AG"
    )

def parse_message_with_openai(message_text: str) -> dict:
    """Use OpenAI with tool calling to parse the user message."""
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

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that extracts company names from user messages. The user wants to get financial information about a company from the Bundesanzeiger database."},
                {"role": "user", "content": message_text}
            ],
            tools=tools,
            tool_choice={"type": "function", "function": {"name": "get_company_info"}}
        )

        tool_call = response.choices[0].message.tool_calls[0]
        if tool_call.function.name == "get_company_info":
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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process user messages and respond with financial data."""
    message_text = update.message.text
    
    # Send a typing indicator while processing
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )
    
    # Use OpenAI to parse the message
    parsed_message = parse_message_with_openai(message_text)
    
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
        f"Looking up financial information for *{company_name}*... This may take a moment.",
        parse_mode="Markdown"
    )
    
    try:
        # Fetch financial data from Bundesanzeiger
        financial_data = bundesanzeiger.get_company_financial_info(company_name)
        
        # Format and send the response
        response = format_financial_response(financial_data)
        await update.message.reply_text(response, parse_mode="Markdown")
    
    except Exception as e:
        logger.error(f"Error fetching financial data: {e}")
        await update.message.reply_text(
            f"Sorry, an error occurred while fetching the data: {str(e)}"
        )

def main() -> None:
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(TELEGRAM_CONFIG['BOT_TOKEN']).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main() 