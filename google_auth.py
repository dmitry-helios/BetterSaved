"""
Google OAuth and Drive API operations for BetterSaved bot.
"""
import json
import logging
from typing import Optional, Dict, Any, Tuple
import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configure logging
logger = logging.getLogger(__name__)

# If modifying these scopes, delete the file token.json.
SCOPES = [
    'https://www.googleapis.com/auth/drive.file',  # For Drive operations
    'https://www.googleapis.com/auth/spreadsheets'  # For Sheets operations
]

class GoogleDriveManager:
    """Manages Google Drive operations and authentication."""
    
    def __init__(self, credentials_file: str = 'client_secret.json'):
        """Initialize with the path to client secrets file."""
        self.credentials_file = credentials_file
        
    def get_authorization_url(self) -> Tuple[str, str]:
        """
        Generate the authorization URL for the user to visit.
        
        Returns:
            Tuple containing (auth_url, state)
        """
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                self.credentials_file, SCOPES)
            flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'  # For command-line authorization
            
            # Generate the authorization URL
            auth_url, state = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent')
            
            return auth_url, state
        except Exception as e:
            logger.error(f"Error generating authorization URL: {e}")
            raise
    
    def exchange_code_for_tokens(self, code: str, state: Optional[str] = None) -> Dict[str, Any]:
        """
        Exchange authorization code for access and refresh tokens.
        
        Args:
            code: The authorization code from Google
            state: The state parameter from the authorization request
            
        Returns:
            Dictionary containing token information
        """
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                self.credentials_file, SCOPES)
            flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'  # For command-line authorization
            
            # Exchange the code for tokens
            flow.fetch_token(code=code)
            
            # Get credentials
            credentials = flow.credentials
            
            # Convert credentials to a serializable dictionary
            token_info = {
                'token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri,
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scopes': credentials.scopes
            }
            
            return token_info
        except Exception as e:
            logger.error(f"Error exchanging code for tokens: {e}")
            raise
    
    def create_credentials_from_token_info(self, token_info: Dict[str, Any]) -> Credentials:
        """
        Create Google OAuth2 credentials from token information.
        
        Args:
            token_info: Dictionary containing token information
            
        Returns:
            Google OAuth2 Credentials object
        """
        try:
            credentials = Credentials(
                token=token_info['token'],
                refresh_token=token_info['refresh_token'],
                token_uri=token_info['token_uri'],
                client_id=token_info['client_id'],
                client_secret=token_info['client_secret'],
                scopes=token_info['scopes']
            )
            
            # Refresh the token if it's expired
            if credentials.expired:
                credentials.refresh(Request())
                
                # Update token_info with refreshed token
                token_info['token'] = credentials.token
                
            return credentials
        except Exception as e:
            logger.error(f"Error creating credentials from token info: {e}")
            raise
    
    def create_folder(self, token_info: Dict[str, Any], folder_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a folder in the user's Google Drive.
        
        Args:
            token_info: Dictionary containing token information
            folder_name: Name of the folder to create
            
        Returns:
            Dictionary with folder_id, folder_url, and success status
        """
        if folder_name is None:
            folder_name = os.getenv("GOOGLE_DRIVE_FOLDER", "BetterSaved")
        try:
            credentials = self.create_credentials_from_token_info(token_info)
            
            # Build the Drive API client
            drive_service = build('drive', 'v3', credentials=credentials)
            
            # Check if folder already exists
            results = drive_service.files().list(
                q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
                spaces='drive',
                fields='files(id, name)'
            ).execute()
            
            items = results.get('files', [])
            
            if items:
                # Folder already exists, return its ID and URL
                folder_id = items[0]['id']
                folder_url = f"https://drive.google.com/drive/folders/{folder_id}"
                logger.info(f"Folder '{folder_name}' already exists with ID: {folder_id}")
                
                # Check if subfolders and spreadsheet exist, create if not
                subfolder_results = self.create_subfolders(credentials, folder_id)
                spreadsheet_result = self.create_spreadsheet(credentials, folder_id)
                
                return {
                    'folder_id': folder_id,
                    'folder_url': folder_url,
                    'success': True,
                    'subfolders': subfolder_results,
                    'spreadsheet': spreadsheet_result
                }
            
            # Folder doesn't exist, create it
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            
            folder = drive_service.files().create(
                body=file_metadata,
                fields='id'
            ).execute()
            
            folder_id = folder.get('id')
            folder_url = f"https://drive.google.com/drive/folders/{folder_id}"
            logger.info(f"Created folder '{folder_name}' with ID: {folder_id}")
            
            # Create subfolders and spreadsheet
            subfolder_results = self.create_subfolders(credentials, folder_id)
            spreadsheet_result = self.create_spreadsheet(credentials, folder_id)
            
            # Log the spreadsheet result structure
            logger.info(f"Spreadsheet result structure: {spreadsheet_result}")
            
            # Create the return structure
            result = {
                'folder_id': folder_id,
                'folder_url': folder_url,
                'success': True,
                'subfolders': subfolder_results,
                'spreadsheet': spreadsheet_result
            }
            
            # Log the full result structure
            logger.info(f"Full create_folder result structure: {result}")
            
            return result
        except HttpError as e:
            logger.error(f"Error creating folder: {e}")
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"Unexpected error creating folder: {e}")
            return {'success': False, 'error': str(e)}
    
    def create_spreadsheet(self, credentials: Credentials, parent_folder_id: str) -> Dict[str, Any]:
        """
        Create a Google Sheet in the specified folder with predefined columns.
        
        Args:
            credentials: Google OAuth credentials
            parent_folder_id: ID of the parent folder
            
        Returns:
            Dictionary with spreadsheet_id, spreadsheet_url, and success status
        """
        try:
            # Build the Sheets and Drive API clients
            sheets_service = build('sheets', 'v4', credentials=credentials)
            drive_service = build('drive', 'v3', credentials=credentials)
            
            # Check if spreadsheet already exists
            results = drive_service.files().list(
                q=f"name='BetterSavedMessages' and mimeType='application/vnd.google-apps.spreadsheet' and '{parent_folder_id}' in parents and trashed=false",
                spaces='drive',
                fields='files(id, name)'
            ).execute()
            
            items = results.get('files', [])
            
            if items:
                # Spreadsheet already exists
                spreadsheet_id = items[0]['id']
                spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
                logger.info(f"Spreadsheet 'BetterSavedMessages' already exists with ID: {spreadsheet_id}")
                return {
                    'spreadsheet_id': spreadsheet_id,
                    'spreadsheet_url': spreadsheet_url,
                    'success': True,
                    'created': False
                }
            
            # Create a new spreadsheet
            spreadsheet_body = {
                'properties': {
                    'title': 'BetterSavedMessages'
                },
                'sheets': [{
                    'properties': {
                        'title': 'Messages'
                    }
                }]
            }
            
            spreadsheet = sheets_service.spreadsheets().create(
                body=spreadsheet_body,
                fields='spreadsheetId'
            ).execute()
            
            spreadsheet_id = spreadsheet.get('spreadsheetId')
            
            # Move the spreadsheet to the BetterSaved folder
            drive_service.files().update(
                fileId=spreadsheet_id,
                addParents=parent_folder_id,
                removeParents='root',
                fields='id, parents'
            ).execute()
            
            # Add headers to the spreadsheet
            values = [
                ['Timestamp', 'Source', 'Category', 'Content', 'ForwardedFrom', 'Link']
            ]
            body = {
                'values': values
            }
            
            sheets_service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range='Messages!A1:F1',
                valueInputOption='RAW',
                body=body
            ).execute()
            
            # Format headers (make bold and freeze)
            requests = [
                {
                    'updateSheetProperties': {
                        'properties': {
                            'gridProperties': {
                                'frozenRowCount': 1
                            },
                            'sheetId': 0
                        },
                        'fields': 'gridProperties.frozenRowCount'
                    }
                },
                {
                    'repeatCell': {
                        'range': {
                            'sheetId': 0,
                            'startRowIndex': 0,
                            'endRowIndex': 1
                        },
                        'cell': {
                            'userEnteredFormat': {
                                'textFormat': {
                                    'bold': True
                                },
                                'backgroundColor': {
                                    'red': 0.9,
                                    'green': 0.9,
                                    'blue': 0.9
                                }
                            }
                        },
                        'fields': 'userEnteredFormat'
                    }
                }
            ]
            
            sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={'requests': requests}
            ).execute()
            
            spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
            logger.info(f"Created spreadsheet 'BetterSavedMessages' with ID: {spreadsheet_id}")
            
            # Create the result structure with detailed info
            result = {
                'spreadsheet_id': spreadsheet_id,
                'spreadsheet_url': spreadsheet_url,
                'success': True,
                'created': True
            }
            
            # Log the result structure
            logger.info(f"Spreadsheet creation result: {result}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error creating spreadsheet: {e}")
            return {'success': False, 'error': str(e)}
    
    def create_subfolders(self, credentials: Credentials, parent_folder_id: str) -> Dict[str, Any]:
        """
        Create subfolders in the BetterSaved folder.
        
        Args:
            credentials: Google OAuth credentials
            parent_folder_id: ID of the parent folder
            
        Returns:
            Dictionary with results of folder creation
        """
        try:
            # Build the Drive API client
            drive_service = build('drive', 'v3', credentials=credentials)
            
            # Subfolders to create
            subfolder_names = ['Images', 'Video', 'Audio', 'PDF', 'Tickets']
            results = {}
            
            for folder_name in subfolder_names:
                # Check if subfolder already exists
                query = drive_service.files().list(
                    q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and '{parent_folder_id}' in parents and trashed=false",
                    spaces='drive',
                    fields='files(id, name)'
                ).execute()
                
                items = query.get('files', [])
                
                if items:
                    # Subfolder already exists
                    subfolder_id = items[0]['id']
                    logger.info(f"Subfolder '{folder_name}' already exists with ID: {subfolder_id}")
                    results[folder_name] = {
                        'folder_id': subfolder_id,
                        'created': False
                    }
                else:
                    # Create subfolder
                    file_metadata = {
                        'name': folder_name,
                        'mimeType': 'application/vnd.google-apps.folder',
                        'parents': [parent_folder_id]
                    }
                    
                    subfolder = drive_service.files().create(
                        body=file_metadata,
                        fields='id'
                    ).execute()
                    
                    subfolder_id = subfolder.get('id')
                    logger.info(f"Created subfolder '{folder_name}' with ID: {subfolder_id}")
                    results[folder_name] = {
                        'folder_id': subfolder_id,
                        'created': True
                    }
            
            return {
                'success': True,
                'folders': results
            }
            
        except Exception as e:
            logger.error(f"Error creating subfolders: {e}")
            return {'success': False, 'error': str(e)}
    
    def upload_file_to_drive(self, token_info: Dict[str, Any], parent_folder_id: str, file_data, file_name: str, 
                          file_type: str = 'image', mime_type: str = 'image/jpeg') -> Dict[str, Any]:
        """
        Upload a file to the user's Google Drive in the appropriate folder structure.
        
        Args:
            token_info: Dictionary containing token information
            parent_folder_id: ID of the parent BetterSaved folder
            file_data: File-like object containing the file data
            file_name: Name to give the file in Google Drive
            file_type: Type of file ('image', 'video', 'audio', 'pdf', 'misc')
            mime_type: MIME type of the file
            
        Returns:
            Dictionary with success status, file_id, and file_url
        """
        try:
            credentials = self.create_credentials_from_token_info(token_info)
            
            # Build the Drive API client
            drive_service = build('drive', 'v3', credentials=credentials)
            
            # Determine the appropriate folder based on file type
            folder_mapping = {
                'image': "Images",
                'video': "Videos",
                'audio': "Audio",
                'pdf': "PDFs",
                'misc': "MiscFiles"
            }
            
            # Use the appropriate folder or default to MiscFiles
            type_folder_name = folder_mapping.get(file_type.lower(), "MiscFiles")
            
            # First, get or create the type folder (Images, Videos, etc.)
            type_folder_id = self._get_or_create_folder(drive_service, type_folder_name, parent_folder_id)
            
            # Create month folder (YYYY-MM format)
            import datetime
            current_month = datetime.datetime.now().strftime("%Y-%m")
            month_folder_id = self._get_or_create_folder(drive_service, current_month, type_folder_id)
            
            # Upload the file to the month folder
            file_metadata = {
                'name': file_name,
                'parents': [month_folder_id]
            }
            
            # Create a MediaFileUpload object
            from googleapiclient.http import MediaIoBaseUpload
            media = MediaIoBaseUpload(file_data, mimetype=mime_type, resumable=True)
            
            # Upload the file
            file = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            file_id = file.get('id')
            file_url = f"https://drive.google.com/file/d/{file_id}/view"
            
            logger.info(f"Uploaded {file_type} file to Google Drive: {file_url}")
            
            return {
                'success': True,
                'file_id': file_id,
                'file_url': file_url
            }
            
        except Exception as e:
            logger.error(f"Error uploading {file_type} file to Google Drive: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'error': str(e)
            }
    
    def upload_photo_to_drive(self, token_info: Dict[str, Any], parent_folder_id: str, photo_file, file_name: str) -> Dict[str, Any]:
        """
        Upload a photo to the user's Google Drive in the appropriate month folder.
        
        Args:
            token_info: Dictionary containing token information
            parent_folder_id: ID of the parent BetterSaved folder
            photo_file: File-like object containing the photo data
            file_name: Name to give the file in Google Drive
            
        Returns:
            Dictionary with success status, file_id, and file_url
        """
        # For backward compatibility, this now calls the generic upload_file_to_drive method
        return self.upload_file_to_drive(
            token_info=token_info,
            parent_folder_id=parent_folder_id,
            file_data=photo_file,
            file_name=file_name,
            file_type='image',
            mime_type='image/jpeg'
        )
    
    def _get_or_create_folder(self, drive_service, folder_name: str, parent_folder_id: str) -> str:
        """
        Get a folder ID if it exists, or create it if it doesn't.
        
        Args:
            drive_service: Google Drive service instance
            folder_name: Name of the folder to find or create
            parent_folder_id: ID of the parent folder
            
        Returns:
            Folder ID
        """
        # Check if folder exists
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and '{parent_folder_id}' in parents and trashed=false"
        results = drive_service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)'
        ).execute()
        
        items = results.get('files', [])
        
        if items:
            # Folder exists, return its ID
            return items[0]['id']
        else:
            # Create the folder
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_folder_id]
            }
            
            folder = drive_service.files().create(
                body=folder_metadata,
                fields='id'
            ).execute()
            
            return folder.get('id')
    
    def save_message_to_sheet(self, token_info: Dict[str, Any], spreadsheet_id: str, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Save a message to the user's Google Sheet.
        
        Args:
            token_info: Dictionary containing token information
            spreadsheet_id: ID of the spreadsheet to save to
            message_data: Dictionary containing message content and metadata
            
        Returns:
            Dictionary with success status and details
        """
        try:
            if not spreadsheet_id:
                return {
                    'success': False,
                    'error': 'No spreadsheet ID provided'
                }
                
            credentials = self.create_credentials_from_token_info(token_info)
            
            # Build the Sheets API client
            sheets_service = build('sheets', 'v4', credentials=credentials)
            
            # Get current timestamp
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Extract message text and metadata
            message_text = message_data.get('text', '')
            is_forwarded = message_data.get('is_forwarded', False)
            
            # Determine source based on forwarding info
            source = 'Telegram Bot Chat'
            
            # Get category and link from message data or use defaults
            category = message_data.get('category', 'None')
            link = message_data.get('link', '')
            
            # Add forwarding information if available
            if is_forwarded:
                forward_from = message_data.get('forward_from')
                forward_from_chat = message_data.get('forward_from_chat')
                
                if forward_from:
                    source = f"Forwarded from {forward_from}"
                elif forward_from_chat:
                    source = f"Forwarded from {forward_from_chat}"
                else:
                    source = "Forwarded message"
                    
                # Only set category to Forwarded if it wasn't explicitly set
                if category == 'None':
                    category = 'Forwarded'
            
            # Prepare row data
            values = [
                [timestamp, source, category, message_text, link]
            ]
            body = {
                'values': values
            }
            
            # Append the row to the sheet
            result = sheets_service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range='Messages!A:E',
                valueInputOption='USER_ENTERED',
                insertDataOption='INSERT_ROWS',
                body=body
            ).execute()
            
            updated_range = result.get('updates', {}).get('updatedRange', '')
            logger.info(f"Message saved to sheet: {updated_range}")
            
            return {
                'success': True,
                'updated_range': updated_range
            }
            
        except Exception as e:
            logger.error(f"Error saving message to sheet: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def test_token_validity(self, token_info: Dict[str, Any]) -> bool:
        """
        Test if the provided token is valid.
        
        Args:
            token_info: Dictionary containing token information
            
        Returns:
            True if token is valid, False otherwise
        """
        try:
            credentials = self.create_credentials_from_token_info(token_info)
            
            # Build the Drive API client
            drive_service = build('drive', 'v3', credentials=credentials)
            
            # Try to list files (minimal request to test validity)
            drive_service.files().list(pageSize=1).execute()
            
            return True
        except Exception as e:
            logger.error(f"Token validation failed: {e}")
            return False
