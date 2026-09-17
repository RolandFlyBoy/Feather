"""File storage utilities (local filesystem, S3-compatible and Google Cloud Storage).

Feather provides a unified storage interface for file uploads. Configure
the backend via the ``STORAGE_BACKEND`` config setting.

Quick Start::

    from feather.storage import get_storage

    storage = get_storage()
    url = storage.upload(file, 'uploads/photo.jpg')

Configuration::

    # .env
    STORAGE_BACKEND=local  # or 's3' or 'gcs'

    # For S3 or an S3-compatible service (STORAGE_BACKEND defaults to s3
    # when S3_BUCKET is set)
    S3_BUCKET=my-bucket
    S3_ENDPOINT=https://s3.example.com

    # For GCS
    STORAGE_BACKEND=gcs
    GCS_BUCKET=my-bucket

Available Backends:
    - ``local``: Local filesystem (development only)
    - ``s3``: AWS S3 or an S3-compatible service
    - ``gcs``: Google Cloud Storage
"""

from typing import Optional, TYPE_CHECKING

from feather.storage.base import StorageBackend
from feather.storage.local import LocalStorage
from feather.storage.gcs import GCSStorage
from feather.storage.s3 import S3Storage

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
        STORAGE_BACKEND: 'local', 's3' or 'gcs'. Unset: 's3' when S3_BUCKET
            is set, otherwise STORAGE_BACKEND_FALLBACK or 'local'
        S3_BUCKET, S3_ENDPOINT, S3_REGION, S3_ACCESS_KEY_ID,
        S3_SECRET_ACCESS_KEY, S3_ADDRESSING_STYLE, S3_URL_EXPIRES,
        S3_PUBLIC_URL: see :mod:`feather.storage.s3`
        GCS_BUCKET: Required if STORAGE_BACKEND='gcs'
        STORAGE_ALLOWED_EXTENSIONS: Optional allow-list for local and S3 uploads
            (comma-separated string or list). When set, only these
            extensions are accepted.
        STORAGE_BLOCKED_EXTENSIONS: Extensions refused by local and S3 uploads.
            Default: html, htm, svg, xhtml, xml, js, mjs, php, phtml.
            Setting it replaces the default list.

    Example::

        from feather.storage import get_storage

        # In a route or service
        storage = get_storage()
        url = storage.upload(request.files['image'], 'uploads/photo.jpg')

        # With explicit app
        storage = get_storage(app)
    """
    from flask import current_app
    from feather.core.config import config_lookup, resolve_backend
    from feather.exceptions import StorageError

    app = app or current_app
    setting = config_lookup(app.config)

    backend, _ = resolve_backend("STORAGE_BACKEND", setting)

    if backend == "s3":
        from feather.storage.s3 import s3_storage_from_settings

        if not setting("S3_BUCKET"):
            raise StorageError(
                "S3_BUCKET is required when STORAGE_BACKEND='s3'. "
                "Set it in your .env file."
            )
        return s3_storage_from_settings(setting)

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
        return LocalStorage(
            app.static_folder,
            allowed_extensions=app.config.get("STORAGE_ALLOWED_EXTENSIONS"),
            blocked_extensions=app.config.get("STORAGE_BLOCKED_EXTENSIONS"),
        )


__all__ = [
    "StorageBackend",
    "LocalStorage",
    "GCSStorage",
    "S3Storage",
    "get_storage",
]
