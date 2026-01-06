"""Local filesystem storage backend.

Stores files in the local filesystem, typically in ``static/uploads/``.
Intended for development use only - use GCS in production.

Example::

    from feather.storage.local import LocalStorage

    storage = LocalStorage('/path/to/static')
    url = storage.upload(file, 'uploads/photo.jpg')
    # Returns: /static/uploads/photo.jpg
"""

import os
import shutil
from pathlib import Path
from typing import BinaryIO, Optional, Union

from feather.storage.base import StorageBackend
from feather.exceptions import StorageError


class LocalStorage(StorageBackend):
    """Local filesystem storage backend.

    Stores files in a directory under the application's static folder.
    URLs are served via Flask's static file serving.

    Args:
        static_folder: Path to the static folder (e.g., '/app/static').
        upload_dir: Subdirectory for uploads (default: 'uploads').

    Example::

        storage = LocalStorage('/app/static')
        url = storage.upload(image_file, 'images/photo.jpg')
        # File saved to: /app/static/uploads/images/photo.jpg
        # URL returned: /static/uploads/images/photo.jpg

    Note:
        This backend is for development only. For production, use
        GCS to avoid:
        - Data loss on container restart
        - Disk space issues
        - Multi-instance sync problems
    """

    def __init__(self, static_folder: Union[str, Path], upload_dir: str = "uploads"):
        """Initialize local storage.

        Args:
            static_folder: Path to Flask's static folder.
            upload_dir: Subdirectory within static for uploads.
        """
        self.static_folder = Path(static_folder)
        self.upload_dir = upload_dir
        self.upload_path = self.static_folder / upload_dir

        # Ensure upload directory exists
        self.upload_path.mkdir(parents=True, exist_ok=True)

    def upload(
        self,
        file: Union[BinaryIO, bytes, Path, str],
        path: str,
        content_type: Optional[str] = None,
    ) -> str:
        """Upload a file to local storage.

        Args:
            file: File to upload (file object, bytes, or path).
            path: Destination path relative to upload directory.
            content_type: MIME type (ignored for local storage).

        Returns:
            URL path to access the file (e.g., '/static/uploads/photo.jpg').

        Raises:
            StorageError: If upload fails.
        """
        try:
            dest_path = self.upload_path / path

            # Ensure parent directory exists
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            # Handle different input types
            if isinstance(file, bytes):
                dest_path.write_bytes(file)
            elif isinstance(file, (str, Path)):
                source_path = Path(file)
                if not source_path.exists():
                    raise StorageError(f"Source file not found: {file}")
                shutil.copy2(source_path, dest_path)
            else:
                # File-like object
                with open(dest_path, "wb") as f:
                    # Read in chunks to handle large files
                    while chunk := file.read(8192):
                        f.write(chunk)

            # Return URL path
            return f"/static/{self.upload_dir}/{path}"

        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to upload file: {e}")

    def download(self, path: str) -> bytes:
        """Download a file from local storage.

        Args:
            path: Path relative to upload directory.

        Returns:
            File contents as bytes.

        Raises:
            StorageError: If file doesn't exist or read fails.
        """
        try:
            file_path = self.upload_path / path

            if not file_path.exists():
                raise StorageError(f"File not found: {path}")

            return file_path.read_bytes()

        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to download file: {e}")

    def delete(self, path: str) -> bool:
        """Delete a file from local storage.

        Args:
            path: Path relative to upload directory.

        Returns:
            True if file was deleted, False if it didn't exist.

        Raises:
            StorageError: If deletion fails.
        """
        try:
            file_path = self.upload_path / path

            if not file_path.exists():
                return False

            file_path.unlink()
            return True

        except Exception as e:
            raise StorageError(f"Failed to delete file: {e}")

    def get_url(self, path: str, expires_in: int = 3600) -> str:
        """Get URL for a file.

        For local storage, this returns a static file URL.
        The expires_in parameter is ignored (local files don't expire).

        Args:
            path: Path relative to upload directory.
            expires_in: Ignored for local storage.

        Returns:
            URL path to access the file.

        Raises:
            StorageError: If file doesn't exist.
        """
        file_path = self.upload_path / path

        if not file_path.exists():
            raise StorageError(f"File not found: {path}")

        return f"/static/{self.upload_dir}/{path}"

    def exists(self, path: str) -> bool:
        """Check if a file exists in local storage.

        Args:
            path: Path relative to upload directory.

        Returns:
            True if file exists, False otherwise.
        """
        file_path = self.upload_path / path
        return file_path.exists()
