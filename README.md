# 🇩🇪 Bundesanzeiger Financial Data Telegram Bot | German Company Financial Analysis

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![OpenAI](https://img.shields.io/badge/OpenAI-API-green.svg)](https://openai.com/)
[![Telegram Bot API](https://img.shields.io/badge/Telegram-Bot%20API-blue.svg)](https://core.telegram.org/bots/api)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Extract, analyze and visualize financial data from German companies using the Bundesanzeiger (Federal Gazette) via a convenient Telegram bot interface with AI-powered financial analysis and visualization.

<p align="center">
  <img alt="Bundesanzeiger Telegram Bot showing company search results and available reports" src="screenshot/bot_1.png" width="400" />
  <img alt="Financial timeline analysis with trend visualization and graphs" src="screenshot/bot_2.png" width="400" />
</p>

## 📋 Table of Contents

- [Features](#features)
- [How It Works](#how-it-works)
- [Setup Instructions](#setup-instructions)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Running Locally](#running-locally)
  - [Docker Deployment](#docker-deployment)
- [Usage](#usage)
  - [Example Commands](#example-commands)
  - [Timeline Analysis](#timeline-analysis)
- [Technical Details](#technical-details)
  - [Architecture](#architecture)
  - [Data Extraction](#data-extraction)
  - [Financial Analysis](#financial-analysis)
  - [Error Handling](#error-handling)
- [Troubleshooting](#troubleshooting)
- [Security Considerations](#security-considerations)
- [License](#license)
- [Contributions](#contributions)

## ✨ Features

- 🔍 **Advanced Company Search**: Find German companies in the Bundesanzeiger by name with fuzzy matching
- 💰 **Financial Data Extraction**: Automatically extract key financial metrics (earnings, total assets, revenue)
- 📊 **Financial Timeline Analysis**: Generate trend visualizations and performance graphs across multiple years
- 🤖 **Natural Language Processing**: OpenAI-powered understanding of financial reports and user queries
- 📱 **Telegram Interface**: User-friendly mobile access to complex financial data
- 💾 **Intelligent Caching**: High-performance data retrieval with automated caching system
- 🛡️ **CAPTCHA Handling**: Automatic solving of Bundesanzeiger CAPTCHA challenges
- 🌐 **Multi-Report Analysis**: Compare data across different financial periods

## 🔄 How It Works

1. Users send a company name to the Telegram bot
2. OpenAI's tool calling API extracts the company name from natural language input
3. The bot searches for the company in the Bundesanzeiger database
4. It retrieves and processes available financial reports
5. AI extracts structured financial data from complex German reports
6. The system generates visualizations and trend analysis
7. Formatted results and graphs are sent back to the user via Telegram

## 🚀 Setup Instructions

### Prerequisites

- Python 3.9+
- OpenAI API Key
- Telegram Bot Token (from @BotFather)
- Internet connection to access Bundesanzeiger

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/bundesanzeiger_telegram_bot.git
   cd bundesanzeiger_telegram_bot
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows, use: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file with your credentials:
   ```
   # OpenAI API Key
   OPENAI_API_KEY=your_openai_api_key

   # Telegram Bot Configuration
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   TELEGRAM_CHAT_ID=your_telegram_chat_id

   # Database Configuration (optional)
   DB_PATH=financial_cache.db
   ```

### Running Locally

Start the Telegram bot:

```bash
python scripts/telegram_bot.py
```

### Docker Deployment

#### Using Docker

1. Build the Docker image:
   ```bash
   docker build -t bundesanzeiger-bot .
   ```

2. Run the container:
   ```bash
   docker run -d --name bundesanzeiger-bot \
     -v $(pwd)/data:/app/data \
     --env-file .env \
     bundesanzeiger-bot
   ```

#### Using Docker Compose

1. Start the service:
   ```bash
   docker-compose up -d
   ```

2. View logs:
   ```bash
   docker-compose logs -f
   ```

## 📱 Usage

Once the bot is running, you can interact with it through Telegram:

1. Start a chat with your bot (using the bot username you set in @BotFather)
2. Send a message with a company name, e.g., `Deutsche Bahn AG` or `Show me financial data for BMW`
3. The bot will process your request and respond with the financial information

### Example Commands

- Send a company name: `Siemens AG`
- Ask a question: `What are the financials for Volkswagen?`
- Get help: `/help`

### Timeline Analysis

The bot can generate financial timelines with trend analysis and graphs. Available commands:

- Basic timeline: `timeline 10` - Analyze up to 10 most recent reports
- Select specific reports: `timeline 10 1,2,5,6` or `timeline 10 1-4`
- Filter by company name: `timeline 10 HolzLand Becker GmbH`
- Timeline for specific report: `2 timeline 10`

The bot will ask for confirmation before processing timeline analysis to prevent unwanted operations.

## 🔧 Technical Details

### Architecture

- `bundesanzeiger.py`: Handles scraping and processing of Bundesanzeiger data
- `telegram_bot.py`: Implements the Telegram bot interface
- `telegram_config.py`: Contains Telegram API configuration

### Data Extraction

The system uses BeautifulSoup for HTML parsing and extraction of financial data from the Bundesanzeiger website. It handles the site's session management, navigation structure, and Wicket components.

### Financial Analysis

Financial data is extracted using natural language processing to understand complex accounting terminology in German financial reports. The system identifies key financial indicators and normalizes them for trend analysis.

### Error Handling

The bot includes robust error handling for common issues:

- Not finding a company in the Bundesanzeiger database
- Connection issues with the Bundesanzeiger website
- Failed parsing of financial data
- CAPTCHA challenges from the Bundesanzeiger site

## 🔒 Troubleshooting

### Common Issues

1. **Import Errors**: If you see import errors, make sure you're running the server from the correct directory and that the parent directory contains the `scripts` folder.

2. **Database Path Issues**: The MCP server now automatically creates the SQLite database in the `data/` directory of the main project. If you see "unable to open database file" errors, ensure the project structure is correct.

3. **Environment Variables**: Make sure either `OPENROUTER_API_KEY` or `OPENAI_API_KEY` is set in your environment or in your MCP client configuration.

4. **Cursor IDE Issues**: 
   - Make sure to use the full Python path in your configuration
   - Check that the working directory is correctly set
   - Verify the environment variable is properly configured

### Restarting the Server

If you need to restart the MCP server in Cursor:
1. Open Cursor settings (Cmd+,)
2. Search for "MCP"
3. Toggle the server off and on again
4. Or restart Cursor entirely

## 🔒 Security Considerations

- Keep your `.env` file secure and never commit it to version control
- Consider using Docker secrets for production deployments
- Regularly rotate your API keys
- The bot stores minimal user data and focuses on processing financial information

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🚀 MCP Server Integration

This project now includes an **MCP (Model Context Protocol) Server** that exposes the Bundesanzeiger functionality as an API for LLMs to use.

### Features

The MCP server provides two main tools:
- **search**: Search for German companies in the Bundesanzeiger database
- **analyze**: Analyze financial reports and extract structured financial data

### Quick Start

```bash
# Navigate to the MCP server directory
cd mcp_server

# Install dependencies
pip install -r requirements.txt

# Test the server
python test_server.py

# Run the server
python server.py
```

### Integration with LLM Clients

The MCP server can be integrated with:
- **Claude Desktop**: Add server configuration to MCP settings
- **Cline (VS Code Extension)**: Configure in Cline settings
- **Custom MCP Clients**: Use the MCP protocol to connect

For detailed integration instructions, see [`mcp_server/INTEGRATION.md`](mcp_server/INTEGRATION.md).

### Example Usage

Once connected to an LLM client, you can use prompts like:
- "Search for BMW AG in the German business registry"  
- "Analyze the financial data for Siemens AG"
- "Compare Deutsche Bahn AG and Volkswagen AG financial performance"

## 👥 Contributions

Contributions are welcome! Please feel free to submit a Pull Request or open an issue for bug reports and feature requests. 