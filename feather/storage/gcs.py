"""Google Cloud Storage backend.

Stores files in a GCS bucket. Requires the ``google-cloud-storage`` package
and valid GCP credentials.

Configuration::

    # .env
    STORAGE_BACKEND=gcs
    GCS_BUCKET=my-bucket-name

    # For production, add service account JSON (single line):
    GCS_CREDENTIALS_JSON={"type":"service_account","project_id":"..."}

    # For local development, use default credentials:
    gcloud auth application-default login

Example::

    from feather.storage.gcs import GCSStorage

    storage = GCSStorage('my-bucket')
    url = storage.upload(file, 'uploads/photo.jpg')
"""

from datetime import timedelta
from pathlib import Path
from typing import BinaryIO, Optional, Union

from feather.storage.base import StorageBackend
from feather.exceptions import StorageError


class GCSStorage(StorageBackend):
    """Google Cloud Storage backend.

    Stores files in a GCS bucket. Supports both public and private files
    with signed URL generation.

    Args:
        bucket_name: Name of the GCS bucket.
        credentials_json: Optional service account JSON as string.
                         If not provided, uses default credentials.
        public: If True, uploaded files are publicly accessible (default: False).

    Example::

        # Using default credentials (local dev)
        storage = GCSStorage('my-bucket')

        # Using inline credentials JSON (production)
        storage = GCSStorage('my-bucket', credentials_json='{"type":"service_account",...}')

        # Upload a file
        url = storage.upload(image_file, 'images/photo.jpg', 'image/jpeg')

        # Get a signed URL for private file
        signed_url = storage.get_url('private/doc.pdf', expires_in=3600)

    Authentication:
        GCS uses Google's default credential chain when credentials_json is not provided:
        1. GOOGLE_APPLICATION_CREDENTIALS environment variable
        2. gcloud CLI default credentials (for local dev)
        3. GCE/GKE service account (in production)
    """

    def __init__(
        self,
        bucket_name: str,
        credentials_json: Optional[str] = None,
        public: bool = False,
    ):
        """Initialize GCS storage.

        Args:
            bucket_name: Name of the GCS bucket.
            credentials_json: Optional service account JSON as string.
                             If not provided, uses default credentials.
            public: Whether uploaded files should be public by default.
        """
        try:
            from google.cloud import storage
        except ImportError:
            raise StorageError(
                "google-cloud-storage is required for GCS storage. "
                "Install it with: pip install google-cloud-storage"
            )

        self.bucket_name = bucket_name
        self.public = public

        # Initialize client
        if credentials_json:
            import json
            from google.oauth2 import service_account
            creds_info = json.loads(credentials_json)
            credentials = service_account.Credentials.from_service_account_info(creds_info)
            self.client = storage.Client(credentials=credentials, project=creds_info.get("project_id"))
        else:
            self.client = storage.Client()

        # Get bucket reference
        self.bucket = self.client.bucket(bucket_name)

    def upload(
        self,
        file: Union[BinaryIO, bytes, Path, str],
        path: str,
        content_type: Optional[str] = None,
    ) -> str:
        """Upload a file to GCS.

        Args:
            file: File to upload (file object, bytes, or path).
            path: Destination path in the bucket.
            content_type: MIME type. Auto-detected if not provided.

        Returns:
            Public URL if file is public, otherwise the GCS URI.

        Raises:
            StorageError: If upload fails.
        """
        try:
            blob = self.bucket.blob(path)

            # Detect content type if not provided
            if not content_type:
                content_type = self.get_content_type(path)

            # Handle different input types
            if isinstance(file, bytes):
                blob.upload_from_string(file, content_type=content_type)
            elif isinstance(file, (str, Path)):
                blob.upload_from_filename(str(file), content_type=content_type)
            else:
                # File-like object
                blob.upload_from_file(file, content_type=content_type)

            # Make public if configured
            if self.public:
                blob.make_public()
                return blob.public_url

            # Return GCS URI for private files
            return f"gs://{self.bucket_name}/{path}"

        except Exception as e:
            raise StorageError(f"Failed to upload to GCS: {e}")

    def download(self, path: str) -> bytes:
        """Download a file from GCS.

        Args:
            path: Path in the bucket.

        Returns:
            File contents as bytes.

        Raises:
            StorageError: If download fails or file doesn't exist.
        """
        try:
            blob = self.bucket.blob(path)

            if not blob.exists():
                raise StorageError(f"File not found in GCS: {path}")

            return blob.download_as_bytes()

        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to download from GCS: {e}")

    def delete(self, path: str) -> bool:
        """Delete a file from GCS.

        Args:
            path: Path in the bucket.

        Returns:
            True if file was deleted, False if it didn't exist.

        Raises:
            StorageError: If deletion fails.
        """
        try:
            blob = self.bucket.blob(path)

            if not blob.exists():
                return False

            blob.delete()
            return True

        except Exception as e:
            raise StorageError(f"Failed to delete from GCS: {e}")

    def get_url(self, path: str, expires_in: int = 3600) -> str:
        """Get URL for accessing a file.

        For public files, returns the public URL.
        For private files, returns a signed URL.

        Args:
            path: Path in the bucket.
            expires_in: Seconds until signed URL expires (default 1 hour).

        Returns:
            URL to access the file.

        Raises:
            StorageError: If file doesn't exist or URL generation fails.
        """
        try:
            blob = self.bucket.blob(path)

            if not blob.exists():
                raise StorageError(f"File not found in GCS: {path}")

            # Return public URL for public files
            if self.public:
                return blob.public_url

            # Generate signed URL for private files
            return blob.generate_signed_url(
                expiration=timedelta(seconds=expires_in),
                method="GET",
            )

        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to generate GCS URL: {e}")

    def exists(self, path: str) -> bool:
        """Check if a file exists in GCS.

        Args:
            path: Path in the bucket.

        Returns:
            True if file exists, False otherwise.
        """
        try:
            blob = self.bucket.blob(path)
            return blob.exists()
        except Exception:
            return False
