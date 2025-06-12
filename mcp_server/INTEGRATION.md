# MCP Server Integration Guide

This document explains how to integrate the Bundesanzeiger MCP Server with various LLM clients and applications.

## Overview

The Bundesanzeiger MCP Server exposes German company financial data search and analysis capabilities through the Model Context Protocol (MCP). This allows LLMs to:

1. **Search** for German companies in the Bundesanzeiger database
2. **Analyze** financial reports and extract structured financial data

## Quick Start

1. **Install dependencies:**
   ```bash
   cd mcp_server
   pip install -r requirements.txt
   ```

2. **Set up environment variables:**
   ```bash
   # Copy .env from parent project or create new one
   cp ../.env .
   ```

3. **Test the server:**
   ```bash
   python test_server.py
   ```

4. **Run the server:**
   ```bash
   python server.py
   # or
   ./run_server.sh
   ```

## Client Integration

### Claude Desktop

To integrate with Claude Desktop, add the server configuration to your MCP settings:

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
         "cwd": "/path/to/your/bundesanzeiger_telegram_bot/mcp_server",
         "env": {
           "OPENAI_API_KEY": "your_openai_api_key_here"
         }
       }
     }
   }
   ```

3. **Restart Claude Desktop**

### Cursor IDE

To integrate with Cursor IDE:

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

3. **Update the configuration**:
   - Replace the path with your actual directory path
   - Add your actual API keys

4. **Restart Cursor IDE** and test with prompts like:
   - "Search for Deutsche Bahn AG in the German business registry"
   - "Analyze the financial data for Siemens Aktiengesellschaft"

### Cline (VS Code Extension)

To use with Cline in VS Code:

1. **Install the Cline extension**

2. **Configure MCP server in Cline settings:**
   ```json
   {
     "cline.mcp": {
       "servers": [
         {
           "name": "bundesanzeiger",
           "command": "python",
           "args": ["server.py"],
           "cwd": "/path/to/your/bundesanzeiger_telegram_bot/mcp_server",
           "env": {
             "OPENROUTER_API_KEY": "your_openrouter_api_key_here",
             "OPENAI_API_KEY": "your_openai_api_key_here"
           }
         }
       ]
     }
   }
   ```

### Custom MCP Client

To integrate with a custom MCP client:

```python
import asyncio
import subprocess
import json
from mcp.client import ClientSession
from mcp.client.stdio import stdio_client

async def use_bundesanzeiger_server():
    # Start the server process
    server_process = subprocess.Popen(
        ["python", "server.py"],
        cwd="/path/to/mcp_server",
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Connect to the server
    async with stdio_client(server_process) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize the session
            await session.initialize()
            
            # List available tools
            tools = await session.list_tools()
            print("Available tools:", [tool.name for tool in tools])
            
            # Search for a company
            search_result = await session.call_tool(
                "search",
                {"company_name": "Deutsche Bahn AG"}
            )
            print("Search result:", search_result)
            
            # Analyze the company
            analyze_result = await session.call_tool(
                "analyze", 
                {"company_name": "Deutsche Bahn AG"}
            )
            print("Analysis result:", analyze_result)

# Run the example
asyncio.run(use_bundesanzeiger_server())
```

## Tool Usage Examples

### Search Tool

**Use case:** Find available financial reports for a German company

```json
{
  "tool": "search",
  "arguments": {
    "company_name": "Volkswagen AG"
  }
}
```

**Response:**
```json
{
  "found": true,
  "searched_name": "Volkswagen AG",
  "reports_count": 2,
  "reports": [
    {
      "name": "Jahresabschluss zum 31.12.2023",
      "company": "Volkswagen AG",
      "date": "2024-05-20T00:00:00",
      "has_financial_data": true
    },
    {
      "name": "Lagebericht 2023",
      "company": "Volkswagen AG", 
      "date": "2024-05-20T00:00:00",
      "has_financial_data": false
    }
  ]
}
```

### Analyze Tool

**Use case:** Extract detailed financial data from reports

```json
{
  "tool": "analyze",
  "arguments": {
    "company_name": "Volkswagen AG"
  }
}
```

**Response:**
```json
{
  "company_name": "Volkswagen AG",
  "found": true,
  "is_cached": false,
  "date": "2024-05-20T00:00:00",
  "financial_data": {
    "earnings_current_year": 18951000000,
    "total_assets": 565425000000,
    "revenue": 322279000000
  },
  "report_name": "Jahresabschluss zum 31.12.2023"
}
```

## LLM Prompt Examples

Here are some example prompts you can use with LLMs connected to this MCP server:

### Basic Company Search
```
"Can you search for BMW AG in the German business registry and tell me what financial reports are available?"
```

### Financial Analysis
```
"Please analyze the financial data for Siemens AG and provide a summary of their key financial metrics."
```

### Comparative Analysis
```
"Compare the financial performance of Deutsche Bahn AG and BMW AG. Search for both companies and analyze their latest financial reports."
```

### Industry Research
```
"I'm researching the German automotive industry. Can you analyze the financial data for Volkswagen AG, BMW AG, and Mercedes-Benz Group AG?"
```

## Error Handling

The server provides detailed error messages for common scenarios:

### Company Not Found
```json
{
  "found": false,
  "message": "No reports found for company: NonExistent Company",
  "searched_name": "NonExistent Company"
}
```

### Analysis Failed
```json
{
  "company_name": "Example AG",
  "found": true,
  "is_cached": false,
  "date": "2024-01-15T00:00:00",
  "report_name": "Jahresabschluss zum 31.12.2023",
  "message": "Found report but couldn't extract financial data"
}
```

## Performance Considerations

1. **Caching:** The server automatically caches results to improve performance for repeated queries
2. **Rate Limiting:** The Bundesanzeiger website may impose rate limits; the server handles this gracefully
3. **CAPTCHA:** The server automatically handles CAPTCHA challenges when they occur
4. **Timeout:** Long-running analysis requests may timeout; consider implementing retry logic in your client

## Troubleshooting

### Common Issues

1. **Import Error:**
   ```bash
   ModuleNotFoundError: No module named 'mcp'
   ```
   **Solution:** Install dependencies: `pip install -r requirements.txt`

2. **OpenAI API Error:**
   ```bash
   Error: OpenAI API key not found
   ```
   **Solution:** Set the `OPENAI_API_KEY` environment variable

3. **Connection Timeout:**
   ```bash
   Error: Connection to Bundesanzeiger failed
   ```
   **Solution:** Check internet connection and try again later

### Debug Mode

To run the server with debug logging:

```bash
PYTHONPATH=../ python -c "
import logging
logging.basicConfig(level=logging.DEBUG)
from server import main
import asyncio
asyncio.run(main())
"
```

## Security Considerations

1. **API Keys:** Never commit API keys to version control
2. **Rate Limiting:** Be respectful of the Bundesanzeiger website's resources
3. **Data Privacy:** Be aware that financial data may be sensitive
4. **Environment Variables:** Use environment variables for configuration

## Support

For issues related to:
- **MCP Protocol:** Check the [MCP documentation](https://modelcontextprotocol.io/)
- **Bundesanzeiger Data:** Refer to the main project documentation
- **Server Issues:** Check the logs and error messages

## Contributing

To contribute improvements to the MCP server:

1. Test your changes with `python test_server.py`
2. Ensure compatibility with the existing Bundesanzeiger functionality
3. Update documentation as needed
4. Submit a pull request with your changes 