from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin
import asyncio
import ipaddress
import socket
import httpx
import logging

from shared.config import get_settings

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

    MAX_REDIRECTS = 5

    async def download(self, source: str, temp_path: Path, **kwargs) -> Path:
        """Download file from URL"""
        logger.info(f"Downloading from URL: {source}")

        # Create temp directory
        temp_path.mkdir(parents=True, exist_ok=True)

        # Extract filename from URL or use default
        filename = source.split('/')[-1].split('?')[0] or 'downloaded_file'
        if filename in ('.', '..'):
            filename = 'downloaded_file'
        if '.' not in filename:
            filename += '.pdf'  # Default extension

        file_path = temp_path / filename
        max_bytes = get_settings().max_file_size_mb * 1024 * 1024

        try:
            # Redirects are followed manually so every hop is re-validated
            async with httpx.AsyncClient(follow_redirects=False, timeout=30.0) as client:
                url = source
                for _ in range(self.MAX_REDIRECTS + 1):
                    response = await _send_pinned(client, url)
                    try:
                        if response.is_redirect:
                            location = response.headers.get('location')
                            if not location:
                                raise Exception("Redirect without Location header")
                            url = urljoin(url, location)
                            continue

                        response.raise_for_status()

                        downloaded = 0
                        with open(file_path, 'wb') as f:
                            async for chunk in response.aiter_bytes():
                                downloaded += len(chunk)
                                if downloaded > max_bytes:
                                    raise Exception(
                                        f"File exceeds maximum size of {get_settings().max_file_size_mb}MB"
                                    )
                                f.write(chunk)

                        logger.info(f"Downloaded {downloaded} bytes to {file_path}")
                        return file_path
                    finally:
                        await response.aclose()

                raise Exception(f"Too many redirects (max {self.MAX_REDIRECTS})")

        except httpx.HTTPError as e:
            file_path.unlink(missing_ok=True)
            logger.error(f"HTTP error downloading file: {e}")
            raise Exception(f"Failed to download from URL: {str(e)}")
        except Exception as e:
            file_path.unlink(missing_ok=True)
            logger.error(f"Error downloading file: {e}")
            raise Exception(f"Download failed: {str(e)}")

    def validate(self, source: str, **kwargs) -> bool:
        """Validate URL format"""
        try:
            # Basic URL validation
            return source.startswith(('http://', 'https://'))
        except Exception:
            return False


# NAT64 well-known prefix: the last 32 bits are an IPv4 address (RFC 6052)
_NAT64_PREFIX = ipaddress.ip_network("64:ff9b::/96")


def _is_public_ip(ip: "ipaddress.IPv4Address | ipaddress.IPv6Address") -> bool:
    """True only for globally routable unicast addresses"""
    if isinstance(ip, ipaddress.IPv6Address):
        # IPv6 forms that embed an IPv4 address are judged by that address
        if ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        elif ip in _NAT64_PREFIX:
            ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return ip.is_global and not ip.is_multicast


async def _resolve_public_ips(host: str, port: int) -> list:
    """
    Resolve host and ensure every address is public.

    Blocks SSRF to loopback, private networks, link-local (cloud metadata at
    169.254.169.254), CGNAT and other reserved ranges, including internal
    Docker services such as redis, elasticsearch and minio.

    Returns:
        The validated addresses, in resolver order
    """
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise Exception(f"Could not resolve host {host}: {e}")

    addresses = list(dict.fromkeys(info[4][0] for info in infos))
    if not addresses:
        raise Exception(f"Could not resolve host {host}")

    for address in addresses:
        if not _is_public_ip(ipaddress.ip_address(address.split('%')[0])):
            raise Exception(f"URL host {host} resolves to a non-public address, refusing to download")

    return addresses


async def _send_pinned(client: httpx.AsyncClient, url: str) -> httpx.Response:
    """
    Validate a URL and send a streamed GET to one of its already-validated IPs.

    Connecting to the resolved IP (instead of letting the HTTP client resolve the
    name again) prevents DNS rebinding between the check and the connection.
    The original host is kept in the Host header and TLS SNI/certificate check.
    Addresses are tried in resolver order until one connects.
    """
    parsed = httpx.URL(url)
    if parsed.scheme not in ('http', 'https'):
        raise Exception(f"Unsupported URL scheme: {parsed.scheme or '(none)'}")
    if not parsed.host:
        raise Exception("URL has no host")
    if parsed.userinfo:
        raise Exception("URLs with credentials are not allowed")

    # ASCII form of the host (IDNA "xn--" for internationalized names)
    host = parsed.raw_host.decode('ascii')
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    addresses = await _resolve_public_ips(host, port)

    host_header = f"[{host}]" if ':' in host else host
    if parsed.port is not None:
        host_header = f"{host_header}:{parsed.port}"

    last_error = None
    for ip in addresses:
        request = client.build_request(
            'GET',
            parsed.copy_with(host=ip),
            headers={'Host': host_header},
            extensions={'sni_hostname': host},
        )
        try:
            return await client.send(request, stream=True)
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            logger.warning(f"Could not connect to {host} at {ip}: {e}")
            last_error = e

    raise last_error


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
