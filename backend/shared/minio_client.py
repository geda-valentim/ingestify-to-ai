import io
import json
import logging
from typing import Optional, BinaryIO
from datetime import timedelta
from minio import Minio
from minio.error import S3Error
from shared.config import get_settings

logger = logging.getLogger(__name__)


class MinIOClient:
    def __init__(self, client: Optional[Minio] = None):
        """
        Initialize MinIO client

        Args:
            client: Optional Minio client instance (for testing). If None, creates production client.
        """
        settings = get_settings()

        if client is not None:
            # Use provided client (for testing)
            self.client = client
        else:
            # Create production MinIO client
            self.client = Minio(
                endpoint=settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure,
            )

        # Bucket names from config
        self.bucket_uploads = settings.minio_bucket_uploads
        self.bucket_pages = settings.minio_bucket_pages
        self.bucket_audio = settings.minio_bucket_audio
        self.bucket_results = settings.minio_bucket_results
        self.bucket_crawled = settings.minio_bucket_crawled

        # Initialize buckets on startup
        self._ensure_buckets_exist()
        self._set_public_read_policies()

    def _ensure_buckets_exist(self):
        """Create buckets if they don't exist"""
        buckets = [
            self.bucket_uploads,
            self.bucket_pages,
            self.bucket_audio,
            self.bucket_results,
            self.bucket_crawled,
        ]

        for bucket_name in buckets:
            try:
                if not self.client.bucket_exists(bucket_name):
                    self.client.make_bucket(bucket_name)
                    logger.info(f"Created MinIO bucket: {bucket_name}")
                else:
                    logger.info(f"MinIO bucket already exists: {bucket_name}")
            except S3Error as e:
                logger.error(f"Error ensuring bucket {bucket_name} exists: {e}")
                raise

    def _set_public_read_policies(self):
        """Set public read access policy for buckets"""
        # Buckets that should be publicly accessible
        public_buckets = [
            self.bucket_uploads,
            self.bucket_pages,
            self.bucket_results,
            self.bucket_crawled,
            # Note: bucket_audio is intentionally excluded from public access
        ]

        for bucket_name in public_buckets:
            try:
                # Define policy for public read access
                policy = {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"AWS": "*"},
                            "Action": ["s3:GetObject"],
                            "Resource": [f"arn:aws:s3:::{bucket_name}/*"]
                        }
                    ]
                }

                # Set bucket policy
                self.client.set_bucket_policy(bucket_name, json.dumps(policy))
                logger.info(f"Set public read policy for bucket: {bucket_name}")
            except S3Error as e:
                logger.warning(f"Failed to set public policy for {bucket_name}: {e}")
                # Don't raise - this is not critical, presigned URLs can still be used

    def health_check(self) -> bool:
        """Check MinIO connection by listing buckets"""
        try:
            self.client.list_buckets()
            return True
        except Exception as e:
            logger.error(f"MinIO health check failed: {e}")
            return False

    def upload_file(
        self,
        bucket_name: str,
        object_name: str,
        file_path: Optional[str] = None,
        file_data: Optional[bytes] = None,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Upload a file to MinIO

        Args:
            bucket_name: Name of the bucket
            object_name: Object name in MinIO (e.g., "uploads/job-123/file.pdf")
            file_path: Path to file on filesystem (provide either this or file_data)
            file_data: File data as bytes (provide either this or file_path)
            content_type: Content type of the file

        Returns:
            str: Object name/path in MinIO

        Raises:
            ValueError: If neither file_path nor file_data provided
            S3Error: If upload fails
        """
        try:
            if file_path:
                # Upload from file path
                self.client.fput_object(
                    bucket_name=bucket_name,
                    object_name=object_name,
                    file_path=file_path,
                    content_type=content_type,
                )
                logger.info(f"Uploaded file to MinIO: {bucket_name}/{object_name}")
            elif file_data:
                # Upload from bytes
                file_stream = io.BytesIO(file_data)
                self.client.put_object(
                    bucket_name=bucket_name,
                    object_name=object_name,
                    data=file_stream,
                    length=len(file_data),
                    content_type=content_type,
                )
                logger.info(f"Uploaded data to MinIO: {bucket_name}/{object_name}")
            else:
                raise ValueError("Either file_path or file_data must be provided")

            return object_name
        except S3Error as e:
            logger.error(f"Failed to upload to MinIO: {e}")
            raise

    def download_file(
        self,
        bucket_name: str,
        object_name: str,
        file_path: Optional[str] = None,
    ) -> Optional[bytes]:
        """
        Download a file from MinIO

        Args:
            bucket_name: Name of the bucket
            object_name: Object name in MinIO
            file_path: If provided, save to this path. If None, return bytes.

        Returns:
            bytes: File data if file_path is None, otherwise None

        Raises:
            S3Error: If download fails
        """
        try:
            if file_path:
                # Download to file path
                self.client.fget_object(
                    bucket_name=bucket_name,
                    object_name=object_name,
                    file_path=file_path,
                )
                logger.info(f"Downloaded from MinIO to {file_path}: {bucket_name}/{object_name}")
                return None
            else:
                # Download to memory
                response = self.client.get_object(bucket_name, object_name)
                data = response.read()
                response.close()
                response.release_conn()
                logger.info(f"Downloaded from MinIO to memory: {bucket_name}/{object_name}")
                return data
        except S3Error as e:
            logger.error(f"Failed to download from MinIO: {e}")
            raise

    def delete_file(self, bucket_name: str, object_name: str) -> bool:
        """
        Delete a file from MinIO

        Args:
            bucket_name: Name of the bucket
            object_name: Object name in MinIO

        Returns:
            bool: True if deleted successfully
        """
        try:
            self.client.remove_object(bucket_name, object_name)
            logger.info(f"Deleted from MinIO: {bucket_name}/{object_name}")
            return True
        except S3Error as e:
            logger.error(f"Failed to delete from MinIO: {e}")
            return False

    def delete_folder(self, bucket_name: str, folder_prefix: str) -> bool:
        """
        Delete all objects with a given prefix (folder)

        Args:
            bucket_name: Name of the bucket
            folder_prefix: Folder prefix (e.g., "uploads/job-123/")

        Returns:
            bool: True if all objects deleted successfully
        """
        try:
            # List all objects with this prefix
            objects = self.client.list_objects(
                bucket_name,
                prefix=folder_prefix,
                recursive=True,
            )

            # Delete each object
            for obj in objects:
                self.client.remove_object(bucket_name, obj.object_name)
                logger.debug(f"Deleted: {bucket_name}/{obj.object_name}")

            logger.info(f"Deleted folder from MinIO: {bucket_name}/{folder_prefix}")
            return True
        except S3Error as e:
            logger.error(f"Failed to delete folder from MinIO: {e}")
            return False

    def file_exists(self, bucket_name: str, object_name: str) -> bool:
        """
        Check if a file exists in MinIO

        Args:
            bucket_name: Name of the bucket
            object_name: Object name in MinIO

        Returns:
            bool: True if file exists
        """
        try:
            self.client.stat_object(bucket_name, object_name)
            return True
        except S3Error:
            return False

    def get_presigned_url(
        self,
        bucket_name: str,
        object_name: str,
        expires: timedelta = timedelta(hours=1),
    ) -> str:
        """
        Generate a presigned URL for temporary access to a file

        Args:
            bucket_name: Name of the bucket
            object_name: Object name in MinIO
            expires: Expiration time (default: 1 hour)

        Returns:
            str: Presigned URL
        """
        try:
            url = self.client.presigned_get_object(
                bucket_name=bucket_name,
                object_name=object_name,
                expires=expires,
            )
            logger.info(f"Generated presigned URL: {bucket_name}/{object_name}")
            return url
        except S3Error as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            raise

    def get_public_url(self, bucket_name: str, object_name: str, request_host: str = None) -> str:
        """
        Get public URL for a file (works if bucket has public read policy)

        Args:
            bucket_name: Name of the bucket
            object_name: Object name in MinIO
            request_host: Optional host from request (e.g., "example.com:8000", "192.168.1.10:8000")
                         If provided, uses same host but with MinIO port (9000)

        Returns:
            str: Public URL accessible from outside Docker network
        """
        settings = get_settings()

        # Determine endpoint to use
        if request_host:
            # Extract host without port and use MinIO port
            host_without_port = request_host.split(':')[0]
            public_endpoint = f"{host_without_port}:9000"
        else:
            # Use configured public endpoint
            public_endpoint = settings.minio_public_endpoint

        # Construct public URL
        # Format: http://public-endpoint/bucket-name/object-name
        protocol = "https" if settings.minio_secure else "http"
        url = f"{protocol}://{public_endpoint}/{bucket_name}/{object_name}"

        return url

    def list_objects(self, bucket_name: str, prefix: str = "") -> list:
        """
        List objects in a bucket with optional prefix

        Args:
            bucket_name: Name of the bucket
            prefix: Optional prefix to filter objects

        Returns:
            list: List of object names
        """
        try:
            objects = self.client.list_objects(
                bucket_name,
                prefix=prefix,
                recursive=True,
            )
            return [obj.object_name for obj in objects]
        except S3Error as e:
            logger.error(f"Failed to list objects in MinIO: {e}")
            return []


# Singleton instance
_minio_client: Optional[MinIOClient] = None


def get_minio_client() -> MinIOClient:
    """Get singleton MinIO client instance"""
    global _minio_client
    if _minio_client is None:
        _minio_client = MinIOClient()
    return _minio_client
