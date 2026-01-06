"""File storage utilities (local filesystem and Google Cloud Storage).

Feather provides a unified storage interface for file uploads. Configure
the backend via the ``STORAGE_BACKEND`` config setting.

Quick Start::

    from feather.storage import get_storage

    storage = get_storage()
    url = storage.upload(file, 'uploads/photo.jpg')

Configuration::

    # .env
    STORAGE_BACKEND=local  # or 'gcs'

    # For GCS
    STORAGE_BACKEND=gcs
    GCS_BUCKET=my-bucket

Available Backends:
    - ``local``: Local filesystem (development only)
    - ``gcs``: Google Cloud Storage
"""

from typing import Optional, TYPE_CHECKING

from feather.storage.base import StorageBackend
from feather.storage.local import LocalStorage
from feather.storage.gcs import GCSStorage

if TYPE_CHECKING:
    from flask import Flask


def get_storage(app: Optional["Flask"] = None) -> StorageBackend:
    """Get the configured storage backend.

    Returns the appropriate storage backend based on the app's configuration.
    Uses ``STORAGE_BACKEND`` config setting to determine which backend to use.

    Args:
        app: Flask app instance. If not provided, uses ``current_app``.

    Returns:
        Configured storage backend instance.

    Raises:
        StorageError: If configuration is invalid or backend initialization fails.

    Configuration:
        STORAGE_BACKEND: 'local' or 'gcs' (default: 'local')
        GCS_BUCKET: Required if STORAGE_BACKEND='gcs'

    Example::

        from feather.storage import get_storage

        # In a route or service
        storage = get_storage()
        url = storage.upload(request.files['image'], 'uploads/photo.jpg')

        # With explicit app
        storage = get_storage(app)
    """
    from flask import current_app
    from feather.exceptions import StorageError

    app = app or current_app

    backend = app.config.get("STORAGE_BACKEND", "local")

    if backend == "gcs":
        bucket = app.config.get("GCS_BUCKET")
        if not bucket:
            raise StorageError(
                "GCS_BUCKET is required when STORAGE_BACKEND='gcs'. "
                "Set it in your .env file."
            )
        credentials_json = app.config.get("GCS_CREDENTIALS_JSON")
        return GCSStorage(bucket, credentials_json=credentials_json)

    else:
        # Default to local storage
        return LocalStorage(app.static_folder)


__all__ = [
    "StorageBackend",
    "LocalStorage",
    "GCSStorage",
    "get_storage",
]
