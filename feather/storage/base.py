"""Abstract base class for storage backends.

This module defines the interface that all storage backends must implement.
Feather supports local filesystem and Google Cloud Storage (GCS).

Example usage::

    from feather.storage import get_storage

    storage = get_storage()
    url = storage.upload(file, 'uploads/image.jpg', content_type='image/jpeg')
    storage.delete('uploads/image.jpg')
"""

from abc import ABC, abstractmethod
from typing import BinaryIO, Optional, Union
from pathlib import Path


class StorageBackend(ABC):
    """Abstract base class for file storage backends.

    All storage backends (local, GCS) must implement this interface.
    Use ``get_storage()`` to get the configured backend instance.

    Attributes:
        bucket_name: Name of the storage bucket/container (cloud backends only).

    Example::

        class MyStorage(StorageBackend):
            def upload(self, file, path, content_type=None):
                # Implementation
                pass
            # ... implement other methods
    """

    @abstractmethod
    def upload(
        self,
        file: Union[BinaryIO, bytes, Path, str],
        path: str,
        content_type: Optional[str] = None,
    ) -> str:
        """Upload a file and return its public URL.

        Args:
            file: File to upload. Can be:
                - A file-like object (opened in binary mode)
                - Raw bytes
                - A Path object pointing to a local file
                - A string path to a local file
            path: Destination path in storage (e.g., 'uploads/images/photo.jpg').
            content_type: MIME type (e.g., 'image/jpeg'). Auto-detected if not provided.

        Returns:
            Public URL of the uploaded file.

        Raises:
            StorageError: If upload fails.

        Example::

            # Upload from file object
            with open('photo.jpg', 'rb') as f:
                url = storage.upload(f, 'uploads/photo.jpg')

            # Upload from bytes
            url = storage.upload(image_bytes, 'uploads/photo.jpg', 'image/jpeg')

            # Upload from path
            url = storage.upload(Path('photo.jpg'), 'uploads/photo.jpg')
        """
        pass

    @abstractmethod
    def download(self, path: str) -> bytes:
        """Download a file's contents.

        Args:
            path: Path to the file in storage.

        Returns:
            File contents as bytes.

        Raises:
            StorageError: If download fails or file doesn't exist.

        Example::

            data = storage.download('uploads/photo.jpg')
            with open('local_copy.jpg', 'wb') as f:
                f.write(data)
        """
        pass

    @abstractmethod
    def delete(self, path: str) -> bool:
        """Delete a file from storage.

        Args:
            path: Path to the file in storage.

        Returns:
            True if file was deleted, False if file didn't exist.

        Raises:
            StorageError: If deletion fails for reasons other than file not existing.

        Example::

            if storage.delete('uploads/old_photo.jpg'):
                print("File deleted")
            else:
                print("File didn't exist")
        """
        pass

    @abstractmethod
    def get_url(self, path: str, expires_in: int = 3600) -> str:
        """Get a URL for accessing the file.

        For public files, returns the public URL.
        For private files, returns a signed URL that expires after ``expires_in`` seconds.

        Args:
            path: Path to the file in storage.
            expires_in: Seconds until signed URL expires (default 1 hour).
                       Ignored for public files.

        Returns:
            URL to access the file.

        Raises:
            StorageError: If URL generation fails.

        Example::

            # Get a URL valid for 1 hour
            url = storage.get_url('uploads/private_doc.pdf')

            # Get a URL valid for 24 hours
            url = storage.get_url('uploads/private_doc.pdf', expires_in=86400)
        """
        pass

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Check if a file exists in storage.

        Args:
            path: Path to check.

        Returns:
            True if file exists, False otherwise.

        Example::

            if storage.exists('uploads/photo.jpg'):
                url = storage.get_url('uploads/photo.jpg')
        """
        pass

    def get_content_type(self, path: str) -> str:
        """Guess MIME type from file extension.

        Args:
            path: File path to analyze.

        Returns:
            MIME type string (defaults to 'application/octet-stream').
        """
        import mimetypes

        content_type, _ = mimetypes.guess_type(path)
        return content_type or "application/octet-stream"
