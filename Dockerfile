# Use official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables for Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create app/data directory with proper permissions
RUN mkdir -p /app/data && \
    chmod 777 /app/data

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create a non-root user and set permissions
RUN useradd -m myuser && \
    # Set ownership for app files
    chown -R myuser:myuser /app

# Switch to non-root user
USER myuser

# Set the default command to run the bot
CMD ["python", "main.py"]
