#!/usr/bin/env python
"""
Main entry point for the BetterSaved Telegram bot.
"""
import logging
import os
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
    # Load environment variables from .env file if it exists
    load_dotenv()
    
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