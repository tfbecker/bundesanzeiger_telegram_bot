import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Telegram configuration
TELEGRAM_CONFIG = {
    'BOT_TOKEN': os.getenv('TELEGRAM_BOT_TOKEN'),  # Get this from @BotFather on Telegram
    'CHAT_ID': os.getenv('TELEGRAM_CHAT_ID')       # Get this by sending a message to @userinfobot
}
