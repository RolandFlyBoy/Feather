"""S3-compatible object storage backend.

Stores files in an S3 bucket: AWS S3, or any S3-compatible service
(MinIO, Garage, Cloudflare R2, Hetzner Object Storage) through
``S3_ENDPOINT``. Requires ``boto3``::

    pip install 'feather-framework[s3]'

Configuration::

    # .env
    STORAGE_BACKEND=s3                     # chosen automatically when S3_BUCKET is set
    S3_BUCKET=my-bucket
    S3_ENDPOINT=https://s3.example.com     # omit for AWS
    S3_REGION=eu-central-1
    S3_ACCESS_KEY_ID=...                   # omit both to use the boto3
    S3_SECRET_ACCESS_KEY=...               # credential chain (env, profile, role)
    S3_ADDRESSING_STYLE=path               # default: path with S3_ENDPOINT, else auto
    S3_URL_EXPIRES=3600                    # lifetime of presigned URLs, seconds
    S3_PUBLIC_URL=https://cdn.example.com  # optional: plain URLs instead of presigned

Buckets are treated as private. ``upload()`` and ``get_url()`` return a
presigned GET URL that expires after ``S3_URL_EXPIRES`` seconds, unless
``S3_PUBLIC_URL`` is set, in which case they return
``S3_PUBLIC_URL/<key>``.

Security
--------
Keys are validated before any request: empty keys, absolute keys, ``.`` and
``..`` segments, backslashes and control characters raise
:class:`~feather.exceptions.StorageError`. Uploads apply the same extension
rules as local storage (``STORAGE_ALLOWED_EXTENSIONS`` /
``STORAGE_BLOCKED_EXTENSIONS``, default block list in
:data:`feather.storage.local.DEFAULT_BLOCKED_EXTENSIONS`), because a bucket
served from a domain of your own can run script on it just like ``static/``.
"""

import os
from pathlib import Path
from typing import Any, BinaryIO, Iterable, Optional, Union
from urllib.parse import quote

from feather._optional import MissingDependencyError, require
from feather.exceptions import StorageError
from feather.storage.base import StorageBackend
from feather.storage.local import DEFAULT_BLOCKED_EXTENSIONS, normalise_extensions

#: Presigned URL lifetime when neither the call nor ``S3_URL_EXPIRES`` sets one.
DEFAULT_URL_EXPIRES = 3600

#: Addressing styles botocore accepts.
ADDRESSING_STYLES = ("auto", "path", "virtual")

#: Error codes S3 and compatible services return for a missing key.
_NOT_FOUND_CODES = {"404", "NoSuchKey", "NotFound"}


class MissingS3Dependency(MissingDependencyError, StorageError):
    """boto3 is not installed.

    Subclasses both ``MissingDependencyError`` (an ``ImportError``) and
    ``StorageError``, the same shape as the GCS backend's error.
    """

    def __init__(self, message: str):
        MissingDependencyError.__init__(self, message)
        self.message = message
        self.status_code = 500
        self.error_code = "STORAGE_ERROR"


def default_addressing_style(endpoint: Optional[str]) -> str:
    """``path`` for a custom endpoint, ``auto`` for AWS.

    Most S3-compatible services do not serve virtual-hosted buckets
    (``bucket.s3.example.com``) without extra DNS, so path style
    (``s3.example.com/bucket``) is the safe default there.
    """
    return "path" if endpoint else "auto"


def _error_code(exc: Exception) -> str:
    response = getattr(exc, "response", None) or {}
    return str((response.get("Error") or {}).get("Code", ""))


class S3Storage(StorageBackend):
    """S3 and S3-compatible storage backend.

    Args:
        bucket_name: Bucket to store files in.
        endpoint_url: Endpoint of an S3-compatible service. ``None`` for AWS.
        region: Region name. ``None`` lets boto3 resolve it.
        access_key_id: Access key. When this and ``secret_access_key`` are
            both unset, boto3's default credential chain is used.
        secret_access_key: Secret key.
        addressing_style: ``path``, ``virtual`` or ``auto``. Defaults to
            ``path`` when ``endpoint_url`` is set, else ``auto``.
        url_expires: Default lifetime of presigned URLs, in seconds.
        public_url: Base URL the bucket is publicly served from. When set,
            URLs are ``public_url/<key>`` and nothing is presigned.
        allowed_extensions: If given, only these extensions may be uploaded.
        blocked_extensions: Extensions to refuse. Defaults to
            :data:`~feather.storage.local.DEFAULT_BLOCKED_EXTENSIONS`.
        client: A ready boto3 S3 client, mainly for tests. The connection
            arguments above are ignored when it is given.

    Example::

        storage = S3Storage("uploads", endpoint_url="https://s3.example.com",
                            region="garage")
        url = storage.upload(image_bytes, "avatars/42.png")
    """

    def __init__(
        self,
        bucket_name: str,
        endpoint_url: Optional[str] = None,
        region: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        addressing_style: Optional[str] = None,
        url_expires: Union[int, str, None] = None,
        public_url: Optional[str] = None,
        allowed_extensions: Union[None, str, Iterable[str]] = None,
        blocked_extensions: Union[None, str, Iterable[str]] = None,
        client: Any = None,
    ):
        if not bucket_name:
            raise StorageError("S3_BUCKET is required for the S3 storage backend.")

        self.bucket_name = bucket_name
        self.endpoint_url = endpoint_url or None
        self.region = region or None
        self.addressing_style = (addressing_style or default_addressing_style(self.endpoint_url)).lower()
        if self.addressing_style not in ADDRESSING_STYLES:
            raise StorageError(
                f"S3_ADDRESSING_STYLE must be one of {', '.join(ADDRESSING_STYLES)}, "
                f"got '{addressing_style}'."
            )
        try:
            self.url_expires = int(url_expires) if url_expires not in (None, "") else DEFAULT_URL_EXPIRES
        except (TypeError, ValueError):
            raise StorageError(f"S3_URL_EXPIRES must be a number of seconds, got '{url_expires}'.")
        self.public_url = public_url.rstrip("/") if public_url else None

        self.allowed_extensions = normalise_extensions(allowed_extensions)
        blocked = normalise_extensions(blocked_extensions)
        self.blocked_extensions = DEFAULT_BLOCKED_EXTENSIONS if blocked is None else blocked

        self.client = client if client is not None else self._build_client(access_key_id, secret_access_key)

    def _build_client(self, access_key_id: Optional[str], secret_access_key: Optional[str]):
        try:
            boto3 = require("boto3", feature="The S3 storage backend")
            botocore_config = require("botocore.config", feature="The S3 storage backend")
        except MissingDependencyError as exc:
            raise MissingS3Dependency(str(exc)) from exc

        options: dict[str, Any] = {
            "signature_version": "s3v4",
            "s3": {"addressing_style": self.addressing_style},
        }
        if self.endpoint_url:
            # boto3 1.36 started sending CRC checksums on every request and
            # validating them on responses. S3-compatible services (Garage,
            # MinIO, Hetzner, R2) reject or mishandle them, so only send and
            # check checksums where the operation requires them.
            options["request_checksum_calculation"] = "when_required"
            options["response_checksum_validation"] = "when_required"

        kwargs: dict[str, Any] = {"config": botocore_config.Config(**options)}
        if self.endpoint_url:
            kwargs["endpoint_url"] = self.endpoint_url
        if self.region:
            kwargs["region_name"] = self.region
        if access_key_id and secret_access_key:
            kwargs["aws_access_key_id"] = access_key_id
            kwargs["aws_secret_access_key"] = secret_access_key
        elif access_key_id or secret_access_key:
            raise StorageError(
                "Set both S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY, or neither to use "
                "the default AWS credential chain."
            )
        return boto3.client("s3", **kwargs)

    # ------------------------------------------------------------------
    # Key safety
    # ------------------------------------------------------------------

    def _key(self, path: Union[str, Path]) -> str:
        """Validate ``path`` and return it as an object key.

        Raises:
            StorageError: If the key is empty, absolute, contains ``.`` or
                ``..`` segments, backslashes or control characters.
        """
        raw = str(path) if path is not None else ""
        if not raw.strip():
            raise StorageError("Invalid storage path: path is empty")
        if raw.startswith("/") or (len(raw) > 1 and raw[1] == ":"):
            raise StorageError(f"Invalid storage path: absolute paths are not allowed: {raw}")
        if "\\" in raw:
            raise StorageError(f"Invalid storage path: backslashes are not allowed: {raw}")
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in raw):
            raise StorageError("Invalid storage path: control characters are not allowed")
        segments = raw.split("/")
        if any(segment in ("", ".", "..") for segment in segments):
            raise StorageError(f"Invalid storage path: empty, '.' or '..' segment: {raw}")
        if len(raw.encode("utf-8")) > 1024:
            raise StorageError("Invalid storage path: keys are limited to 1024 bytes")
        return raw

    def _check_extension(self, key: str) -> None:
        ext = Path(key).suffix.lower().lstrip(".")

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
                "from a domain you control. Set STORAGE_ALLOWED_EXTENSIONS or "
                "STORAGE_BLOCKED_EXTENSIONS to change this."
            )

    def _is_not_found(self, exc: Exception) -> bool:
        return _error_code(exc) in _NOT_FOUND_CODES

    def _url_for(self, key: str, expires_in: Optional[int] = None,
                 download_name: Optional[str] = None, content_type: Optional[str] = None) -> str:
        if self.public_url:
            return f"{self.public_url}/{quote(key)}"
        params: dict[str, Any] = {"Bucket": self.bucket_name, "Key": key}
        if download_name:
            safe = "".join(ch for ch in download_name if ch.isalnum() or ch in " ._-").strip() or "download"
            params["ResponseContentDisposition"] = f'inline; filename="{safe}"'
        if content_type:
            params["ResponseContentType"] = content_type
        return self.client.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=int(expires_in if expires_in is not None else self.url_expires),
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
        """Upload a file to the bucket.

        Args:
            file: File object, bytes, or a local file path.
            path: Object key.
            content_type: MIME type. Guessed from the extension if not given.

        Returns:
            A presigned GET URL, or ``S3_PUBLIC_URL/<key>`` when that is set.

        Raises:
            StorageError: If the key is invalid, the extension is not
                permitted, or the upload fails.
        """
        key = self._key(path)
        self._check_extension(key)
        content_type = content_type or self.get_content_type(key)
        extra = {"ContentType": content_type}

        try:
            if isinstance(file, bytes):
                self.client.put_object(Bucket=self.bucket_name, Key=key, Body=file, **extra)
            elif isinstance(file, (str, Path)):
                source = Path(file)
                if not source.is_file():
                    raise StorageError(f"Source file not found: {file}")
                self.client.upload_file(str(source), self.bucket_name, key, ExtraArgs=extra)
            else:
                self.client.upload_fileobj(file, self.bucket_name, key, ExtraArgs=extra)
            return self._url_for(key)
        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to upload to S3: {e}")

    def download(self, path: str) -> bytes:
        """Download an object's contents.

        Raises:
            StorageError: If the key is invalid, missing, or the read fails.
        """
        key = self._key(path)
        try:
            response = self.client.get_object(Bucket=self.bucket_name, Key=key)
            return response["Body"].read()
        except Exception as e:
            if self._is_not_found(e):
                raise StorageError(f"File not found in S3: {path}")
            raise StorageError(f"Failed to download from S3: {e}")

    def delete(self, path: str) -> bool:
        """Delete an object.

        Returns:
            True if the object was deleted, False if it did not exist.
        """
        key = self._key(path)
        if not self.exists(key):
            return False
        try:
            self.client.delete_object(Bucket=self.bucket_name, Key=key)
            return True
        except Exception as e:
            raise StorageError(f"Failed to delete from S3: {e}")

    def get_url(self, path: str, expires_in: Optional[int] = None,
                download_name: Optional[str] = None, content_type: Optional[str] = None) -> str:
        """URL for an existing object.

        Args:
            path: Object key.
            expires_in: Presigned URL lifetime in seconds. Defaults to
                ``S3_URL_EXPIRES`` (3600). Ignored with ``S3_PUBLIC_URL``.
            download_name: If given, the response carries an inline
                Content-Disposition with this filename (presigned URLs only).
            content_type: Content-Type override for the response
                (presigned URLs only).

        Raises:
            StorageError: If the object does not exist or signing fails.
        """
        key = self._key(path)
        if not self.exists(key):
            raise StorageError(f"File not found in S3: {path}")
        try:
            return self._url_for(key, expires_in, download_name, content_type)
        except Exception as e:
            raise StorageError(f"Failed to generate S3 URL: {e}")

    def exists(self, path: str) -> bool:
        """Whether an object exists.

        Raises:
            StorageError: If the key is invalid, or the check fails for a
                reason other than the object being absent (bad credentials,
                a missing bucket), so those are not mistaken for "not found".
        """
        key = self._key(path)
        try:
            self.client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except Exception as e:
            if self._is_not_found(e):
                return False
            raise StorageError(f"Failed to check S3 object: {e}")


def s3_storage_from_settings(setting, **overrides) -> S3Storage:
    """Build :class:`S3Storage` from a ``setting(key)`` lookup.

    ``setting`` returns the configured value for a key, or ``None``.
    ``get_storage()`` passes one that reads the app config, then the
    environment.
    """
    options = dict(
        bucket_name=setting("S3_BUCKET"),
        endpoint_url=setting("S3_ENDPOINT"),
        region=setting("S3_REGION"),
        access_key_id=setting("S3_ACCESS_KEY_ID"),
        secret_access_key=setting("S3_SECRET_ACCESS_KEY"),
        addressing_style=setting("S3_ADDRESSING_STYLE"),
        url_expires=setting("S3_URL_EXPIRES"),
        public_url=setting("S3_PUBLIC_URL"),
        allowed_extensions=setting("STORAGE_ALLOWED_EXTENSIONS"),
        blocked_extensions=setting("STORAGE_BLOCKED_EXTENSIONS"),
    )
    options.update(overrides)
    return S3Storage(**options)


__all__ = ["S3Storage", "MissingS3Dependency", "DEFAULT_URL_EXPIRES", "s3_storage_from_settings"]
