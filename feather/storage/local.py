"""Local filesystem storage backend.

Stores files in the local filesystem, typically in ``static/uploads/``.
Intended for development use only - use GCS in production.

Example::

    from feather.storage.local import LocalStorage

    storage = LocalStorage('/path/to/static')
    url = storage.upload(file, 'uploads/photo.jpg')
    # Returns: /static/uploads/photo.jpg

Security
--------
Every path is resolved and must stay inside the upload directory; ``../``
segments, absolute paths and symlinks that point outside raise
:class:`~feather.exceptions.StorageError`.

Because uploads live under ``static/`` they are served by Flask with a
content type derived from the extension, so an uploaded ``.html`` or ``.svg``
would execute on the application origin. Script-capable extensions are
therefore refused by default (see :data:`DEFAULT_BLOCKED_EXTENSIONS`). Adjust
with the ``STORAGE_BLOCKED_EXTENSIONS`` / ``STORAGE_ALLOWED_EXTENSIONS``
config keys (comma-separated strings or lists). To accept SVG uploads, for
example, either list only the types you take::

    STORAGE_ALLOWED_EXTENSIONS=jpg,jpeg,png,gif,webp,svg

or replace the block list without ``svg``::

    STORAGE_BLOCKED_EXTENSIONS=html,htm,xhtml,xml,js,mjs,php,phtml
"""

import re
import shutil
from pathlib import Path
from typing import BinaryIO, Iterable, Optional, Union

from feather.storage.base import StorageBackend
from feather.exceptions import StorageError


#: Extensions refused by ``upload`` unless overridden. Each of these is served
#: by browsers with a content type that can run script on the app origin
#: (or, for PHP, be executed by a misconfigured server in front of Flask).
DEFAULT_BLOCKED_EXTENSIONS = frozenset(
    {"html", "htm", "svg", "xhtml", "xml", "js", "mjs", "php", "phtml"}
)

_WINDOWS_DRIVE = re.compile(r"^[a-zA-Z]:")


def normalise_extensions(value: Union[None, str, Iterable[str]]) -> Optional[frozenset]:
    """Turn a config value into a set of lower-case extensions without dots.

    Accepts ``None`` (returns ``None``), a comma-separated string such as
    ``"jpg, .png,SVG"`` or any iterable of strings.
    """
    if value is None:
        return None
    if isinstance(value, str):
        items = value.split(",")
    else:
        items = list(value)
    cleaned = {str(item).strip().lower().lstrip(".") for item in items}
    cleaned.discard("")
    return frozenset(cleaned)


class LocalStorage(StorageBackend):
    """Local filesystem storage backend.

    Stores files in a directory under the application's static folder.
    URLs are served via Flask's static file serving.

    Args:
        static_folder: Path to the static folder (e.g., '/app/static').
        upload_dir: Subdirectory for uploads (default: 'uploads').
        allowed_extensions: If given, only these extensions may be uploaded
            (an allow-list wins over the block list, so listing ``svg`` here
            permits SVG uploads).
        blocked_extensions: Extensions to refuse. Defaults to
            :data:`DEFAULT_BLOCKED_EXTENSIONS`; passing a value replaces the
            default list entirely.

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

    def __init__(
        self,
        static_folder: Union[str, Path],
        upload_dir: str = "uploads",
        allowed_extensions: Union[None, str, Iterable[str]] = None,
        blocked_extensions: Union[None, str, Iterable[str]] = None,
    ):
        """Initialize local storage.

        Args:
            static_folder: Path to Flask's static folder.
            upload_dir: Subdirectory within static for uploads.
            allowed_extensions: Optional allow-list of extensions.
            blocked_extensions: Optional block-list of extensions (replaces
                the default list).
        """
        self.static_folder = Path(static_folder)
        self.upload_dir = upload_dir
        self.upload_path = self.static_folder / upload_dir

        self.allowed_extensions = normalise_extensions(allowed_extensions)
        blocked = normalise_extensions(blocked_extensions)
        self.blocked_extensions = DEFAULT_BLOCKED_EXTENSIONS if blocked is None else blocked

        # Ensure upload directory exists
        self.upload_path.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Path safety
    # ------------------------------------------------------------------

    def _resolve(self, path: Union[str, Path]) -> Path:
        """Resolve ``path`` inside the upload directory or raise.

        Rejects empty paths, absolute paths (POSIX or Windows-style), and
        anything that, after resolving ``..`` segments and symlinks, does not
        land strictly inside ``self.upload_path``.

        Returns:
            The absolute, resolved filesystem path.

        Raises:
            StorageError: If the path would escape the upload directory.
        """
        raw = str(path) if path is not None else ""
        if not raw.strip():
            raise StorageError("Invalid storage path: path is empty")

        candidate = Path(raw)
        if candidate.is_absolute() or raw.startswith(("/", "\\")) or _WINDOWS_DRIVE.match(raw):
            raise StorageError(f"Invalid storage path: absolute paths are not allowed: {raw}")

        base = self.upload_path.resolve()
        resolved = (base / candidate).resolve()

        if resolved == base or not resolved.is_relative_to(base):
            raise StorageError(f"Invalid storage path: escapes upload directory: {raw}")

        return resolved

    def _relative(self, resolved: Path) -> str:
        """URL-style relative path (forward slashes) inside the upload dir."""
        return resolved.relative_to(self.upload_path.resolve()).as_posix()

    def _check_extension(self, path: str) -> None:
        """Refuse uploads whose extension is blocked or not allowed.

        Raises:
            StorageError: If the extension is not permitted.
        """
        ext = Path(path).suffix.lower().lstrip(".")

        if self.allowed_extensions is not None:
            if ext not in self.allowed_extensions:
                allowed = ", ".join(sorted(self.allowed_extensions))
                raise StorageError(
                    f"File extension '.{ext}' is not allowed (STORAGE_ALLOWED_EXTENSIONS: {allowed})"
                )
            return

        if ext and ext in self.blocked_extensions:
            raise StorageError(
                f"File extension '.{ext}' is blocked because it can run script when served "
                "from the app origin. Set STORAGE_ALLOWED_EXTENSIONS or "
                "STORAGE_BLOCKED_EXTENSIONS to change this."
            )

    # ------------------------------------------------------------------
    # StorageBackend interface
    # ------------------------------------------------------------------

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
            StorageError: If upload fails, the path escapes the upload
                directory, or the extension is not permitted.
        """
        dest_path = self._resolve(path)
        self._check_extension(dest_path.name)

        try:
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
            return f"/static/{self.upload_dir}/{self._relative(dest_path)}"

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
            StorageError: If file doesn't exist, read fails, or the path
                escapes the upload directory.
        """
        file_path = self._resolve(path)

        try:
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
            StorageError: If deletion fails or the path escapes the upload
                directory.
        """
        file_path = self._resolve(path)

        try:
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
            StorageError: If file doesn't exist or the path escapes the
                upload directory.
        """
        file_path = self._resolve(path)

        if not file_path.exists():
            raise StorageError(f"File not found: {path}")

        return f"/static/{self.upload_dir}/{self._relative(file_path)}"

    def exists(self, path: str) -> bool:
        """Check if a file exists in local storage.

        Args:
            path: Path relative to upload directory.

        Returns:
            True if file exists, False otherwise.

        Raises:
            StorageError: If the path escapes the upload directory.
        """
        return self._resolve(path).exists()
