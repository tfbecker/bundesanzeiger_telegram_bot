FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Create volume for persistent cache
VOLUME /app/data

# Set environment variable for database path
ENV DB_PATH=/app/data/financial_cache.db

# Run the bot
CMD ["python", "scripts/telegram_bot.py"] 