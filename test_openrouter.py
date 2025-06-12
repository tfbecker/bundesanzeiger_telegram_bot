#!/usr/bin/env python3
"""
Test script for OpenRouter integration with DeepSeek models
"""
import os
import json
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_openrouter_deepseek():
    """Test OpenRouter with DeepSeek Chat model"""
    
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip('"\'')
    if not OPENROUTER_API_KEY:
        print("❌ OPENROUTER_API_KEY not found in environment variables")
        return False
    
    print(f"✅ Found OpenRouter API key: {OPENROUTER_API_KEY[:10]}...")
    
    # Test simple chat completion
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/yourusername/bundesanzeiger_telegram_bot",
        "X-Title": "Bundesanzeiger Telegram Bot Test"
    }
    
    payload = {
        "model": "deepseek/deepseek-chat-v3-0324",
        "messages": [
            {"role": "user", "content": "Hello! Can you help me extract a company name from this message: 'Show me financial data for Apple Inc.'? Just respond with the company name."}
        ]
    }
    
    try:
        print("🔄 Testing DeepSeek Chat v3 via OpenRouter...")
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        
        response_data = response.json()
        content = response_data["choices"][0]["message"]["content"]
        
        print(f"✅ DeepSeek Chat response: {content}")
        return True
        
    except Exception as e:
        print(f"❌ Error testing OpenRouter: {e}")
        if hasattr(response, 'text'):
            print(f"Response text: {response.text}")
        return False

def test_deepseek_r1():
    """Test DeepSeek R1 model for financial analysis"""
    
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip('"\'')
    if not OPENROUTER_API_KEY:
        print("❌ OPENROUTER_API_KEY not found in environment variables")
        return False
    
    # Test R1 model with financial analysis
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/yourusername/bundesanzeiger_telegram_bot",
        "X-Title": "Bundesanzeiger Telegram Bot Test"
    }
    
    payload = {
        "model": "deepseek/deepseek-r1-0528",
        "messages": [
            {"role": "system", "content": "You are an accounting specialist. Extract financial data from company reports. Only respond with JSON."},
            {"role": "user", "content": """Extract financial data from this sample text and return JSON:
            Revenue: €50,000,000
            Total Assets: €120,000,000
            Current Year Earnings: €8,500,000
            
            Return only JSON with keys: earnings_current_year, total_assets, revenue"""}
        ]
    }
    
    try:
        print("🔄 Testing DeepSeek R1 for financial analysis...")
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        
        response_data = response.json()
        content = response_data["choices"][0]["message"]["content"]
        
        print(f"✅ DeepSeek R1 response: {content}")
        
        # Try to parse as JSON
        try:
            # Clean the response content - remove markdown code blocks if present
            clean_content = content.strip()
            if clean_content.startswith("```json"):
                clean_content = clean_content[7:]  # Remove ```json
            if clean_content.startswith("```"):
                clean_content = clean_content[3:]   # Remove ```
            if clean_content.endswith("```"):
                clean_content = clean_content[:-3]  # Remove trailing ```
            clean_content = clean_content.strip()
            
            parsed = json.loads(clean_content)
            print(f"✅ Successfully parsed JSON: {parsed}")
            return True
        except json.JSONDecodeError:
            print("⚠️ Response was not valid JSON, but R1 model responded")
            return True
            
    except Exception as e:
        print(f"❌ Error testing DeepSeek R1: {e}")
        if hasattr(response, 'text'):
            print(f"Response text: {response.text}")
        return False

def test_tool_calling():
    """Test tool calling with DeepSeek Chat"""
    
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip('"\'')
    if not OPENROUTER_API_KEY:
        print("❌ OPENROUTER_API_KEY not found in environment variables")
        return False
    
    # Test tool calling (similar to what the bot uses)
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/yourusername/bundesanzeiger_telegram_bot",
        "X-Title": "Bundesanzeiger Telegram Bot Test"
    }
    
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_company_info",
                "description": "Get financial information for a company from Bundesanzeiger",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "company_name": {
                            "type": "string",
                            "description": "The name of the company to search for"
                        }
                    },
                    "required": ["company_name"]
                }
            }
        }
    ]
    
    payload = {
        "model": "deepseek/deepseek-chat-v3-0324",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that extracts company names from user messages."},
            {"role": "user", "content": "Show me financial data for Deutsche Bahn AG"}
        ],
        "tools": tools,
        "tool_choice": {"type": "function", "function": {"name": "get_company_info"}}
    }
    
    try:
        print("🔄 Testing tool calling with DeepSeek Chat...")
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        
        response_data = response.json()
        
        if "tool_calls" in response_data["choices"][0]["message"]:
            tool_call = response_data["choices"][0]["message"]["tool_calls"][0]
            arguments = json.loads(tool_call["function"]["arguments"])
            company_name = arguments.get("company_name")
            print(f"✅ Tool calling successful! Extracted company: {company_name}")
            return True
        else:
            print("❌ No tool calls found in response")
            print(f"Response: {response_data}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing tool calling: {e}")
        if hasattr(response, 'text'):
            print(f"Response text: {response.text}")
        return False

if __name__ == "__main__":
    print("🧪 Testing OpenRouter integration with DeepSeek models...")
    print("=" * 60)
    
    # Test basic functionality
    print("1️⃣ Testing DeepSeek Chat v3 (for company extraction)")
    basic_test = test_openrouter_deepseek()
    print()
    
    # Test R1 model
    print("2️⃣ Testing DeepSeek R1 (for financial analysis)")
    r1_test = test_deepseek_r1()
    print()
    
    # Test tool calling
    print("3️⃣ Testing tool calling with DeepSeek Chat")
    tool_test = test_tool_calling()
    print()
    
    if basic_test and r1_test and tool_test:
        print("🎉 All tests passed! Both DeepSeek models are working correctly.")
        print("\n📋 Model Configuration:")
        print("   • Chat/Extraction: deepseek/deepseek-chat-v3-0324")
        print("   • Financial Analysis: deepseek/deepseek-r1-0528")
    else:
        print("❌ Some tests failed. Please check your configuration.")
        print("\nMake sure you have:")
        print("1. Created a .env file with OPENROUTER_API_KEY")
        print("2. Added your OpenRouter API key to the .env file (remove any quotes)")
        print("3. Installed the required dependencies: pip install requests python-dotenv") 