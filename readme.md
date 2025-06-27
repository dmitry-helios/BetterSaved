# BetterSaved Telegram Bot

BetterSaved is a Telegram bot designed to help users save, organize, and manage messages, media, and files directly to Google Drive and Google Sheets. The bot is built with Python and leverages Google APIs for Drive and Sheets integration.

## Features
- Save messages and media from Telegram chats to Google Drive
- Organize files by type (Images, Video, Audio, PDF, Tickets) and by month
- Store message metadata in a Google Sheet for easy search and reference
- OAuth2 authentication for secure Google account access
- Automated folder and spreadsheet creation in Google Drive

## Project Structure
```
bot.py                # Main bot logic
main.py               # Entry point for running the bot
requirements.txt      # Python dependencies
client_secret.json    # Google API credentials (not tracked in git)
database.py           # (Optional) Local database logic
google_auth.py        # Google OAuth and Drive/Sheets integration
media/                # Media assets (e.g., bot banner)
deploy.bat            # Deployment script for EC2
```

## Setup Instructions
1. **Clone the repository**
   ```
   git clone <your-repo-url>
   cd BetterSaved
   ```
2. **Create a virtual environment and install dependencies**
   ```
   python -m venv venv
   venv\Scripts\activate  # On Windows
   # or
   source venv/bin/activate  # On Linux/Mac
   pip install -r requirements.txt
   ```
3. **Add your Google API credentials**
   - Place your `client_secret.json` in the project root (do not commit this file).
   - The bot will guide you through OAuth2 authentication on first run.
4. **Configure your Telegram bot token**
   - Store your Telegram bot token securely (e.g., in an `.env` file or as an environment variable).
5. **Run the bot**
   ```
   python main.py
   ```

## Deployment
- The bot can be deployed to an AWS EC2 instance or any server with Python 3.8+.
- Use the provided `deploy.bat` script for automated deployment to EC2.

## Security
- Sensitive files such as `client_secret.json`, `token.json`, `bot-key.pem`, and backup files are excluded from version control via `.gitignore`.
- Never commit your secrets or keys to the repository.

## Contributing
Pull requests are welcome! Please open an issue first to discuss major changes.

## License
MIT License
