import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Telegram configuration
TELEGRAM_CONFIG = {
    # Get this from @BotFather on Telegram
    'BOT_TOKEN': os.getenv('TELEGRAM_BOT_TOKEN'),
    # Get this by sending a message to @userinfobot
    'CHAT_ID': os.getenv('TELEGRAM_CHAT_ID')
}
