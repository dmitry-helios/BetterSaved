#!/usr/bin/env python
"""
Main entry point for the Echo Telegram bot. test
"""
import logging
import os
import sys
from dotenv import load_dotenv

from bot import BetterSavedBot

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    """Start the bot."""
    # Determine which environment to load
    env_file = ".env.test"  # Default to test
    if len(sys.argv) > 1 and sys.argv[1].lower() == "prod":
        env_file = ".env.prod"
    load_dotenv(env_file)
    
    # Get the token from environment variable
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        logger.error("No token provided. Set TELEGRAM_TOKEN environment variable.")
        return
    
    # Create and start the bot
    bot = BetterSavedBot(token)
    bot.start()

if __name__ == "__main__":
    main()