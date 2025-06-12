#!/bin/bash
# Run the Bundesanzeiger MCP Server

echo "🚀 Starting Bundesanzeiger MCP Server..."
echo "=" * 50

# Check if we're in the right directory
if [[ ! -f "server.py" ]]; then
    echo "❌ Error: server.py not found. Make sure you're in the mcp_server directory."
    exit 1
fi

# Check if .env file exists in parent directory
if [[ ! -f "../.env" ]]; then
    echo "⚠️  Warning: .env file not found in parent directory."
    echo "   Make sure to set up your environment variables (OPENAI_API_KEY, etc.)"
fi

# Check if dependencies are installed
python -c "import mcp" 2>/dev/null
if [[ $? -ne 0 ]]; then
    echo "❌ Error: MCP library not installed."
    echo "   Run: pip install -r requirements.txt"
    exit 1
fi

echo "✅ Starting server..."
echo "   The server will communicate via stdin/stdout using the MCP protocol."
echo "   To test the server functionality, run: python test_server.py"
echo ""

# Run the server
python server.py 