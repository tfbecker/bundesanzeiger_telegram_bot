#!/usr/bin/env python3
"""
MCP Server for Bundesanzeiger Financial Data

This server exposes two main tools:
1. search - Search for German companies in Bundesanzeiger
2. analyze - Analyze financial reports for a specific company
"""

import asyncio
import json
import logging
import sys
import os
from pathlib import Path
from typing import Any, Sequence
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource,
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
    LoggingLevel,
    ServerCapabilities,
)
import mcp.types as types

# Set up logging first
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add the parent directory to the Python path for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'scripts'))

try:
    from scripts.bundesanzeiger import Bundesanzeiger
    logger.debug("Successfully imported Bundesanzeiger from scripts")
except ImportError as e:
    logger.debug(f"Failed to import from scripts: {e}")
    try:
        from bundesanzeiger import Bundesanzeiger
        logger.debug("Successfully imported Bundesanzeiger directly")
    except ImportError as e2:
        logger.error(f"Could not import Bundesanzeiger: {e2}")
        raise

class BundesanzeigerMCPServer:
    """MCP Server wrapper for Bundesanzeiger functionality"""
    
    def __init__(self):
        self.server = Server("bundesanzeiger")
        
        # Set up database path in the main project data directory
        data_dir = os.path.join(project_root, "data")
        os.makedirs(data_dir, exist_ok=True)
        db_path = os.path.join(data_dir, "financial_cache.db")
        
        # Set the database path as environment variable so the cache class uses it
        os.environ['DB_PATH'] = db_path
        
        self.bundesanzeiger = Bundesanzeiger()
        self.setup_handlers()
    
    def setup_handlers(self):
        """Set up MCP server handlers"""
        
        @self.server.list_tools()
        async def handle_list_tools() -> list[Tool]:
            """List available tools"""
            return [
                Tool(
                    name="search",
                    description="Search for German companies in the Bundesanzeiger database. Returns basic company information and list of available reports WITHOUT processing financial data. Use this first to find companies, then use 'analyze' to get financial details.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "company_name": {
                                "type": "string",
                                "description": "Name of the German company to search for (e.g., 'Deutsche Bahn AG', 'BMW AG')"
                            }
                        },
                        "required": ["company_name"]
                    }
                ),
                Tool(
                    name="analyze",
                    description="Analyze financial reports for a specific German company. Processes the actual report content using AI to extract earnings, assets, and revenue. Use the exact company name returned from the search results.",
                    inputSchema={
                        "type": "object", 
                        "properties": {
                            "company_name": {
                                "type": "string",
                                "description": "Exact name of the German company to analyze (should match the name returned from search results)"
                            }
                        },
                        "required": ["company_name"]
                    }
                )
            ]
        
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
            """Handle tool execution"""
            if name == "search":
                return await self._handle_search(arguments or {})
            elif name == "analyze":
                return await self._handle_analyze(arguments or {})
            else:
                raise ValueError(f"Unknown tool: {name}")
    
    async def _handle_search(self, arguments: dict) -> list[TextContent]:
        """Handle search tool calls - return basic search results only"""
        try:
            company_name = arguments.get("company_name")
            if not company_name:
                return [TextContent(
                    type="text",
                    text="Error: company_name is required"
                )]
            
            logger.info(f"Searching for company: {company_name}")
            
            # Use a new method that only returns basic search results without processing reports
            search_results = self.bundesanzeiger.search_companies(company_name)
            
            if not search_results:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "found": False,
                        "message": f"No reports found for company: {company_name}",
                        "searched_name": company_name
                    }, indent=2)
                )]
            
            return [TextContent(
                type="text",
                text=json.dumps(search_results, indent=2, default=str)
            )]
            
        except Exception as e:
            logger.error(f"Error in search: {e}")
            return [TextContent(
                type="text",
                text=f"Error searching for company: {str(e)}"
            )]
    
    async def _handle_analyze(self, arguments: dict) -> list[TextContent]:
        """Handle analyze tool calls"""
        try:
            company_name = arguments.get("company_name")
            if not company_name:
                return [TextContent(
                    type="text",
                    text="Error: company_name is required"
                )]
            
            logger.info(f"Analyzing company: {company_name}")
            
            # Use the existing get_company_financial_info method
            financial_info = self.bundesanzeiger.get_company_financial_info(company_name)
            
            return [TextContent(
                type="text", 
                text=json.dumps(financial_info, indent=2, default=str)
            )]
            
        except Exception as e:
            logger.error(f"Error in analyze: {e}")
            return [TextContent(
                type="text",
                text=f"Error analyzing company: {str(e)}"
            )]
    
    async def run(self):
        """Run the MCP server"""
        try:
            async with stdio_server() as (read_stream, write_stream):
                await self.server.run(
                    read_stream,
                    write_stream,
                    InitializationOptions(
                        server_name="bundesanzeiger",
                        server_version="1.0.0",
                        capabilities=ServerCapabilities(
                            tools={},
                        ),
                    ),
                )
        except Exception as e:
            logger.error(f"Server error: {e}")
            raise


async def main():
    """Main entry point"""
    server = BundesanzeigerMCPServer()
    await server.run()


if __name__ == "__main__":
    asyncio.run(main()) 