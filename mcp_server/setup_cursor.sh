#!/bin/bash
# Setup script for Cursor IDE MCP integration

echo "🎯 Bundesanzeiger MCP Server - Cursor IDE Setup"
echo "=" * 50

# Get the current directory path
CURRENT_DIR=$(pwd)
PARENT_DIR=$(dirname "$CURRENT_DIR")

echo "📁 Detected paths:"
echo "   MCP Server directory: $CURRENT_DIR"
echo "   Project root: $PARENT_DIR"

# Check if we're in the right directory
if [[ ! -f "server.py" ]]; then
    echo "❌ Error: server.py not found. Please run this script from the mcp_server directory."
    exit 1
fi

# Check for required files
if [[ ! -f "../.env" ]] && [[ ! -f ".env" ]]; then
    echo "⚠️  Warning: No .env file found. Make sure to set your API keys manually."
fi

# Generate the Cursor IDE configuration
echo ""
echo "📋 Cursor IDE MCP Configuration:"
echo "   Copy this configuration to your Cursor IDE settings:"
echo ""
echo "┌─────────────────────────────────────────────────────────────┐"
echo "│ Cursor IDE Settings (Cmd/Ctrl + , → Search 'MCP')          │"
echo "└─────────────────────────────────────────────────────────────┘"

cat << EOF

{
  "mcp.servers": [
    {
      "name": "bundesanzeiger",
      "command": "python",
      "args": ["server.py"],
      "cwd": "$CURRENT_DIR",
      "env": {
        "OPENROUTER_API_KEY": "your_openrouter_api_key_here",
        "OPENAI_API_KEY": "your_openai_api_key_here"
      }
    }
  ]
}

EOF

echo ""
echo "🔧 Setup Instructions:"
echo "1. Open Cursor IDE"
echo "2. Go to Settings (Cmd/Ctrl + ,)"
echo "3. Search for 'MCP' in settings"
echo "4. Add the configuration above"
echo "5. Replace 'your_openrouter_api_key_here' and 'your_openai_api_key_here' with your actual API keys"
echo "6. Restart Cursor IDE"
echo ""
echo "✅ Test with these prompts:"
echo "   • 'Search for Deutsche Bahn AG in the German business registry'"
echo "   • 'Analyze the financial data for Siemens Aktiengesellschaft'"
echo "   • 'What are the latest financial reports for Volkswagen AG?'"
echo ""
echo "📖 For more information, see:"
echo "   • README.md - Basic usage"
echo "   • INTEGRATION.md - Detailed integration guide"
echo ""
echo "🎉 Happy analyzing German company financials with Cursor IDE!" 