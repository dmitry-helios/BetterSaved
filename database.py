"""
Database operations for the BetterSaved bot.
testiung
"""
import sqlite3
import os
import logging
from typing import Optional, Tuple, Dict, Any

# Configure logging
logger = logging.getLogger(__name__)

class Database:
    """SQLite database manager for BetterSaved bot."""
    
    def __init__(self, db_path: Optional[str] = None):
        """Initialize the database connection."""
        if db_path is None:
            db_path = os.getenv("DB_PATH", "users.db")
        self.db_path = db_path
        self.conn = None
        self.cursor = None
        self.connect()
        self.setup_tables()
    
    def connect(self):
        """Connect to the SQLite database."""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.cursor = self.conn.cursor()
            logger.info(f"Connected to database: {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Database connection error: {e}")
            raise
    
    def setup_tables(self):
        """Create necessary tables if they don't exist."""
        try:
            # Create users table
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                telegram_id TEXT UNIQUE,
                name TEXT,
                key_gdrive TEXT,
                folder_id TEXT,
                folder_url TEXT,
                spreadsheet_id TEXT,
                spreadsheet_url TEXT,
                connect_msg_shown INTEGER DEFAULT 0,
                lang TEXT DEFAULT 'en'
            )
            ''')
            self.conn.commit()
            logger.info("Database tables initialized")
        except sqlite3.Error as e:
            logger.error(f"Error setting up database tables: {e}")
            raise
    
    def update_user_language(self, user_id: str, lang: str) -> bool:
        """Update user's language preference.
        
        Args:
            user_id: The user's ID
            lang: Language code (e.g., 'en', 'es')
            
        Returns:
            bool: True if update was successful, False otherwise
        """
        try:
            self.cursor.execute(
                "UPDATE users SET lang = ? WHERE user_id = ?",
                (lang, user_id)
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error updating user language: {e}")
            return False
    
    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
    
    def get_user_by_telegram_id(self, telegram_id: str) -> Optional[Dict[str, Any]]:
        """Get user data by Telegram ID."""
        try:
            self.cursor.execute(
                "SELECT user_id, telegram_id, name, key_gdrive, folder_id, folder_url, spreadsheet_id, spreadsheet_url, lang FROM users WHERE telegram_id = ?", 
                (telegram_id,)
            )
            user = self.cursor.fetchone()
            
            if user:
                return {
                    "user_id": user[0],
                    "telegram_id": user[1],
                    "name": user[2],
                    "key_gdrive": user[3],
                    "folder_id": user[4],
                    "folder_url": user[5],
                    "spreadsheet_id": user[6],
                    "spreadsheet_url": user[7],
                    "lang": user[8] if len(user) > 8 else 'en'  # Default to 'en' if column doesn't exist yet
                }
            return None
        except sqlite3.Error as e:
            logger.error(f"Error getting user by Telegram ID: {e}")
            return None
    
    def create_or_update_user(self, telegram_id: str, name: str, key_gdrive: str = "", folder_id: str = "", folder_url: str = "", spreadsheet_id: str = "", spreadsheet_url: str = "") -> Optional[str]:
        """Create a new user or update existing user."""
        try:
            # Check if user already exists
            existing_user = self.get_user_by_telegram_id(telegram_id)
            
            if existing_user:
                # Update existing user
                user_id = existing_user["user_id"]
                self.cursor.execute(
                    "UPDATE users SET name = ?, key_gdrive = ?, folder_id = ?, folder_url = ?, spreadsheet_id = ?, spreadsheet_url = ? WHERE user_id = ?",
                    (name, key_gdrive, folder_id, folder_url, spreadsheet_id, spreadsheet_url, user_id)
                )
            else:
                # Create new user with a unique ID
                user_id = f"user_{telegram_id}"
                self.cursor.execute(
                    "INSERT INTO users (user_id, telegram_id, name, key_gdrive, folder_id, folder_url, spreadsheet_id, spreadsheet_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (user_id, telegram_id, name, key_gdrive, folder_id, folder_url, spreadsheet_id, spreadsheet_url)
                )
            
            self.conn.commit()
            return user_id
        except sqlite3.Error as e:
            logger.error(f"Error creating/updating user: {e}")
            return None
            
    def update_user_drive_token(self, telegram_id: str, token_info: str) -> bool:
        """Update a user's Google Drive token information.
        
        Args:
            telegram_id: The user's Telegram ID
            token_info: JSON string containing token information
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.cursor.execute(
                "UPDATE users SET key_gdrive = ? WHERE telegram_id = ?",
                (token_info, telegram_id)
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error updating user drive token: {e}")
            return False
    
    def get_user_drive_token(self, telegram_id: str) -> Optional[str]:
        """Get a user's Google Drive token information.
        
        Args:
            telegram_id: The user's Telegram ID
            
        Returns:
            JSON string containing token information, or None if not found
        """
        try:
            self.cursor.execute(
                "SELECT key_gdrive FROM users WHERE telegram_id = ?",
                (telegram_id,)
            )
            result = self.cursor.fetchone()
            if result and result[0]:
                return result[0]
            return None
        except sqlite3.Error as e:
            logger.error(f"Error getting user drive token: {e}")
            return None
            
    def update_drive_folder_info(self, telegram_id: str, folder_id: str, folder_url: str) -> bool:
        """Update a user's Google Drive folder information.
        
        Args:
            telegram_id: The user's Telegram ID
            folder_id: The ID of the user's BetterSaved folder
            folder_url: The URL of the user's BetterSaved folder
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.cursor.execute(
                "UPDATE users SET folder_id = ?, folder_url = ? WHERE telegram_id = ?",
                (folder_id, folder_url, telegram_id)
            )
            self.conn.commit()
            logger.info(f"Updated Drive folder info for user {telegram_id}")
            return True
        except sqlite3.Error as e:
            logger.error(f"Error updating user drive folder info: {e}")
            return False
            
    def update_drive_spreadsheet_info(self, telegram_id: str, spreadsheet_id: str, spreadsheet_url: str) -> bool:
        """Update a user's Google Drive spreadsheet information.
        
        Args:
            telegram_id: The user's Telegram ID
            spreadsheet_id: The ID of the user's BetterSaved spreadsheet
            spreadsheet_url: The URL of the user's BetterSaved spreadsheet
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.cursor.execute(
                "UPDATE users SET spreadsheet_id = ?, spreadsheet_url = ? WHERE telegram_id = ?",
                (spreadsheet_id, spreadsheet_url, telegram_id)
            )
            self.conn.commit()
            logger.info(f"Updated Drive spreadsheet info for user {telegram_id}")
            return True
        except sqlite3.Error as e:
            logger.error(f"Error updating user drive spreadsheet info: {e}")
            return False
            
    def get_user_drive_info(self, telegram_id: str) -> Optional[Dict[str, str]]:
        """Get a user's Google Drive folder and spreadsheet information.
        
        Args:
            telegram_id: The user's Telegram ID
            
        Returns:
            Dictionary containing folder_id, folder_url, spreadsheet_id, and spreadsheet_url,
            or None if not found
        """
        try:
            self.cursor.execute(
                "SELECT folder_id, folder_url, spreadsheet_id, spreadsheet_url FROM users WHERE telegram_id = ?",
                (telegram_id,)
            )
            result = self.cursor.fetchone()
            if result:
                return {
                    "folder_id": result[0] or "",
                    "folder_url": result[1] or "",
                    "spreadsheet_id": result[2] or "",
                    "spreadsheet_url": result[3] or ""
                }
            return None
        except sqlite3.Error as e:
            logger.error(f"Error getting user drive info: {e}")
            return None
            
    def debug_view_user(self, telegram_id: str) -> Dict[str, Any]:
        """Get all user data for debugging purposes.
        
        Args:
            telegram_id: The user's Telegram ID
            
        Returns:
            Dictionary containing all user data, or empty dict if not found
        """
        try:
            self.cursor.execute(
                "SELECT * FROM users WHERE telegram_id = ?", 
                (telegram_id,)
            )
            columns = [column[0] for column in self.cursor.description]
            user = self.cursor.fetchone()
            
            if user:
                user_dict = {columns[i]: user[i] for i in range(len(columns))}
                logger.info(f"DEBUG - User data for {telegram_id}: {user_dict}")
                return user_dict
            
            logger.warning(f"DEBUG - No user found with telegram_id {telegram_id}")
            return {}
        except sqlite3.Error as e:
            logger.error(f"DEBUG - Error viewing user data: {e}")
            return {}
            
    def check_connect_msg_shown(self, telegram_id: str) -> bool:
        """Check if the connect message has been shown to the user.
        
        Args:
            telegram_id: The user's Telegram ID
            
        Returns:
            True if the message has been shown, False otherwise
        """
        try:
            self.cursor.execute(
                "SELECT connect_msg_shown FROM users WHERE telegram_id = ?",
                (telegram_id,)
            )
            result = self.cursor.fetchone()
            if result and result[0] == 1:
                return True
            return False
        except sqlite3.Error as e:
            logger.error(f"Error checking connect message status: {e}")
            return False
            
    def mark_connect_msg_shown(self, telegram_id: str) -> bool:
        """Mark that the connect message has been shown to the user.
        
        Args:
            telegram_id: The user's Telegram ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.cursor.execute(
                "UPDATE users SET connect_msg_shown = 1 WHERE telegram_id = ?",
                (telegram_id,)
            )
            self.conn.commit()
            logger.info(f"Marked connect message as shown for user {telegram_id}")
            return True
        except sqlite3.Error as e:
            logger.error(f"Error marking connect message as shown: {e}")
            return False
            
    def delete_user(self, telegram_id: str) -> bool:
        """Delete a user from the database.
        
        Args:
            telegram_id: The user's Telegram ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Check if user exists first
            self.cursor.execute(
                "SELECT user_id FROM users WHERE telegram_id = ?",
                (telegram_id,)
            )
            user = self.cursor.fetchone()
            
            if not user:
                logger.warning(f"Attempted to delete non-existent user {telegram_id}")
                return False
                
            # Delete the user
            self.cursor.execute(
                "DELETE FROM users WHERE telegram_id = ?",
                (telegram_id,)
            )
            self.conn.commit()
            logger.info(f"Deleted user {telegram_id} from database")
            return True
        except sqlite3.Error as e:
            logger.error(f"Error deleting user: {e}")
            return False
