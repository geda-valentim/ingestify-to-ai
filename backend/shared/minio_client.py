import io
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
        self._remove_public_read_policies()

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

    def _remove_public_read_policies(self):
        """
        Make sure no bucket allows anonymous reads.

        Earlier versions set a public "s3:GetObject for *" policy on the uploads,
        pages and results buckets, exposing every user's documents to anyone who
        could guess an object key. Files are now served through the API after an
        ownership check, so the policy is removed from existing buckets too.
        """
        for bucket_name in [
            self.bucket_uploads,
            self.bucket_pages,
            self.bucket_audio,
            self.bucket_results,
            self.bucket_crawled,
        ]:
            # Fail closed: if the policy can't be checked or removed, the client is not
            # created (get_minio_client retries on the next call) instead of silently
            # running with buckets that may still be publicly readable.
            try:
                policy = self.client.get_bucket_policy(bucket_name)
            except S3Error as e:
                if e.code == "NoSuchBucketPolicy":
                    continue
                raise RuntimeError(f"Could not verify that bucket {bucket_name} is private: {e}") from e

            if not policy:
                continue
            try:
                self.client.delete_bucket_policy(bucket_name)
                logger.info(f"Removed public read policy from bucket: {bucket_name}")
            except S3Error as e:
                raise RuntimeError(f"Could not remove the public policy from bucket {bucket_name}: {e}") from e

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
            elif file_data is not None:
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

    def open_object(self, bucket_name: str, object_name: str):
        """
        Open an object for streaming.

        Returns the urllib3 response: iterate with .stream(chunk_size), then call
        .close() and .release_conn(). Raises S3Error if the object does not exist.
        """
        return self.client.get_object(bucket_name, object_name)

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
