#!/usr/bin/env python3
"""
Setup script for Bundesanzeiger MCP Server
"""

from setuptools import setup, find_packages

setup(
    name="bundesanzeiger-mcp-server",
    version="1.0.0",
    description="MCP Server for Bundesanzeiger Financial Data",
    author="Your Name",
    author_email="your.email@example.com",
    packages=find_packages(),
    install_requires=[
        "mcp>=1.0.0",
        "requests>=2.31.0",
        "python-dotenv>=1.0.0",
        "beautifulsoup4>=4.12.0",
        "numpy>=1.24.0",
        "fuzzywuzzy>=0.18.0",
        "python-Levenshtein>=0.20.0",
        "dateparser>=1.2.0",
        "deutschland>=0.1.1",
        "matplotlib",
    ],
    entry_points={
        "console_scripts": [
            "bundesanzeiger-mcp-server=server:main",
        ],
    },
    python_requires=">=3.9",
) 