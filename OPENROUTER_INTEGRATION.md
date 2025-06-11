# OpenRouter Integration with DeepSeek

This project has been updated to use the **DeepSeek Chat v3** model via **OpenRouter** instead of OpenAI.

## What Changed

### 1. Dependencies
- Removed: `openai>=1.6.0`
- The `requests` library (already included) is now used for API calls
- `python-dotenv` is used to load environment variables

### 2. Environment Variables
You need to create a `.env` file in the project root with:

```env
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

# OpenRouter API Configuration
OPENROUTER_API_KEY=your_openrouter_api_key_here

# Database Configuration  
DB_PATH=financial_cache.db
```

### 3. Code Changes

#### API Integration
- Replaced OpenAI client with direct HTTP requests to OpenRouter
- Updated `parse_message_with_openai()` → `parse_message_with_deepseek()`
- Updated `process_financial_data()` to use DeepSeek via OpenRouter
- Using model: `deepseek/deepseek-chat-v3-0324`

#### Features Maintained
- ✅ Tool calling for company name extraction
- ✅ Financial data extraction from reports
- ✅ Timeline analysis and graphing
- ✅ All existing Telegram bot functionality

## Getting Your OpenRouter API Key

1. Visit [OpenRouter.ai](https://openrouter.ai/)
2. Sign up for an account
3. Go to your dashboard and create an API key
4. Add the key to your `.env` file

## Testing the Integration

Run the test script to verify everything works:

```bash
python test_openrouter.py
```

This will test:
- Basic API connectivity
- Tool calling functionality
- Model response quality

## Running the Bot

```bash
# Install dependencies
pip install -r requirements.txt

# Run the bot
python scripts/telegram_bot.py
```

## Benefits of Using DeepSeek

- **Cost-effective**: Generally cheaper than GPT-4 models
- **Good performance**: DeepSeek v3 is competitive with GPT-4 class models
- **Large context window**: Can handle longer financial documents
- **Tool calling support**: Maintains the structured data extraction capabilities

## Troubleshooting

### Common Issues

1. **API Key Error**: Make sure your `.env` file is in the project root and contains the correct API key
2. **Tool Calling Issues**: Some models may not support tool calling - DeepSeek v3 does support it
3. **Rate Limits**: OpenRouter has different rate limits than OpenAI

### Debug Tips

- Check the logs for API response details
- Use the test script to isolate issues
- Verify your OpenRouter account has sufficient credits

## Model Information

- **Model**: `deepseek/deepseek-chat-v3-0324`
- **Context Window**: Large context window suitable for financial documents
- **Capabilities**: Text generation, tool calling, JSON structured output
- **Provider**: OpenRouter (routing to DeepSeek) 