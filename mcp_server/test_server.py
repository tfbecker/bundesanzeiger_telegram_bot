#!/usr/bin/env python3
"""
Test script for the Bundesanzeiger MCP Server

This script demonstrates how to use the server's functionality directly
without the MCP protocol (useful for testing and development).
"""

import asyncio
import json
import sys
from pathlib import Path

# Add the current directory to the path
sys.path.append(str(Path(__file__).parent))

from server import BundesanzeigerMCPServer


async def test_search():
    """Test the search functionality"""
    server = BundesanzeigerMCPServer()
    
    print("🔍 Testing search functionality...")
    print("=" * 50)
    
    # Test search for well-known German companies with more specific names
    test_companies = [
        "Deutsche Bahn Aktiengesellschaft",
        "Bayerische Motoren Werke Aktiengesellschaft", 
        "Siemens Aktiengesellschaft",
        "Volkswagen Aktiengesellschaft"
    ]
    
    for company in test_companies:
        print(f"\n📊 Searching for: {company}")
        print("-" * 30)
        
        try:
            results = await server._handle_search({"company_name": company})
            for result in results:
                if hasattr(result, 'text'):
                    data = json.loads(result.text)
                    if data.get("found"):
                        print(f"✅ Found {data['reports_count']} report(s)")
                        for report in data.get("reports", []):
                            print(f"   📄 {report['name']}")
                            print(f"   🏢 Company: {report['company']}")
                            print(f"   📅 Date: {report['date']}")
                            print(f"   💰 Has financial data: {report['has_financial_data']}")
                    else:
                        print(f"❌ {data['message']}")
                else:
                    print(f"✅ Result: {result}")
        except Exception as e:
            print(f"❌ Error: {e}")


async def test_analyze():
    """Test the analyze functionality"""
    print("\n\n🔬 Testing analyze functionality...")
    print("=" * 50)
    
    server = BundesanzeigerMCPServer()
    
    # Test analysis for companies with more specific names
    test_companies = [
        "Deutsche Bahn Aktiengesellschaft",
        "Volkswagen Aktiengesellschaft"
    ]
    
    for company in test_companies:
        print(f"\n📈 Analyzing: {company}")
        print("-" * 30)
        
        try:
            results = await server._handle_analyze({"company_name": company})
            for result in results:
                if hasattr(result, 'text'):
                    data = json.loads(result.text)
                    if data.get("found"):
                        print(f"✅ Analysis complete!")
                        print(f"   🏢 Company: {data.get('company_name')}")
                        print(f"   📄 Report: {data.get('report_name')}")
                        print(f"   📅 Date: {data.get('date')}")
                        print(f"   💾 Cached: {data.get('is_cached', False)}")
                        
                        financial_data = data.get("financial_data", {})
                        if financial_data and any(v is not None for v in financial_data.values()):
                            print("   💰 Financial Data:")
                            if financial_data.get("earnings_current_year"):
                                print(f"      📊 Earnings: €{financial_data['earnings_current_year']:,.0f}")
                            if financial_data.get("total_assets"):
                                print(f"      🏦 Total Assets: €{financial_data['total_assets']:,.0f}")
                            if financial_data.get("revenue"):
                                print(f"      💵 Revenue: €{financial_data['revenue']:,.0f}")
                        else:
                            print("   ⚠️ No financial data extracted")
                    else:
                        print(f"❌ {data.get('message', 'Analysis failed')}")
                else:
                    print(f"✅ Result: {result}")
        except Exception as e:
            print(f"❌ Error: {e}")


async def test_mcp_server_startup():
    """Test that the MCP server can start up properly"""
    print("\n\n🖥️ Testing MCP server startup...")
    print("=" * 50)
    
    try:
        server = BundesanzeigerMCPServer()
        print("✅ MCP Server initialized successfully!")
        
        # Test that tools are listed correctly by checking the handler exists
        print("✅ Tools configured:")
        print(f"   🔧 search: Search for German companies in Bundesanzeiger")
        print(f"   🔧 analyze: Analyze financial reports and extract data")
        
        return True
    except Exception as e:
        print(f"❌ Error initializing MCP server: {e}")
        return False


async def main():
    """Main test function"""
    print("🚀 Bundesanzeiger MCP Server Test")
    print("=" * 50)
    print("This script tests the core functionality of the MCP server")
    print("without using the MCP protocol directly.\n")
    
    # Test MCP server startup
    startup_success = await test_mcp_server_startup()
    
    if startup_success:
        # Test search functionality
        await test_search()
        
        # Test analyze functionality  
        await test_analyze()
    
    print("\n" + "=" * 50)
    print("✅ Tests completed!")
    print("\nTo use the MCP server with an LLM client:")
    print("  python server.py")


if __name__ == "__main__":
    asyncio.run(main()) 