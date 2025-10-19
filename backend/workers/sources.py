from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
import httpx
import logging

logger = logging.getLogger(__name__)


class SourceHandler(ABC):
    """Abstract base class for source handlers"""

    @abstractmethod
    async def download(self, source: str, temp_path: Path, **kwargs) -> Path:
        """Download file and return local path"""
        pass

    @abstractmethod
    def validate(self, source: str, **kwargs) -> bool:
        """Validate if source is accessible"""
        pass


class FileHandler(SourceHandler):
    """Handler for uploaded files"""

    async def download(self, source: str, temp_path: Path, **kwargs) -> Path:
        """File is already local, just return the path"""
        file_path = Path(source)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {source}")
        return file_path

    def validate(self, source: str, **kwargs) -> bool:
        """Validate file exists and is readable"""
        try:
            file_path = Path(source)
            return file_path.exists() and file_path.is_file()
        except Exception as e:
            logger.error(f"File validation failed: {e}")
            return False


class URLHandler(SourceHandler):
    """Handler for URL downloads"""

    async def download(self, source: str, temp_path: Path, **kwargs) -> Path:
        """Download file from URL"""
        logger.info(f"Downloading from URL: {source}")

        # Create temp directory
        temp_path.mkdir(parents=True, exist_ok=True)

        # Extract filename from URL or use default
        filename = source.split('/')[-1].split('?')[0] or 'downloaded_file'
        if '.' not in filename:
            filename += '.pdf'  # Default extension

        file_path = temp_path / filename

        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                response = await client.get(source)
                response.raise_for_status()

                # Write to file
                with open(file_path, 'wb') as f:
                    f.write(response.content)

                logger.info(f"Downloaded {len(response.content)} bytes to {file_path}")
                return file_path

        except httpx.HTTPError as e:
            logger.error(f"HTTP error downloading file: {e}")
            raise Exception(f"Failed to download from URL: {str(e)}")
        except Exception as e:
            logger.error(f"Error downloading file: {e}")
            raise Exception(f"Download failed: {str(e)}")

    def validate(self, source: str, **kwargs) -> bool:
        """Validate URL format"""
        try:
            # Basic URL validation
            return source.startswith(('http://', 'https://'))
        except Exception:
            return False


class GoogleDriveHandler(SourceHandler):
    """Handler for Google Drive files"""

    async def download(self, source: str, temp_path: Path, **kwargs) -> Path:
        """Download file from Google Drive"""
        auth_token = kwargs.get('auth_token')
        if not auth_token:
            raise ValueError("auth_token is required for Google Drive")

        logger.info(f"Downloading from Google Drive: {source}")

        # Create temp directory
        temp_path.mkdir(parents=True, exist_ok=True)
        file_path = temp_path / f"gdrive_{source}"

        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaIoBaseDownload
            import io

            # Create credentials from token
            creds = Credentials(token=auth_token)

            # Build Drive service
            service = build('drive', 'v3', credentials=creds)

            # Download file
            request = service.files().get_media(fileId=source)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)

            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    logger.info(f"Download progress: {int(status.progress() * 100)}%")

            # Write to file
            with open(file_path, 'wb') as f:
                f.write(fh.getvalue())

            logger.info(f"Downloaded from Google Drive to {file_path}")
            return file_path

        except Exception as e:
            logger.error(f"Google Drive download failed: {e}")
            raise Exception(f"Failed to download from Google Drive: {str(e)}")

    def validate(self, source: str, **kwargs) -> bool:
        """Validate Google Drive file ID"""
        auth_token = kwargs.get('auth_token')
        if not auth_token:
            return False

        try:
            # Basic validation: file ID should be alphanumeric
            return bool(source and len(source) > 10)
        except Exception:
            return False


class DropboxHandler(SourceHandler):
    """Handler for Dropbox files"""

    async def download(self, source: str, temp_path: Path, **kwargs) -> Path:
        """Download file from Dropbox"""
        auth_token = kwargs.get('auth_token')
        if not auth_token:
            raise ValueError("auth_token is required for Dropbox")

        logger.info(f"Downloading from Dropbox: {source}")

        # Create temp directory
        temp_path.mkdir(parents=True, exist_ok=True)
        filename = source.split('/')[-1] or 'dropbox_file'
        file_path = temp_path / filename

        try:
            import dropbox

            # Create Dropbox client
            dbx = dropbox.Dropbox(auth_token)

            # Download file
            metadata, response = dbx.files_download(source)

            # Write to file
            with open(file_path, 'wb') as f:
                f.write(response.content)

            logger.info(f"Downloaded from Dropbox to {file_path}")
            return file_path

        except Exception as e:
            logger.error(f"Dropbox download failed: {e}")
            raise Exception(f"Failed to download from Dropbox: {str(e)}")

    def validate(self, source: str, **kwargs) -> bool:
        """Validate Dropbox path"""
        auth_token = kwargs.get('auth_token')
        if not auth_token:
            return False

        try:
            # Basic validation: path should start with /
            return source.startswith('/')
        except Exception:
            return False


def get_source_handler(source_type: str) -> SourceHandler:
    """Get appropriate source handler based on type"""
    handlers = {
        'file': FileHandler(),
        'url': URLHandler(),
        'gdrive': GoogleDriveHandler(),
        'dropbox': DropboxHandler(),
    }

    handler = handlers.get(source_type)
    if not handler:
        raise ValueError(f"Unknown source type: {source_type}")

    return handler
