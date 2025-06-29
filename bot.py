"""
Simple Telegram bot for BetterSaved - AWS EC2 deployment.
testin1g
"""
import logging
import os
import json
import traceback
from datetime import datetime
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler,
    CallbackQueryHandler
)
from database import Database
from google_auth import GoogleDriveManager
import asyncio
import sys
from logging.handlers import RotatingFileHandler

# Create logs directory if it doesn't exist
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(log_dir, exist_ok=True)

# Set up file handler
log_file = os.path.join(log_dir, 'telegram_bot.log')
file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

# Set up console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

# Configure root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

# Get logger for this module
logger = logging.getLogger(__name__)
logger.info("Logging configured to file: %s", log_file)

# Import Google API libraries directly
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError

# Load the message texts
def load_messages():
    with open('message_text.json', 'r', encoding='utf-8') as f:
        return json.load(f)

# Load all messages
MESSAGES = load_messages()

class BetterSavedBot:
    """Simple Telegram bot for BetterSaved with database integration."""
    
    # Define conversation states
    WAITING_FOR_AUTH_CODE = 1
    WAITING_FOR_NUKE_CONFIRMATION = 2
    
    def __init__(self, token):
        """Initialize the bot with the given token."""
        self.token = token
        self.application = Application.builder().token(token).build()
        
        # Initialize database
        self.db = Database()
        
        # Initialize Google Drive manager
        self.drive_manager = GoogleDriveManager()
        
        # Register handlers
        self._register_handlers()
        
    def _register_handlers(self):
        """Register command and message handlers."""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("user", self.user_command))
        self.application.add_handler(CommandHandler("disconnect_drive", self.disconnect_drive_command))
        self.application.add_handler(CommandHandler("fix_spreadsheet", self.fix_spreadsheet_command))
        
        # Conversation handler for Google Drive authentication
        # This must come BEFORE the general message handler
        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler("connect_drive", self.connect_drive_command),
                CallbackQueryHandler(self.connect_drive_command, pattern="^connect_drive$")
            ],
            states={
                self.WAITING_FOR_AUTH_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_auth_code)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel_auth)],
            name="drive_auth_conversation"
        )
        self.application.add_handler(conv_handler)

        # Add nuke_user command with conversation handler
        nuke_handler = ConversationHandler(
            entry_points=[CommandHandler("nuke_user", self.nuke_user_command)],
            states={
                self.WAITING_FOR_NUKE_CONFIRMATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_nuke_confirmation)]
            },
            fallbacks=[CommandHandler("cancel", self.cancel_command)]
        )
        self.application.add_handler(nuke_handler)
        

        
        # Message handlers - must come AFTER conversation handlers
        # Register callback query handler for button clicks
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        
        # Register message handler for all other messages
        self.application.add_handler(MessageHandler(~filters.COMMAND, self.respond_to_message))
        
        # Error handler
        self.application.add_error_handler(self.error_handler)
        
        logger.info("All handlers registered successfully")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a message when the command /start is issued and register the user."""
        user = update.effective_user
        
        # Create or update user in the database
        self.db.create_or_update_user(
            telegram_id=str(user.id),
            name=user.full_name or user.first_name
        )
        
        # Welcome message caption with HTML formatting
        welcome_caption = (f"{MESSAGES['en']['welcome']['title']}\n\n{MESSAGES['en']['welcome']['description']}")
        
        # Create inline keyboard buttons
        keyboard = [
            [InlineKeyboardButton(MESSAGES['en']['welcome']['buttons']['connect_drive'], callback_data="connect_drive")],
            [InlineKeyboardButton(MESSAGES['en']['welcome']['buttons']['settings'], callback_data="settings")],
            [InlineKeyboardButton(MESSAGES['en']['welcome']['buttons']['about'], callback_data="about"), 
             InlineKeyboardButton(MESSAGES['en']['welcome']['buttons']['donate'], callback_data="donate")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Path to the banner image
        banner_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'media', 'bot-banner.png')
        
        try:
            # Send the welcome banner with caption and buttons
            with open(banner_path, 'rb') as banner_file:
                await update.message.reply_photo(
                    photo=banner_file,
                    caption=welcome_caption,
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )
            logger.info(f"Sent welcome banner to user {user.id}")
        except Exception as e:
            # Fallback to text-only message if image sending fails
            logger.error(f"Failed to send welcome banner: {e}")
            await update.message.reply_text(
                f"Hi {user.first_name}! {welcome_caption}",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a message when the command /help is issued."""
        help_text = (
            "Here's what I can do:\n\n"
            "- Send me any text message, and I'll save it to your Google Sheets\n"
            "- Send me images, videos, audio, PDFs, and other files to save them to your Google Drive\n"
            "- Use /start to get started\n"
            "- Use /user to see your user information\n"
            "- Use /connect_drive to connect your Google Drive\n"
            "- Use /disconnect_drive to revoke Drive access\n"
            "- Use /fix_spreadsheet if you're having issues saving messages\n"
            "- Use /nuke_user to completely delete your account data\n"
            "- Use /help to see this message again"
        )
        await update.message.reply_text(help_text)
    
    async def respond_to_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process and save user messages."""
        user = update.effective_user
        telegram_id = str(user.id)
        message = update.message
        
        # Detailed message debugging
        logger.info(f"Received message from {telegram_id}")
        logger.info(f"Message object type: {type(message)}")
        logger.info(f"Message attributes: {dir(message)}")
        logger.info(f"Message text: {message.text if hasattr(message, 'text') else 'No text'}")
        logger.info(f"Has photo: {bool(message.photo) if hasattr(message, 'photo') else False}")
        logger.info(f"Has document: {bool(message.document) if hasattr(message, 'document') else False}")
        logger.info(f"Has video: {bool(message.video) if hasattr(message, 'video') else False}")
        logger.info(f"Has audio: {bool(message.audio) if hasattr(message, 'audio') else False}")
        logger.info(f"Has voice: {bool(message.voice) if hasattr(message, 'voice') else False}")
        logger.info(f"Has sticker: {bool(message.sticker) if hasattr(message, 'sticker') else False}")
        
        # More reliable way to check for attachments
        has_attachment = False
        attachment_type = None
        
        # Check each possible attachment type
        if message.photo:
            # Photos are handled specially - don't mark as attachment to reject
            logger.info(f"Photo detected: {message.photo}")
            await self._handle_photo_message(update, context)
            return
        elif message.document:
            # Check document type by mime type
            mime_type = message.document.mime_type or ""
            
            if mime_type.startswith("image/"):
                # Image document
                logger.info(f"Image document detected: {message.document.file_name}, {mime_type}")
                await self._handle_image_document(update, context)
                return
            elif mime_type == "application/pdf":
                # PDF document
                logger.info(f"PDF document detected: {message.document.file_name}")
                await self._handle_pdf_document(update, context)
                return
            elif mime_type.startswith("audio/") or mime_type == "application/ogg":
                # Audio document
                logger.info(f"Audio document detected: {message.document.file_name}, {mime_type}")
                await self._handle_audio_document(update, context)
                return
            elif mime_type.startswith("video/"):
                # Video document
                logger.info(f"Video document detected: {message.document.file_name}, {mime_type}")
                await self._handle_video_document(update, context)
                return
            else:
                # Other document types
                logger.info(f"Misc document detected: {message.document.file_name}, {mime_type}")
                await self._handle_misc_document(update, context)
                return
        elif message.video:
            logger.info(f"Video message detected")
            await self._handle_video_message(update, context)
            return
        elif message.audio:
            logger.info(f"Audio message detected")
            await self._handle_audio_message(update, context)
            return
        elif message.voice:
            logger.info(f"Voice message detected")
            await self._handle_voice_message(update, context)
            return
        elif message.video_note:
            logger.info(f"Video note (circular video) detected")
            await self._handle_video_note(update, context)
            return
        elif message.sticker:
            has_attachment = True
            attachment_type = "sticker"
        elif message.animation:
            has_attachment = True
            attachment_type = "animation"
        elif message.location:
            has_attachment = True
            attachment_type = "location"
        elif message.contact:
            has_attachment = True
            attachment_type = "contact"
        elif message.poll:
            has_attachment = True
            attachment_type = "poll"
        elif message.venue:
            has_attachment = True
            attachment_type = "venue"
        elif message.game:
            has_attachment = True
            attachment_type = "game"
        elif message.dice:
            has_attachment = True
            attachment_type = "dice"
        
        # Check for media group messages
        if message.media_group_id is not None:
            has_attachment = True
            attachment_type = "media_group"
            logger.info(f"Media group detected: {message.media_group_id}")
        
        # Check for forwarded messages
        is_forwarded = message.forward_date is not None
        
        if has_attachment:
            logger.info(f"Attachment detected in message from {telegram_id}: {attachment_type}")
            
            # Get more detailed info for document types
            document_info = ""
            if attachment_type == "document" and message.document:
                mime_type = message.document.mime_type or "unknown type"
                file_name = message.document.file_name or "unnamed file"
                file_size = message.document.file_size or 0
                file_size_kb = file_size / 1024 if file_size else 0
                document_info = f" ({file_name}, {mime_type}, {file_size_kb:.1f} KB)"
                logger.info(f"Document details: {file_name}, {mime_type}, {file_size_kb:.1f} KB")
            
            # Create a more informative response message
            await message.reply_text(
                f"I'm a very young bot and I can't deal with {attachment_type}{document_info} attachments yet. \n\n"
                f"In the future, I'll be able to save {attachment_type} files to your Google Drive, but for now, "
                f"please send text messages only."
            )
            return
            
        # Handle forwarded messages
        if is_forwarded:
            logger.info(f"Forwarded message detected from {telegram_id}")
            # We'll still process forwarded messages, but log them differently
        
        # Process text message
        if message.text:
            # Get complete user data for debugging
            user_data = self.db.debug_view_user(telegram_id)
            logger.info(f"Complete user data: {user_data}")
            
            # Get user's Drive token and spreadsheet info
            token_json = self.db.get_user_drive_token(telegram_id)
            drive_info = self.db.get_user_drive_info(telegram_id)
            
            # Debug logging
            logger.info(f"User {telegram_id} drive info: {drive_info}")
            
            # Check if user has connected Google Drive
            if not token_json:
                logger.info(f"User {telegram_id} has no Google Drive token")
                
                # Check if we've already shown the connect message to this user
                if not self.db.check_connect_msg_shown(telegram_id):
                    # First time showing the message - send it and mark as shown
                    await message.reply_text(
                        "If you want your messages to be saved to your Google Drive, <b>you need to connect your Google Drive account first</b>.\n\n"
                        "Use /connect_drive to get started.\n\n"
                        "You can still use this without a Drive connection just as you would your regular Saved Messages.",
                        parse_mode='HTML'
                    )
                    self.db.mark_connect_msg_shown(telegram_id)
                return
            
            # Try to recover spreadsheet info if missing
            if not drive_info or not drive_info.get('spreadsheet_id'):
                logger.info(f"Attempting to recover Drive info for user {telegram_id}")
                
                # Try to parse token and get folder ID from user data
                try:
                    token_info = json.loads(token_json)
                    folder_id = user_data.get('folder_id', '')
                    
                    if folder_id:
                        # We have a folder ID, try to find the spreadsheet in it
                        logger.info(f"Found folder_id {folder_id}, searching for spreadsheet")
                        
                        # Create credentials from token
                        credentials = self.drive_manager.create_credentials_from_token_info(token_info)
                        
                        # Build the Drive API client
                        drive_service = build('drive', 'v3', credentials=credentials)
                        
                        # Search for the spreadsheet in the folder
                        results = drive_service.files().list(
                            q=f"name='BetterSavedMessages' and mimeType='application/vnd.google-apps.spreadsheet' and '{folder_id}' in parents and trashed=false",
                            spaces='drive',
                            fields='files(id, name)'
                        ).execute()
                        
                        items = results.get('files', [])
                        
                        if items:
                            # Found the spreadsheet, update the database
                            spreadsheet_id = items[0]['id']
                            spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
                            
                            logger.info(f"Found spreadsheet with ID: {spreadsheet_id}")
                            self.db.update_drive_spreadsheet_info(telegram_id, spreadsheet_id, spreadsheet_url)
                            
                            # Update drive_info with the recovered data
                            drive_info = self.db.get_user_drive_info(telegram_id)
                            logger.info(f"Updated drive info: {drive_info}")
                        else:
                            # No spreadsheet found, create one
                            logger.info("No spreadsheet found, creating a new one")
                            spreadsheet_result = self.drive_manager.create_spreadsheet(credentials, folder_id)
                            
                            if spreadsheet_result.get('success'):
                                spreadsheet_id = spreadsheet_result.get('spreadsheet_id', '')
                                spreadsheet_url = spreadsheet_result.get('spreadsheet_url', '')
                                
                                if spreadsheet_id and spreadsheet_url:
                                    self.db.update_drive_spreadsheet_info(telegram_id, spreadsheet_id, spreadsheet_url)
                                    drive_info = self.db.get_user_drive_info(telegram_id)
                                    logger.info(f"Created new spreadsheet and updated drive info: {drive_info}")
                except Exception as e:
                    logger.error(f"Error recovering spreadsheet info: {e}")
            
            # Check if recovery was successful
            if not drive_info or not drive_info.get('spreadsheet_id'):
                logger.error(f"Recovery failed, no spreadsheet info available")
                await message.reply_text(
                    "You don't have a BetterSaved spreadsheet set up. "
                    "Please reconnect your Google Drive with /connect_drive."
                )
                return
            
            # Save message to spreadsheet
            try:
                # Parse token JSON
                token_info = json.loads(token_json)
                spreadsheet_id = drive_info.get('spreadsheet_id')
                
                # Show saving indicator
                saving_message = await message.reply_text("💾 Saving your message...")
                
                # Prepare message metadata
                message_metadata = {
                    'text': message.text,
                    'is_forwarded': is_forwarded,
                    'forward_date': message.forward_date.isoformat() if message.forward_date else None,
                    'forward_from': None,
                    'forward_from_chat': None
                }
                
                # Add forwarding information if available
                if message.forward_from:
                    message_metadata['forward_from'] = message.forward_from.full_name or message.forward_from.first_name
                elif message.forward_from_chat:
                    message_metadata['forward_from_chat'] = message.forward_from_chat.title or message.forward_from_chat.username
                
                # Save to Google Sheets
                result = self.drive_manager.save_message_to_sheet(token_info, spreadsheet_id, message_metadata)
                
                if result['success']:
                    # Update the saving message with success and auto-delete notice
                    await saving_message.edit_text(
                        "✅ Message saved to your BetterSaved spreadsheet!\n\n"
                        "This message will disappear in a few seconds."
                    )
                    
                    # Schedule message deletion after 5 seconds (non-blocking)
                    asyncio.create_task(self._delete_message_after_delay(saving_message, 5))
                else:
                    error = result.get('error', 'Unknown error')
                    logger.error(f"Failed to save message for user {telegram_id}: {error}")
                    await saving_message.edit_text(
                        "❌ Failed to save your message. Please try again later."
                    )
            except Exception as e:
                logger.error(f"Error processing message for user {telegram_id}: {e}")
                await message.reply_text(
                    "❌ An error occurred while saving your message. Please try again later."
                )
    
    async def error_handler(self, update, context):
        """Log errors caused by updates."""
        logger.error(f"Update {update} caused error {context.error}")
    
    async def user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Display user information when the command /user is issued."""
        user = update.effective_user
        telegram_id = str(user.id)
        
        # Get user from database
        db_user = self.db.get_user_by_telegram_id(telegram_id)
        
        if db_user:
            # User exists in database
            user_info = (
                f"📊 *Your User Information*\n\n"
                f"🆔 User ID: `{db_user['user_id']}`\n"
                f"🔢 Telegram ID: `{db_user['telegram_id']}`\n"
                f"👤 Name: {db_user['name']}\n"
                f"Language: {db_user['lang']}\n"
            )
            
            # Add Google Drive key info if available
            if db_user['key_gdrive']:
                user_info += f"🔑 Google Drive Connection: Set Successfully!\n"
            else:
                user_info += "🔑 Google Drive Connection: Not set up\n"
                
            await update.message.reply_text(user_info, parse_mode='Markdown')
        else:
            # User not found - should not happen as we register users on start
            user_id = self.db.create_or_update_user(
                telegram_id=telegram_id,
                name=user.full_name or user.first_name
            )
            await update.message.reply_text(
                f"You've been registered with User ID: {user_id}\n"
                f"Use /user to see your information."
            )
    
    async def set_commands(self):
        """Set bot commands to be shown in the Telegram UI."""
        commands = [
            BotCommand("start", "Start the bot and register your user"),
            BotCommand("help", "Get help information"),
            BotCommand("user", "View your user information"),
            BotCommand("connect_drive", "Connect your Google Drive account"),
            BotCommand("disconnect_drive", "Disconnect your Google Drive account"),
            BotCommand("fix_spreadsheet", "Run this if you have spreadsheet detection issues")
        ]
        await self.application.bot.set_my_commands(commands)
        logger.info("Bot commands have been set")
    
    def start(self):
        """Start the bot."""
        logger.info("Starting bot...")
        
        # Don't set commands before starting the bot
        # We'll use post_init hook instead
        self.application.post_init = self.post_init
        
        # Start the bot
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

    async def post_init(self, application: Application) -> None:
        """Post-initialization hook for the application."""
        await self.set_commands()
        
    async def set_commands(self):
        """Set the bot's command menu."""
        commands = [
            BotCommand("start", "Start the bot and get a welcome message"),
            BotCommand("help", "Show help information"),
            BotCommand("connect_drive", "Connect your Google Drive account"),
            BotCommand("disconnect_drive", "Disconnect your Google Drive account"),
            BotCommand("fix_spreadsheet", "Fix issues with your spreadsheet"),
            BotCommand("nuke_user", "Delete your account and all data")
        ]
        
        await self.application.bot.set_my_commands(commands)
        logger.info("Bot commands have been set")
        
    async def connect_drive_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start the Google Drive connection process."""
        try:
            telegram_id = str(update.effective_user.id)
            logger.info(f"Starting Google Drive connection for user {telegram_id}")
            
            # Get the authorization URL
            auth_url, state = self.drive_manager.get_authorization_url()
            context.user_data['oauth_state'] = state
            
            # Prepare the message with instructions
            instructions = (
                "🔗 <b>Connect Google Drive</b>\n\n"
                "1. Click the link below to authorize access to your Google Drive\n"
                "2. After allowing access, you'll get an authorization code\n"
                "3. Copy that code and send it to me\n\n"
                f"<a href='{auth_url}'>🔗 Click here to authorize Google Drive</a>\n\n"
                "<i>This will create a 'BetterSaved' folder in your Google Drive where all your saved messages will be stored.</i>"
            )
            
            # Send the message based on the update type
            try:
                if update.callback_query:
                    # If called from a button click
                    await update.callback_query.message.reply_text(
                        text=instructions,
                        parse_mode='HTML',
                        disable_web_page_preview=True
                    )
                else:
                    # If called from a command
                    await update.message.reply_text(
                        text=instructions,
                        parse_mode='HTML',
                        disable_web_page_preview=True
                    )
                
                return self.WAITING_FOR_AUTH_CODE
                
            except Exception as e:
                logger.error(f"Error sending message: {e}")
                # Try alternative way if the first attempt fails
                try:
                    if update.effective_chat:
                        await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text=instructions,
                            parse_mode='HTML',
                            disable_web_page_preview=True
                        )
                        return self.WAITING_FOR_AUTH_CODE
                except Exception as e2:
                    logger.error(f"Failed to send message via alternative method: {e2}")
                    raise e
                    
        except Exception as e:
            logger.error(f"Error in connect_drive_command: {e}", exc_info=True)
            error_message = "❌ Sorry, I couldn't start the Google Drive connection process. Please try again later."
            try:
                if update.callback_query:
                    await update.callback_query.message.reply_text(error_message)
                elif update.message:
                    await update.message.reply_text(error_message)
                elif update.effective_chat:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=error_message
                    )
            except Exception as e2:
                logger.error(f"Failed to send error message: {e2}")
            
            return ConversationHandler.END
    
    async def process_auth_code(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process the authorization code sent by the user and create a folder."""
        user = update.effective_user
        telegram_id = str(user.id)
        auth_code = update.message.text.strip()
        
        logger.info(f"Received auth code from user {telegram_id}. Processing...")
        
        # Delete the message containing the auth code for security
        try:
            await update.message.delete()
        except Exception as e:
            logger.warning(f"Could not delete message with auth code: {e}")
        
        try:
            # Exchange the code for tokens
            logger.info(f"Exchanging auth code for tokens for user {telegram_id}")
            token_info = self.drive_manager.exchange_code_for_tokens(auth_code)
            logger.info(f"Successfully obtained tokens for user {telegram_id}")
            
            # Store the tokens in the database
            token_json = json.dumps(token_info)
            self.db.update_user_drive_token(telegram_id, token_json)
            logger.info(f"Saved tokens to database for user {telegram_id}")
            
            # Send initial success message
            await update.message.reply_text(
                "✅ *Google Drive Connected Successfully!*\n\n"
                "Your Google Drive account is now connected to BetterSaved.\n"
                "Creating your BetterSaved folder...",
                parse_mode='Markdown'
            )
            
            # Create the BetterSaved folder with spreadsheet and subfolders
            logger.info(f"Creating BetterSaved folder for user {telegram_id}")
            try:
                result = self.drive_manager.create_folder(token_info)
                logger.info(f"Folder creation result: {result}")
                
                if result['success']:
                    folder_id = result['folder_id']
                    folder_url = result['folder_url']
                    logger.info(f"Folder created successfully with ID: {folder_id}")
                    
                    # Store folder information in the database
                    folder_update_result = self.db.update_drive_folder_info(telegram_id, folder_id, folder_url)
                    logger.info(f"Stored folder info in database for user {telegram_id}, result: {folder_update_result}")
                    
                    # Verify folder info was stored
                    drive_info_after_folder = self.db.get_user_drive_info(telegram_id)
                    logger.info(f"Drive info after folder update: {drive_info_after_folder}")
                    
                    # Check if spreadsheet was created and store in database
                    spreadsheet_info = ""
                    if result.get('spreadsheet', {}).get('success', False):
                        spreadsheet_id = result['spreadsheet'].get('spreadsheet_id', '')
                        spreadsheet_url = result['spreadsheet'].get('spreadsheet_url', '')
                        
                        logger.info(f"Spreadsheet info from Drive API: id={spreadsheet_id}, url={spreadsheet_url}")
                        
                        if spreadsheet_id and spreadsheet_url:
                            # Store spreadsheet information in the database
                            spreadsheet_update_result = self.db.update_drive_spreadsheet_info(telegram_id, spreadsheet_id, spreadsheet_url)
                            logger.info(f"Stored spreadsheet info in database for user {telegram_id}, result: {spreadsheet_update_result}")
                            
                            # Verify the data was stored correctly
                            drive_info_after_spreadsheet = self.db.get_user_drive_info(telegram_id)
                            logger.info(f"Drive info after spreadsheet update: {drive_info_after_spreadsheet}")
                            
                            spreadsheet_info = f"\n\n📃 *Spreadsheet*: [BetterSavedMessages]({spreadsheet_url})"
                    
                    await update.message.reply_text(
                        "✅ *BetterSaved Setup Complete!*\n\n"
                        f"📁 *Main Folder*: [BetterSaved]({folder_url})\n"
                        "The following items have been created:\n"
                        "- A spreadsheet to log your saved messages\n"
                        "- Subfolders for different content types (Images, Video, Audio, PDF, Tickets)"
                        f"{spreadsheet_info}",
                        parse_mode='Markdown',
                        disable_web_page_preview=True
                    )
                else:
                    error_msg = result.get('error', 'Unknown error')
                    logger.warning(f"Failed to create folder for user {telegram_id}: {error_msg}")
                    await update.message.reply_text(
                        "⚠️ Your Google Drive was connected successfully, but I couldn't create the BetterSaved folder. "
                        "You may need to create it manually or try reconnecting later."
                    )
            except Exception as folder_error:
                logger.error(f"Exception during folder creation: {str(folder_error)}")
                await update.message.reply_text(
                    "⚠️ Your Google Drive was connected successfully, but I couldn't create the BetterSaved folder due to an error. "
                    "You may need to create it manually."
                )
            
        except Exception as e:
            logger.error(f"Error processing auth code for user {telegram_id}: {e}")
            logger.error(f"Exception details: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            await update.message.reply_text(
                "❌ Sorry, I couldn't connect to your Google Drive. "
                "The authorization code might be invalid or expired. "
                "Please try again with /connect_drive."
            )
        
        return ConversationHandler.END
    
    async def cancel_auth(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel the Google Drive connection process."""
        await update.message.reply_text(
            "🛑 Google Drive connection process canceled. "
            "You can start again anytime with /connect_drive."
        )
        return ConversationHandler.END
    

    
    async def disconnect_drive_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Disconnect Google Drive from the user's account."""
        user = update.effective_user
        telegram_id = str(user.id)
        
        # Check if user has a token
        token_json = self.db.get_user_drive_token(telegram_id)
        if not token_json:
            await update.message.reply_text(
                "❌ You don't have a Google Drive connection to disconnect."
            )
            return
            
        # Clear the token
        success = self.db.update_user_drive_token(telegram_id, None)
        
        if success:
            await update.message.reply_text(
                "✅ Your Google Drive connection has been removed. Your saved messages will no longer be stored in Google Drive."
                "You can reconnect anytime using /connect_drive."
            )
        else:
            await update.message.reply_text(
                "❌ Failed to disconnect your Google Drive. Please try again later."
            )
            
    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel the current conversation."""
        await update.message.reply_text(
            "Operation cancelled. What would you like to do next?"
        )
        return ConversationHandler.END
        
    async def nuke_user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start the process of deleting a user's account data."""
        user = update.effective_user
        telegram_id = str(user.id)
        
        # Check if user exists in database
        user_data = self.db.debug_view_user(telegram_id)
        if not user_data:
            await update.message.reply_text(
                "❌ You don't have an account to delete."
            )
            return ConversationHandler.END
        
        # Send warning message
        warning_message = (
            "⚠️ <b>DANGER ZONE - ACCOUNT DELETION</b> ⚠️\n\n"
            "You are about to delete your account and all associated data from BetterSaved.\n\n"
            "<b>This action cannot be undone!</b>\n\n"
            "• All your settings will be deleted\n"
            "• Your Google Drive connection will be removed\n"
            "• Your saved preferences will be lost\n\n"
            "<i>Note: This will NOT delete any files already saved to your Google Drive.</i>\n\n"
            "To confirm deletion, reply with the word 'CONFIRM' (all caps).\n"
            "To cancel, reply with anything else or use the /cancel command."
        )
        
        await update.message.reply_text(warning_message, parse_mode='HTML')
        return self.WAITING_FOR_NUKE_CONFIRMATION
    
    async def process_nuke_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process the confirmation for account deletion."""
        user = update.effective_user
        telegram_id = str(user.id)
        message_text = update.message.text.strip()
        
        # Check if the confirmation is correct
        if message_text == "CONFIRM":
            # Delete the user from the database
            success = self.db.delete_user(telegram_id)
            
            if success:
                await update.message.reply_text(
                    "💥 Your account has been deleted. All your data has been removed from our database.\n\n"
                    "If you wish to use BetterSaved again in the future, just send /start to get started.",
                    parse_mode='HTML'
                )
                logger.info(f"User {telegram_id} has deleted their account")
            else:
                await update.message.reply_text(
                    "❌ Something went wrong while trying to delete your account. Please try again later or contact support."
                )
                logger.error(f"Failed to delete user {telegram_id}")
        else:
            # Incorrect confirmation
            await update.message.reply_text(
                "Account deletion cancelled. Your data remains intact."
            )
            logger.info(f"User {telegram_id} cancelled account deletion")
        
        return ConversationHandler.END
        
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button clicks from inline keyboards."""
        query = update.callback_query
        user = query.from_user
        telegram_id = str(user.id)
        callback_data = query.data
        
        # Log the button click
        logger.info(f"User {telegram_id} clicked button: {callback_data}")
        
        # Always answer the callback query first to avoid the "loading" state
        await query.answer()
        
        if callback_data == "connect_drive":
            # Let the conversation handler handle this by calling connect_drive_command
            # with the callback query instead of a command
            try:
                return await self.connect_drive_command(update, context)
            except Exception as e:
                logger.error(f"Error in connect_drive button: {e}")
                await query.message.reply_text(
                    "❌ Sorry, I couldn't start the Google Drive connection process. "
                    "Please try again later or use the /connect_drive command."
                )
                return
            
        elif callback_data == "settings":
            # Create settings menu with buttons
            try:
                keyboard = [
                    [InlineKeyboardButton("🔗 Connect Drive", callback_data="connect_drive"),
                     InlineKeyboardButton("🔌 Disconnect Drive", callback_data="disconnect_drive")],
                    [InlineKeyboardButton("📝 User Info", callback_data="user_info"),
                     InlineKeyboardButton("💾 Fix Spreadsheet", callback_data="fix_spreadsheet")],
                    [InlineKeyboardButton("⚙️ Advanced Settings", callback_data="advanced_settings")],
                    [InlineKeyboardButton("💥 Delete Account", callback_data="nuke_user")],
                    [InlineKeyboardButton("⬅️ Back", callback_data="back_to_main")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Try to edit the message, if it fails, send a new one
                try:
                    await query.edit_message_text(
                        text="⚙️ <b>Settings</b>\n\nSelect an option from the menu below:",
                        parse_mode='HTML',
                        reply_markup=reply_markup
                    )
                except Exception as e:
                    logger.error(f"Error editing message for settings: {e}")
                    # If editing fails, send a new message
                    await query.message.reply_text(
                        text="⚙️ <b>Settings</b>\n\nSelect an option from the menu below:",
                        parse_mode='HTML',
                        reply_markup=reply_markup
                    )
            except Exception as e:
                logger.error(f"Error in settings button: {e}")
                await query.message.reply_text(
                    "❌ Something went wrong with the settings menu. Please try again."
                )
            
        elif callback_data == "about":
            try:
                # About message with information about the bot
                about_text = (
                    "ℹ️ <b>About BetterSaved Bot</b>\n\n"
                    "BetterSaved is a Telegram bot that enhances your Saved Messages experience by automatically "
                    "saving your messages, photos, videos, documents and other files to your Google Drive.\n\n"
                    "This bot serves as a proof of concept for a way to give the control over your notes and "
                    "messenger-based storage back to you, without sacrificing the usability of a 'dump chat' "
                    "in your messenger of choice.\n\n"
                    "<b>Developer:</b> @dmitry_helios\n"
                    "<b>Version:</b> 0.1.0\n\n"
                    "<b>Planned Features in Near Future:</b>\n"
                    "• AI Message Categorization\n"
                    "• Support for various storage providers (OneDrive, Local storage etc.)\n"
                    "• AI message search and retrieval\n\n"
                    "<b>Features down the pipeline:</b>\n"
                    "• WhatsApp, IG, FB messenger bots with united storage\n"
                    "• Self-hosted LLM support\n"
                    "• Dedicated WebUI for note management\n"
                    "• Integration with password management apps\n"
                    "• And more!\n\n"
                    "Please contact me if you have any suggestions or feedback, or would like to beta-test the bot's Google Drive integration."
                )
                
                keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="back_to_main")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Try to edit the message, if it fails, send a new one
                try:
                    await query.edit_message_text(
                        text=about_text,
                        parse_mode='HTML',
                        reply_markup=reply_markup
                    )
                except Exception as e:
                    logger.error(f"Error editing message for about: {e}")
                    # If editing fails, send a new message
                    await query.message.reply_text(
                        text=about_text,
                        parse_mode='HTML',
                        reply_markup=reply_markup
                    )
            except Exception as e:
                logger.error(f"Error in about button: {e}")
                await query.message.reply_text(
                    "❌ Something went wrong with the about information. Please try again."
                )
            
        elif callback_data == "donate":
            try:
                # Donate message (placeholder for now)
                donate_text = (
                    "☕ <b>Buy Me a Coffee</b>\n\n"
                    "Thank you for considering supporting the development of BetterSaved!\n\n"
                    "<a href='https://ko-fi.com/helios_xii'>Send a donation through Ko-Fi</a>\n"
                    "USDT TRC-20:\n"
                    "TNcKWRoVpyMN6MzXdQaM6E2sebM9iSMzdi\n"
                    "Bybit UID: 70333452\n"
                    "Your support helps keep the bot running and enables new features."
                )
                
                keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="back_to_main")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Try to edit the message, if it fails, send a new one
                try:
                    await query.edit_message_text(
                        text=donate_text,
                        parse_mode='HTML',
                        reply_markup=reply_markup
                    )
                except Exception as e:
                    logger.error(f"Error editing message for donate: {e}")
                    # If editing fails, send a new message
                    await query.message.reply_text(
                        text=donate_text,
                        parse_mode='HTML',
                        reply_markup=reply_markup
                    )
            except Exception as e:
                logger.error(f"Error in donate button: {e}")
                await query.message.reply_text(
                    "❌ Something went wrong with the donation information. Please try again."
                )
            
        elif callback_data == "back_to_main":
            try:
                # Return to the main menu
                welcome_caption = (
                    "<b>Hi! I am the Better Saved Messages bot.</b>\n\n"
                    "You can use me as your regular Saved Messages chat, but I can do more!\n\n"
                    "Log in to your Google Drive account and I will keep a detailed log of all your messages, "
                    "as well as download and save all your attachments to a folder on your Google Drive."
                )
                
                keyboard = [
                    [InlineKeyboardButton("🔗 Connect Google Drive", callback_data="connect_drive")],
                    [InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
                    [InlineKeyboardButton("ℹ️ About This Bot", callback_data="about"), 
                     InlineKeyboardButton("☕ Buy me a coffee", callback_data="donate")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Try to edit the message, if it fails, send a new one
                try:
                    await query.edit_message_text(
                        text=welcome_caption,
                        parse_mode='HTML',
                        reply_markup=reply_markup
                    )
                except Exception as e:
                    logger.error(f"Error editing message for back_to_main: {e}")
                    # If editing fails, send a new message
                    await query.message.reply_text(
                        text=welcome_caption,
                        parse_mode='HTML',
                        reply_markup=reply_markup
                    )
            except Exception as e:
                logger.error(f"Error in back_to_main button: {e}")
                await query.message.reply_text(
                    "❌ Something went wrong returning to the main menu. Please try again or use /start."
                )
            
        elif callback_data == "disconnect_drive":
            # Handle disconnect drive button
            telegram_id = str(user.id)
            
            # Check if user has a token
            token_json = self.db.get_user_drive_token(telegram_id)
            if not token_json:
                await query.message.reply_text(
                    "❌ You don't have a Google Drive connection to disconnect."
                )
                return
                
            # Clear the token
            success = self.db.update_user_drive_token(telegram_id, None)
            
            if success:
                await query.message.reply_text(
                    "✅ Your Google Drive connection has been removed. Your saved messages will no longer be stored in Google Drive.\n\n"
                    "You can reconnect anytime using the Connect Drive button or /connect_drive command."
                )
            else:
                await query.message.reply_text(
                    "❌ Failed to disconnect your Google Drive. Please try again later."
                )
            
        elif callback_data == "user_info":
            # Show user information
            user_data = self.db.debug_view_user(telegram_id)
            
            if user_data:
                # Format the user data for display
                has_drive = "Yes" if user_data.get('key_gdrive') else "No"
                has_folder = "Yes" if user_data.get('folder_id') else "No"
                has_spreadsheet = "Yes" if user_data.get('spreadsheet_id') else "No"
                
                user_info = (
                    "📝 <b>User Information</b>\n\n"
                    f"<b>Name:</b> {user_data.get('name', 'Not set')}\n"
                    f"<b>Telegram ID:</b> {telegram_id}\n"
                    f"<b>Google Drive Connected:</b> {has_drive}\n"
                    f"<b>BetterSaved Folder Created:</b> {has_folder}\n"
                    f"<b>Messages Spreadsheet Created:</b> {has_spreadsheet}\n"
                )
            else:
                user_info = "❌ No user data found. Please use /start to register."
            
            keyboard = [[InlineKeyboardButton("⬅️ Back to Settings", callback_data="settings")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                text=user_info,
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            
        elif callback_data == "fix_spreadsheet":
            # Handle fix spreadsheet button
            telegram_id = str(user.id)
            
            # Get user data for debugging
            user_data = self.db.debug_view_user(telegram_id)
            logger.info(f"User data before fix: {user_data}")
            
            # Get token
            token_json = self.db.get_user_drive_token(telegram_id)
            if not token_json:
                await query.message.reply_text(
                    "❌ You need to connect your Google Drive first. Use the Connect Drive button or /connect_drive command to get started."
                )
                return
                
            # Show working message
            working_message = await query.message.reply_text(
                "🔄 Working on fixing your spreadsheet... This may take a moment."
            )
            
            try:
                # Parse token
                token_info = json.loads(token_json)
                
                # Get folder ID
                folder_id = self.db.get_user_folder_id(telegram_id)
                if not folder_id:
                    # Create folder if it doesn't exist
                    folder_result = self.drive_manager.create_better_saved_folder(token_info)
                    folder_id = folder_result.get('id')
                    folder_url = folder_result.get('webViewLink')
                    
                    # Save folder info to database
                    self.db.update_user_folder_info(telegram_id, folder_id, folder_url)
                    logger.info(f"Created new folder for user {telegram_id}: {folder_id}")
                
                # Create spreadsheet in the folder
                spreadsheet_result = self.drive_manager.create_spreadsheet(token_info, folder_id)
                spreadsheet_id = spreadsheet_result.get('id')
                spreadsheet_url = spreadsheet_result.get('webViewLink')
                
                # Save spreadsheet info to database
                self.db.update_user_spreadsheet_info(telegram_id, spreadsheet_id, spreadsheet_url)
                
                # Success message
                await working_message.edit_text(
                    f"✅ Spreadsheet fixed successfully! Your messages will now be saved to your Google Drive.\n\n"
                    f"<a href='{spreadsheet_url}'>View your messages spreadsheet</a>",
                    parse_mode='HTML'
                )
                
                logger.info(f"Fixed spreadsheet for user {telegram_id}: {spreadsheet_id}")
                
            except Exception as e:
                # Error message
                await working_message.edit_text(
                    "❌ Failed to fix your spreadsheet. Please try again later or contact support."
                )
                logger.error(f"Error fixing spreadsheet: {e}")
                logger.error(traceback.format_exc())
            
        elif callback_data == "nuke_user":
            # Show warning before redirecting to nuke_user_command
            warning_message = (
                "⚠️ <b>WARNING: Account Deletion</b>\n\n"
                "You are about to delete your account and all associated data.\n"
                "This action cannot be undone!\n\n"
                "To proceed, use the /nuke_user command and follow the instructions."
            )
            
            keyboard = [[InlineKeyboardButton("⬅️ Back to Settings", callback_data="settings")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                text=warning_message,
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            
        elif callback_data == "advanced_settings":
            # Placeholder for advanced settings
            advanced_text = (
                "⚙️ <b>Advanced Settings</b>\n\n"
                "Advanced settings will be available in future updates.\n\n"
                "Stay tuned for more features!"
            )
            
            keyboard = [[InlineKeyboardButton("⬅️ Back to Settings", callback_data="settings")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                text=advanced_text,
                parse_mode='HTML',
                reply_markup=reply_markup
            )
    
    async def fix_spreadsheet_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Fix spreadsheet information in the database."""
        user = update.effective_user
        telegram_id = str(user.id)
        
        # Get user data for debugging
        user_data = self.db.debug_view_user(telegram_id)
        logger.info(f"User data before fix: {user_data}")
        
        # Get token
        token_json = self.db.get_user_drive_token(telegram_id)
        if not token_json:
            # Check if we've already shown the connect message to this user
            if not self.db.check_connect_msg_shown(telegram_id):
                # First time showing the message - send it and mark as shown
                await update.message.reply_text(
                    "❌ <b>You need to connect your Google Drive first.</b> Use /connect_drive to get started.",
                    parse_mode='HTML'
                )
                self.db.mark_connect_msg_shown(telegram_id)
            return
            
        # Show working message
        status_message = await update.message.reply_text("🔄 Fixing your spreadsheet information...")
        
        try:
            # Parse token
            token_info = json.loads(token_json)
            
            # Get folder ID
            folder_id = user_data.get('folder_id', '')
            if not folder_id:
                await status_message.edit_text(
                    "❌ No folder information found. Please reconnect your Google Drive with /connect_drive."
                )
                return
                
            # Create credentials
            credentials = self.drive_manager.create_credentials_from_token_info(token_info)
            
            # Search for existing spreadsheet
            drive_service = build('drive', 'v3', credentials=credentials)
            results = drive_service.files().list(
                q=f"name='BetterSavedMessages' and mimeType='application/vnd.google-apps.spreadsheet' and '{folder_id}' in parents and trashed=false",
                spaces='drive',
                fields='files(id, name)'
            ).execute()
            
            items = results.get('files', [])
            
            if items:
                # Found existing spreadsheet
                spreadsheet_id = items[0]['id']
                spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
                
                # Update database
                self.db.update_drive_spreadsheet_info(telegram_id, spreadsheet_id, spreadsheet_url)
                
                # Verify update
                updated_data = self.db.debug_view_user(telegram_id)
                logger.info(f"User data after fix (existing spreadsheet): {updated_data}")
                
                await status_message.edit_text(
                    "✅ Found existing spreadsheet and fixed database information. You can now save messages!"
                )
            else:
                # Create new spreadsheet
                spreadsheet_result = self.drive_manager.create_spreadsheet(credentials, folder_id)
                
                if spreadsheet_result.get('success'):
                    spreadsheet_id = spreadsheet_result.get('spreadsheet_id', '')
                    spreadsheet_url = spreadsheet_result.get('spreadsheet_url', '')
                    
                    # Update database
                    self.db.update_drive_spreadsheet_info(telegram_id, spreadsheet_id, spreadsheet_url)
                    
                    # Verify update
                    updated_data = self.db.debug_view_user(telegram_id)
                    logger.info(f"User data after fix (new spreadsheet): {updated_data}")
                    
                    await status_message.edit_text(
                        "✅ Created new spreadsheet and fixed database information. You can now save messages!"
                    )
                else:
                    error = spreadsheet_result.get('error', 'Unknown error')
                    logger.error(f"Error creating spreadsheet: {error}")
                    await status_message.edit_text(
                        "❌ Failed to create spreadsheet. Please try reconnecting with /connect_drive."
                    )
        except Exception as e:
            logger.error(f"Error fixing spreadsheet: {e}")
            logger.error(traceback.format_exc())
            await status_message.edit_text(
                "❌ An error occurred while fixing your spreadsheet information. Please try again later."
            )
    
    async def _handle_photo_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photo messages by uploading to Google Drive and logging to spreadsheet.
        
        Args:
            update: The update containing the photo message
            context: The context object
        """
        user = update.effective_user
        telegram_id = str(user.id)
        message = update.message
        
        # Get user data
        user_data = self.db.debug_view_user(telegram_id)
        logger.info(f"Processing photo from user: {user_data}")
        
        # Get user's Drive token and spreadsheet info
        token_json = self.db.get_user_drive_token(telegram_id)
        drive_info = self.db.get_user_drive_info(telegram_id)
        
        # Check if user has connected Google Drive
        if not token_json:
            logger.info(f"User {telegram_id} has no Google Drive token")
            await message.reply_text(
                "You need to connect your Google Drive account first. "
                "Use /connect_drive to get started."
            )
            return
        
        # Check if user has a spreadsheet
        if not drive_info or not drive_info.get('spreadsheet_id') or not drive_info.get('folder_id'):
            logger.error(f"User {telegram_id} missing drive info: {drive_info}")
            await message.reply_text(
                "You don't have a BetterSaved spreadsheet or folder set up. "
                "Please use /fix_spreadsheet to repair your setup."
            )
            return
        
        # Create a saving message for this photo
        # For media groups, we'll handle each photo independently but with a shared caption
        is_media_group = message.media_group_id is not None
        media_group_id = message.media_group_id
        
        # Log media group information
        if is_media_group:
            logger.info(f"Media group detected: {media_group_id}")
            # Initialize shared media group info if needed
            if 'media_groups' not in context.bot_data:
                context.bot_data['media_groups'] = {}
            
            # Store or retrieve the shared caption for this group
            if media_group_id not in context.bot_data['media_groups']:
                # First photo in this group - store the caption
                context.bot_data['media_groups'][media_group_id] = {
                    'caption': message.caption if message.caption else "<Image>",
                    'count': 1,
                    'processed': 0,
                    'finalized': False,
                    'photos_processed': set()  # Track which photos we've processed by file_id
                }
                logger.info(f"First photo in group {media_group_id}, caption: {context.bot_data['media_groups'][media_group_id]['caption']}")
                # Create a group progress message
                group_message = await message.reply_text("💾 Processing your photos...")
                context.bot_data['media_groups'][media_group_id]['message'] = group_message
            else:
                # Not the first photo - increment the count
                context.bot_data['media_groups'][media_group_id]['count'] += 1
                logger.info(f"Additional photo in group {media_group_id}, count: {context.bot_data['media_groups'][media_group_id]['count']}")
        else:
            # Single photo
            logger.info("Single photo (not in media group)")
        
        # Each photo gets its own saving indicator, but we'll hide it for media groups
        if is_media_group:
            # Use the group message for updates
            saving_message = context.bot_data['media_groups'][media_group_id]['message']
        else:
            # Single photo gets its own message
            saving_message = await message.reply_text("💾 Saving your photo...")
        
        try:
            # Parse token JSON
            token_info = json.loads(token_json)
            folder_id = drive_info.get('folder_id')
            spreadsheet_id = drive_info.get('spreadsheet_id')
            
            # Get the largest photo (best quality)
            photo = message.photo[-1]  # The last photo is the largest one
            
            # For media groups, check if we've already processed this photo
            if is_media_group:
                if photo.file_id in context.bot_data['media_groups'][media_group_id]['photos_processed']:
                    logger.info(f"Skipping already processed photo {photo.file_id} in group {media_group_id}")
                    return
                else:
                    # Mark this photo as being processed
                    context.bot_data['media_groups'][media_group_id]['photos_processed'].add(photo.file_id)
                    logger.info(f"Processing new photo {photo.file_id} in group {media_group_id}")
            
            # Get photo file
            photo_file = await context.bot.get_file(photo.file_id)
            
            # Generate a unique filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"photo_{timestamp}_{photo.file_unique_id}.jpg"
            
            # Download the photo to memory
            from io import BytesIO
            photo_data = BytesIO()
            await photo_file.download_to_memory(photo_data)
            photo_data.seek(0)  # Reset file pointer to beginning
            
            # Upload photo to Google Drive
            upload_result = self.drive_manager.upload_photo_to_drive(
                token_info, 
                folder_id, 
                photo_data, 
                file_name
            )
            
            if not upload_result.get('success'):
                error = upload_result.get('error', 'Unknown error')
                logger.error(f"Failed to upload photo: {error}")
                
                if is_media_group:
                    context.bot_data['media_groups'][media_group_id]['failed_count'] += 1
                else:
                    await saving_message.edit_text(
                        "❌ Failed to save your photo. Please try again later."
                    )
                return
            
            # Get the file URL from the upload result
            file_url = upload_result.get('file_url', '')
            
            # Get caption - for media groups, use the shared caption
            if is_media_group:
                content = context.bot_data['media_groups'][media_group_id]['caption']
                logger.info(f"Using shared caption for media group {media_group_id}: {content}")
            else:
                content = message.caption if message.caption else "<Image>"
            
            # Prepare message metadata for spreadsheet
            message_metadata = {
                'text': content,
                'is_forwarded': message.forward_date is not None,
                'forward_date': message.forward_date.isoformat() if message.forward_date else None,
                'forward_from': None,
                'forward_from_chat': None,
                'category': 'Image',
                'link': file_url
            }
            
            # Add forwarding information if available
            if message.forward_from:
                message_metadata['forward_from'] = message.forward_from.full_name or message.forward_from.first_name
            elif message.forward_from_chat:
                message_metadata['forward_from_chat'] = message.forward_from_chat.title or message.forward_from_chat.username
            
            # Save to Google Sheets
            sheet_result = self.drive_manager.save_message_to_sheet(token_info, spreadsheet_id, message_metadata)
            
            if sheet_result['success']:
                logger.info(f"Successfully saved photo to spreadsheet: {file_url}")
                
                if is_media_group:
                    # Update processed count for the group
                    context.bot_data['media_groups'][media_group_id]['processed'] += 1
                    processed = context.bot_data['media_groups'][media_group_id]['processed']
                    count = context.bot_data['media_groups'][media_group_id]['count']
                    
                    # Update the group message
                    await saving_message.edit_text(f"💾 Saved {processed} photo(s)...")
                    
                    # If we've processed all photos we know about, finalize after a delay
                    # to catch any stragglers, but only if we haven't already scheduled finalization
                    if processed >= count and not context.bot_data['media_groups'][media_group_id].get('finalized', False):
                        logger.info(f"All known photos in group {media_group_id} processed, scheduling finalization")
                        # Mark as finalized to prevent multiple finalizations
                        context.bot_data['media_groups'][media_group_id]['finalized'] = True
                        # Wait 5 seconds before finalizing to catch any late arrivals
                        asyncio.create_task(self._finalize_media_group(context, media_group_id, saving_message, 5))
                else:
                    # Single photo success message
                    await saving_message.edit_text(
                        f"✅ Photo saved to your Google Drive and logged in your spreadsheet!\n\n"
                        f"Caption: {content}\n\n"
                        f"This message will disappear in a few seconds."
                    )
                    
                    # Schedule message deletion after 5 seconds (non-blocking)
                    asyncio.create_task(self._delete_message_after_delay(saving_message, 5))
            else:
                error = sheet_result.get('error', 'Unknown error')
                logger.error(f"Failed to log photo to spreadsheet: {error}")
                
                if is_media_group:
                    # Update the group message to show an error occurred
                    await saving_message.edit_text(
                        f"⚠️ Error saving one of your photos. Please try again later."
                    )
                else:
                    await saving_message.edit_text(
                        f"⚠️ Photo was saved to Google Drive but failed to log in spreadsheet.\n"
                        f"URL: {file_url}"
                    )
        except Exception as e:
            logger.error(f"Error processing photo for user {telegram_id}: {e}")
            logger.error(traceback.format_exc())
            
            if not is_media_group:
                await saving_message.edit_text(
                    "❌ An error occurred while saving your photo. Please try again later."
                )
    
    async def _finalize_media_group(self, context, media_group_id, saving_message, wait_seconds):
        """Finalize a media group after all photos have been processed.
        
        Args:
            context: The context object
            media_group_id: The ID of the media group
            saving_message: The message to update with the final status
            wait_seconds: Number of seconds to wait before finalizing
        """
        try:
            # Wait for a few seconds to make sure all photos have been processed
            # This gives time for any remaining photos to be processed
            await asyncio.sleep(wait_seconds)
            
            # Check if the media group exists in the context
            if 'media_groups' not in context.bot_data or media_group_id not in context.bot_data['media_groups']:
                logger.info(f"Media group {media_group_id} not found in context during finalization")
                return
            
            # Get the media group data
            group_data = context.bot_data['media_groups'][media_group_id]
            processed = group_data['processed']
            photo_count = len(group_data['photos_processed'])
            
            logger.info(f"Finalizing media group {media_group_id} with {processed} photos processed, {photo_count} unique photos")
            
            # Double check that we're not finalizing too early
            if processed < group_data['count']:
                logger.warning(f"Finalizing media group {media_group_id} early: processed {processed}, expected {group_data['count']}")
            
            # Show success message with the actual number of unique photos processed
            await saving_message.edit_text(
                f"✅ All {photo_count} photos saved to your Google Drive and logged in your spreadsheet!\n\n"
                "This message will disappear in a few seconds."
            )
            
            # Schedule message deletion after 5 seconds
            asyncio.create_task(self._delete_message_after_delay(saving_message, 5))
            
            try:
                # Clean up the media group data
                if media_group_id in context.bot_data['media_groups']:
                    del context.bot_data['media_groups'][media_group_id]
                    logger.info(f"Media group {media_group_id} finalized and data cleaned up")
            except Exception as cleanup_error:
                logger.error(f"Error cleaning up media group data: {cleanup_error}")
            
        except Exception as e:
            logger.error(f"Error finalizing media group: {e}")
            logger.error(traceback.format_exc())
    
    async def _handle_file_upload(self, update: Update, context: ContextTypes.DEFAULT_TYPE, file_type: str, mime_type: str, file_obj, file_name: str, category_name: str):
        """Generic handler for uploading files to Google Drive and logging to spreadsheet.
        
        Args:
            update: The update containing the message
            context: The context object
            file_type: Type of file for Google Drive folder ('image', 'video', 'audio', 'pdf', 'misc')
            mime_type: MIME type of the file
            file_obj: File object to upload
            file_name: Name to give the file in Google Drive
            category_name: Category name for spreadsheet logging
        """
        user = update.effective_user
        telegram_id = str(user.id)
        message = update.message
        
        # Create a saving message
        saving_message = await message.reply_text(f"💾 Saving your {category_name.lower()}...")
        
        try:
            # Parse token JSON
            token_json = self.db.get_user_drive_token(telegram_id)
            drive_info = self.db.get_user_drive_info(telegram_id)
            token_info = json.loads(token_json)
            folder_id = drive_info.get('folder_id')
            spreadsheet_id = drive_info.get('spreadsheet_id')
            
            # Upload file to Google Drive
            upload_result = self.drive_manager.upload_file_to_drive(
                token_info, 
                folder_id, 
                file_obj, 
                file_name,
                file_type,
                mime_type
            )
            
            if not upload_result.get('success'):
                error = upload_result.get('error', 'Unknown error')
                logger.error(f"Failed to upload {file_type}: {error}")
                await saving_message.edit_text(f"❌ Failed to save your {category_name.lower()}. Please try again later.")
                return
            
            # Get the file URL from the upload result
            file_url = upload_result.get('file_url', '')
            
            # Get caption or use placeholder
            content = message.caption if message.caption else f"<{category_name}>"
            
            # Prepare message metadata for spreadsheet
            message_metadata = {
                'text': content,
                'is_forwarded': message.forward_date is not None,
                'forward_date': message.forward_date.isoformat() if message.forward_date else None,
                'forward_from': None,
                'forward_from_chat': None,
                'category': category_name,
                'link': file_url
            }
            
            # Add forwarding information if available
            if message.forward_from:
                message_metadata['forward_from'] = message.forward_from.full_name or message.forward_from.first_name
            elif message.forward_from_chat:
                message_metadata['forward_from_chat'] = message.forward_from_chat.title or message.forward_from_chat.username
            
            # Save to Google Sheets
            sheet_result = self.drive_manager.save_message_to_sheet(token_info, spreadsheet_id, message_metadata)
            
            if sheet_result['success']:
                logger.info(f"Successfully saved {file_type} to spreadsheet: {file_url}")
                
                # Success message
                await saving_message.edit_text(
                    f"✅ {category_name} saved to your Google Drive and logged in your spreadsheet!\n\n"
                    f"Caption: {content}\n\n"
                    f"This message will disappear in a few seconds."
                )
                
                # Schedule message deletion after 5 seconds (non-blocking)
                asyncio.create_task(self._delete_message_after_delay(saving_message, 5))
            else:
                error = sheet_result.get('error', 'Unknown error')
                logger.error(f"Failed to log {file_type} to spreadsheet: {error}")
                
                await saving_message.edit_text(
                    f"⚠️ {category_name} was saved to Google Drive but failed to log in spreadsheet.\n"
                    f"URL: {file_url}"
                )
        except Exception as e:
            logger.error(f"Error processing {file_type} for user {telegram_id}: {e}")
            logger.error(traceback.format_exc())
            
            await saving_message.edit_text(
                f"❌ An error occurred while saving your {category_name.lower()}. Please try again later."
            )
    
    async def _handle_image_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle image documents by uploading to Google Drive and logging to spreadsheet.
        
        Args:
            update: The update containing the document message
            context: The context object
        """
        message = update.message
        document = message.document
        
        # Log document details
        logger.info(f"Processing image document: {document.file_name}, {document.mime_type}")
        
        # Get document file
        document_file = await context.bot.get_file(document.file_id)
        
        # Generate a unique filename or use the original
        file_name = document.file_name
        if not file_name:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_extension = ".jpg" if document.mime_type == "image/jpeg" else ".png"
            file_name = f"image_{timestamp}_{document.file_unique_id}{file_extension}"
        
        # Download the document to memory
        from io import BytesIO
        document_data = BytesIO()
        await document_file.download_to_memory(document_data)
        document_data.seek(0)  # Reset file pointer to beginning
        
        # Use the generic file upload handler
        await self._handle_file_upload(
            update, 
            context, 
            'image', 
            document.mime_type, 
            document_data, 
            file_name, 
            'Image Document'
        )
        
    async def _handle_pdf_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle PDF documents by uploading to Google Drive and logging to spreadsheet.
        
        Args:
            update: The update containing the document message
            context: The context object
        """
        message = update.message
        document = message.document
        
        # Log document details
        logger.info(f"Processing PDF document: {document.file_name}")
        
        # Get document file
        document_file = await context.bot.get_file(document.file_id)
        
        # Generate a unique filename or use the original
        file_name = document.file_name
        if not file_name:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"document_{timestamp}_{document.file_unique_id}.pdf"
        
        # Download the document to memory
        from io import BytesIO
        document_data = BytesIO()
        await document_file.download_to_memory(document_data)
        document_data.seek(0)  # Reset file pointer to beginning
        
        # Use the generic file upload handler
        await self._handle_file_upload(
            update, 
            context, 
            'pdf', 
            'application/pdf', 
            document_data, 
            file_name, 
            'PDF Document'
        )
        
    async def _handle_audio_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle audio documents by uploading to Google Drive and logging to spreadsheet.
        
        Args:
            update: The update containing the document message
            context: The context object
        """
        message = update.message
        document = message.document
        
        # Log document details
        logger.info(f"Processing audio document: {document.file_name}, {document.mime_type}")
        
        # Get document file
        document_file = await context.bot.get_file(document.file_id)
        
        # Generate a unique filename or use the original
        file_name = document.file_name
        if not file_name:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_extension = ".ogg" if document.mime_type == "application/ogg" else ".mp3"
            file_name = f"audio_{timestamp}_{document.file_unique_id}{file_extension}"
        
        # Download the document to memory
        from io import BytesIO
        document_data = BytesIO()
        await document_file.download_to_memory(document_data)
        document_data.seek(0)  # Reset file pointer to beginning
        
        # Use the generic file upload handler
        await self._handle_file_upload(
            update, 
            context, 
            'audio', 
            document.mime_type, 
            document_data, 
            file_name, 
            'Audio Document'
        )
        
    async def _handle_video_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle video documents by uploading to Google Drive and logging to spreadsheet.
        
        Args:
            update: The update containing the document message
            context: The context object
        """
        message = update.message
        document = message.document
        
        # Log document details
        logger.info(f"Processing video document: {document.file_name}, {document.mime_type}")
        
        # Get document file
        document_file = await context.bot.get_file(document.file_id)
        
        # Generate a unique filename or use the original
        file_name = document.file_name
        if not file_name:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_extension = ".mp4"
            file_name = f"video_{timestamp}_{document.file_unique_id}{file_extension}"
        
        # Download the document to memory
        from io import BytesIO
        document_data = BytesIO()
        await document_file.download_to_memory(document_data)
        document_data.seek(0)  # Reset file pointer to beginning
        
        # Use the generic file upload handler
        await self._handle_file_upload(
            update, 
            context, 
            'video', 
            document.mime_type, 
            document_data, 
            file_name, 
            'Video Document'
        )
        
    async def _handle_misc_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle miscellaneous documents by uploading to Google Drive and logging to spreadsheet.
        
        Args:
            update: The update containing the document message
            context: The context object
        """
        message = update.message
        document = message.document
        
        # Log document details
        logger.info(f"Processing misc document: {document.file_name}, {document.mime_type}")
        
        # Get document file
        document_file = await context.bot.get_file(document.file_id)
        
        # Use the original filename or generate one
        file_name = document.file_name
        if not file_name:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"file_{timestamp}_{document.file_unique_id}"
        
        # Download the document to memory
        from io import BytesIO
        document_data = BytesIO()
        await document_file.download_to_memory(document_data)
        document_data.seek(0)  # Reset file pointer to beginning
        
        # Use the generic file upload handler
        await self._handle_file_upload(
            update, 
            context, 
            'misc', 
            document.mime_type or 'application/octet-stream', 
            document_data, 
            file_name, 
            'Document'
        )
    
    async def _handle_video_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle video messages by uploading to Google Drive and logging to spreadsheet.
        
        Args:
            update: The update containing the video message
            context: The context object
        """
        message = update.message
        video = message.video
        
        # Log video details
        logger.info(f"Processing video message: duration {video.duration}s, file size {video.file_size} bytes")
        
        # Get video file
        video_file = await context.bot.get_file(video.file_id)
        
        # Generate a unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = video.file_name
        if not file_name:
            file_name = f"video_{timestamp}_{video.file_unique_id}.mp4"
        
        # Download the video to memory
        from io import BytesIO
        video_data = BytesIO()
        await video_file.download_to_memory(video_data)
        video_data.seek(0)  # Reset file pointer to beginning
        
        # Use the generic file upload handler
        await self._handle_file_upload(
            update, 
            context, 
            'video', 
            'video/mp4', 
            video_data, 
            file_name, 
            'Video'
        )
    
    async def _handle_audio_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle audio messages by uploading to Google Drive and logging to spreadsheet.
        
        Args:
            update: The update containing the audio message
            context: The context object
        """
        message = update.message
        audio = message.audio
        
        # Log audio details
        logger.info(f"Processing audio message: {audio.title or 'Untitled'}, duration {audio.duration}s")
        
        # Get audio file
        audio_file = await context.bot.get_file(audio.file_id)
        
        # Generate a filename based on audio metadata or a timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if audio.title and audio.performer:
            file_name = f"{audio.performer} - {audio.title}.mp3"
        elif audio.title:
            file_name = f"{audio.title}.mp3"
        elif audio.file_name:
            file_name = audio.file_name
        else:
            file_name = f"audio_{timestamp}_{audio.file_unique_id}.mp3"
        
        # Download the audio to memory
        from io import BytesIO
        audio_data = BytesIO()
        await audio_file.download_to_memory(audio_data)
        audio_data.seek(0)  # Reset file pointer to beginning
        
        # Use the generic file upload handler
        await self._handle_file_upload(
            update, 
            context, 
            'audio', 
            'audio/mpeg', 
            audio_data, 
            file_name, 
            'Audio'
        )
    
    async def _handle_voice_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle voice messages by uploading to Google Drive and logging to spreadsheet.
        
        Args:
            update: The update containing the voice message
            context: The context object
        """
        message = update.message
        voice = message.voice
        
        # Log voice details
        logger.info(f"Processing voice message: duration {voice.duration}s")
        
        # Get voice file
        voice_file = await context.bot.get_file(voice.file_id)
        
        # Generate a unique filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"voice_{timestamp}_{voice.file_unique_id}.ogg"
        
        # Download the voice to memory
        from io import BytesIO
        voice_data = BytesIO()
        await voice_file.download_to_memory(voice_data)
        voice_data.seek(0)  # Reset file pointer to beginning
        
        # Use the generic file upload handler
        await self._handle_file_upload(
            update, 
            context, 
            'audio', 
            'audio/ogg', 
            voice_data, 
            file_name, 
            'Voice Message'
        )
    
    async def _handle_video_note(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle video notes (circular videos) by uploading to Google Drive and logging to spreadsheet.
        
        Args:
            update: The update containing the video note message
            context: The context object
        """
        message = update.message
        video_note = message.video_note
        
        # Log video note details
        logger.info(f"Processing video note: duration {video_note.duration}s, length {video_note.length}px")
        
        # Get video note file
        video_note_file = await context.bot.get_file(video_note.file_id)
        
        # Generate a unique filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"video_note_{timestamp}_{video_note.file_unique_id}.mp4"
        
        # Download the video note to memory
        from io import BytesIO
        video_note_data = BytesIO()
        await video_note_file.download_to_memory(video_note_data)
        video_note_data.seek(0)  # Reset file pointer to beginning
        
        # Use the generic file upload handler
        await self._handle_file_upload(
            update, 
            context, 
            'video', 
            'video/mp4', 
            video_note_data, 
            file_name, 
            'Video Note'
        )
    
    async def _delete_message_after_delay(self, message, delay_seconds):
        """Delete a message after a specified delay.
        
        Args:
            message: The message to delete
            delay_seconds: Number of seconds to wait before deletion
        """
        try:
            # Wait for the specified delay
            await asyncio.sleep(delay_seconds)
            
            # Delete the message
            await message.delete()
            logger.info(f"Auto-deleted message after {delay_seconds} seconds")
        except Exception as e:
            # Don't raise exceptions - this is a background task
            logger.error(f"Error auto-deleting message: {e}")
    
    def __del__(self):
        """Clean up resources when the bot is destroyed."""
        if hasattr(self, 'db'):
            self.db.close()