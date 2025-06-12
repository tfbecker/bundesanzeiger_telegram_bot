# Bundesanzeiger MCP Server

This is a Model Context Protocol (MCP) server that exposes the functionality of the Bundesanzeiger Telegram bot as an API for LLMs to use.

## Features

The MCP server provides two main tools:

1. **search** - Search for German companies in the Bundesanzeiger database
2. **analyze** - Analyze financial reports for a specific company and extract financial data

## Installation

1. Navigate to the MCP server directory:
   ```bash
   cd mcp_server
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Make sure you have the environment variables set up (same as the main project):
   ```bash
   # Copy the .env file from the parent directory or create a new one
   cp ../.env . 
   ```

### Quick Setup for Cursor IDE

For a quick Cursor IDE setup, run:

```bash
./setup_cursor.sh
```

This will generate the exact configuration you need to copy into your Cursor IDE settings.

## Usage

### Running the Server

To run the MCP server:

```bash
python server.py
```

The server will start and communicate via stdin/stdout using the MCP protocol.

### Tools Available

#### 1. search
Search for German companies in the Bundesanzeiger database.

**Parameters:**
- `company_name` (string, required): Name of the German company to search for

**Example:**
```json
{
  "name": "search",
  "arguments": {
    "company_name": "Deutsche Bahn AG"
  }
}
```

**Response:**
```json
{
  "found": true,
  "searched_name": "Deutsche Bahn AG",
  "reports_count": 1,
  "reports": [
    {
      "name": "Jahresabschluss zum 31.12.2023",
      "company": "Deutsche Bahn AG",
      "date": "2024-06-15T00:00:00",
      "has_financial_data": true
    }
  ]
}
```

#### 2. analyze
Analyze financial reports for a specific German company and extract detailed financial data.

**Parameters:**
- `company_name` (string, required): Exact name of the German company to analyze

**Example:**
```json
{
  "name": "analyze", 
  "arguments": {
    "company_name": "Deutsche Bahn AG"
  }
}
```

**Response:**
```json
{
  "company_name": "Deutsche Bahn AG",
  "found": true,
  "is_cached": false,
  "date": "2024-06-15T00:00:00",
  "financial_data": {
    "earnings_current_year": 1200000000,
    "total_assets": 45000000000,
    "revenue": 52000000000
  },
  "report_name": "Jahresabschluss zum 31.12.2023"
}
```

## Integration with LLM Clients

This MCP server can be integrated with various LLM tools and applications that support the Model Context Protocol.

### Cursor IDE

To integrate the Bundesanzeiger MCP server with Cursor IDE:

1. **Install the MCP extension** (if not already installed):
   - Open Cursor IDE
   - Go to Extensions (Cmd/Ctrl + Shift + X)
   - Search for "MCP" or "Model Context Protocol"
   - Install the MCP extension

2. **Configure the MCP server**:
   - Open Cursor settings (Cmd/Ctrl + ,)
   - Search for "MCP" in settings
   - Add a new MCP server configuration:

   ```json
   {
     "mcp.servers": [
       {
         "name": "bundesanzeiger",
         "command": "python",
         "args": ["server.py"],
         "cwd": "/absolute/path/to/your/bundesanzeiger_telegram_bot/mcp_server",
         "env": {
           "OPENROUTER_API_KEY": "your_openrouter_api_key_here",
           "OPENAI_API_KEY": "your_openai_api_key_here"
         }
       }
     ]
   }
   ```

3. **Update the configuration paths**:
   - Replace `/absolute/path/to/your/bundesanzeiger_telegram_bot/mcp_server` with the actual path to your MCP server directory
   - Add your actual API keys to the `env` section

4. **Restart Cursor IDE** to load the new MCP server configuration

5. **Test the integration**:
   - Open a new chat in Cursor
   - Try prompts like:
     - "Search for Deutsche Bahn AG in the German business registry"
     - "Analyze the financial data for Siemens Aktiengesellschaft"
     - "What are the latest financial reports for Volkswagen AG?"

### Claude Desktop

To integrate with Claude Desktop:

1. **Locate the Claude Desktop config file:**
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`

2. **Add the server configuration:**
   ```json
   {
     "mcpServers": {
       "bundesanzeiger": {
         "command": "python",
         "args": ["server.py"],
         "cwd": "/absolute/path/to/your/bundesanzeiger_telegram_bot/mcp_server",
         "env": {
           "OPENROUTER_API_KEY": "your_openrouter_api_key_here",
           "OPENAI_API_KEY": "your_openai_api_key_here"
         }
       }
     }
   }
   ```

3. **Restart Claude Desktop**

### Cline (VS Code Extension)

To use with Cline in VS Code:

1. **Install the Cline extension** in VS Code

2. **Configure MCP server in Cline settings:**
   ```json
   {
     "cline.mcp": {
       "servers": [
         {
           "name": "bundesanzeiger",
           "command": "python",
           "args": ["server.py"],
           "cwd": "/absolute/path/to/your/bundesanzeiger_telegram_bot/mcp_server",
           "env": {
             "OPENROUTER_API_KEY": "your_openrouter_api_key_here",
             "OPENAI_API_KEY": "your_openai_api_key_here"
           }
         }
       ]
     }
   }
   ```

### General Usage with LLM Clients

Once integrated, the LLM can use the tools to:

1. **Search for German companies by name**
2. **Get detailed financial analysis** including earnings, assets, and revenue  
3. **Access cached results** for faster repeated queries

### Example Prompts

Once connected to any LLM client, you can use prompts like:

- **Basic Search**: "Search for BMW AG in the German business registry"
- **Financial Analysis**: "Analyze the financial data for Siemens AG and summarize their performance"
- **Comparative Analysis**: "Compare the financial metrics of Deutsche Bahn AG and Volkswagen AG"
- **Industry Research**: "Find and analyze financial reports for major German automotive companies"

## Technical Details

- The server reuses all the existing functionality from the main Bundesanzeiger project
- It imports the `Bundesanzeiger` class from `scripts/bundesanzeiger.py`
- Caching is automatically handled by the existing cache system
- CAPTCHA solving is handled transparently when needed

## Error Handling

The server includes comprehensive error handling for:
- Missing or invalid company names
- Companies not found in the Bundesanzeiger database
- Network connectivity issues
- Data extraction failures

## Requirements

- Python 3.9+
- All dependencies from the main project
- MCP library for the protocol implementation
- Same environment variables as the main project (OpenAI API key, etc.)

## Environment Variables

Make sure to set up the same environment variables as the main project:

```bash
# OpenAI API Key (for financial data extraction)
OPENAI_API_KEY=your_openai_api_key

# Database path (optional)
DB_PATH=financial_cache.db
``` 