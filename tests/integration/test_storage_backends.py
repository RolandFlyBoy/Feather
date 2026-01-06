"""Integration tests for storage backends.

Tests the local filesystem storage backend to ensure file operations
work correctly. GCS backend tests use mocks to avoid cloud dependencies.
"""

import io
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from feather.storage.local import LocalStorage
from feather.exceptions import StorageError


pytestmark = pytest.mark.integration


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_storage():
    """Create a temporary storage directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = LocalStorage(temp_dir, upload_dir='uploads')
        yield storage


@pytest.fixture
def sample_content():
    """Sample file content for testing."""
    return b'Hello, World! This is test content.'


# =============================================================================
# Test LocalStorage Upload
# =============================================================================

class TestLocalStorageUpload:
    """Tests for LocalStorage.upload()."""

    def test_upload_from_bytes(self, temp_storage, sample_content):
        """Upload from raw bytes."""
        url = temp_storage.upload(sample_content, 'test.txt')

        assert url == '/static/uploads/test.txt'
        assert temp_storage.exists('test.txt')

    def test_upload_from_file_object(self, temp_storage, sample_content):
        """Upload from file-like object."""
        file_obj = io.BytesIO(sample_content)
        url = temp_storage.upload(file_obj, 'test.txt')

        assert url == '/static/uploads/test.txt'
        assert temp_storage.exists('test.txt')

    def test_upload_from_path(self, temp_storage, sample_content):
        """Upload from Path object."""
        # Create a source file
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(sample_content)
            source_path = Path(f.name)

        try:
            url = temp_storage.upload(source_path, 'test.txt')
            assert url == '/static/uploads/test.txt'
            assert temp_storage.exists('test.txt')
        finally:
            source_path.unlink()

    def test_upload_from_string_path(self, temp_storage, sample_content):
        """Upload from string path."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(sample_content)
            source_path = f.name

        try:
            url = temp_storage.upload(source_path, 'test.txt')
            assert url == '/static/uploads/test.txt'
            assert temp_storage.exists('test.txt')
        finally:
            Path(source_path).unlink()

    def test_upload_creates_subdirectories(self, temp_storage, sample_content):
        """Upload creates nested directories."""
        url = temp_storage.upload(sample_content, 'images/avatars/user1.jpg')

        assert url == '/static/uploads/images/avatars/user1.jpg'
        assert temp_storage.exists('images/avatars/user1.jpg')

    def test_upload_overwrites_existing(self, temp_storage):
        """Upload overwrites existing file."""
        temp_storage.upload(b'original content', 'test.txt')
        temp_storage.upload(b'new content', 'test.txt')

        content = temp_storage.download('test.txt')
        assert content == b'new content'

    def test_upload_raises_for_missing_source(self, temp_storage):
        """Upload raises StorageError for missing source file."""
        with pytest.raises(StorageError) as exc_info:
            temp_storage.upload('/nonexistent/file.txt', 'test.txt')

        assert 'not found' in str(exc_info.value).lower()


# =============================================================================
# Test LocalStorage Download
# =============================================================================

class TestLocalStorageDownload:
    """Tests for LocalStorage.download()."""

    def test_download_returns_content(self, temp_storage, sample_content):
        """Download returns file contents as bytes."""
        temp_storage.upload(sample_content, 'test.txt')
        content = temp_storage.download('test.txt')

        assert content == sample_content
        assert isinstance(content, bytes)

    def test_download_raises_for_missing_file(self, temp_storage):
        """Download raises StorageError for missing file."""
        with pytest.raises(StorageError) as exc_info:
            temp_storage.download('nonexistent.txt')

        assert 'not found' in str(exc_info.value).lower()

    def test_download_from_subdirectory(self, temp_storage, sample_content):
        """Download works for files in subdirectories."""
        temp_storage.upload(sample_content, 'data/file.txt')
        content = temp_storage.download('data/file.txt')

        assert content == sample_content


# =============================================================================
# Test LocalStorage Delete
# =============================================================================

class TestLocalStorageDelete:
    """Tests for LocalStorage.delete()."""

    def test_delete_removes_file(self, temp_storage, sample_content):
        """Delete removes the file."""
        temp_storage.upload(sample_content, 'test.txt')
        assert temp_storage.exists('test.txt')

        result = temp_storage.delete('test.txt')

        assert result is True
        assert not temp_storage.exists('test.txt')

    def test_delete_returns_false_for_missing(self, temp_storage):
        """Delete returns False for non-existent file."""
        result = temp_storage.delete('nonexistent.txt')
        assert result is False

    def test_delete_from_subdirectory(self, temp_storage, sample_content):
        """Delete works for files in subdirectories."""
        temp_storage.upload(sample_content, 'data/file.txt')

        result = temp_storage.delete('data/file.txt')

        assert result is True
        assert not temp_storage.exists('data/file.txt')


# =============================================================================
# Test LocalStorage Exists
# =============================================================================

class TestLocalStorageExists:
    """Tests for LocalStorage.exists()."""

    def test_exists_returns_true_for_existing(self, temp_storage, sample_content):
        """Exists returns True for existing file."""
        temp_storage.upload(sample_content, 'test.txt')
        assert temp_storage.exists('test.txt') is True

    def test_exists_returns_false_for_missing(self, temp_storage):
        """Exists returns False for non-existent file."""
        assert temp_storage.exists('nonexistent.txt') is False

    def test_exists_works_with_subdirectories(self, temp_storage, sample_content):
        """Exists works for files in subdirectories."""
        temp_storage.upload(sample_content, 'data/file.txt')

        assert temp_storage.exists('data/file.txt') is True
        assert temp_storage.exists('data/other.txt') is False


# =============================================================================
# Test LocalStorage GetUrl
# =============================================================================

class TestLocalStorageGetUrl:
    """Tests for LocalStorage.get_url()."""

    def test_get_url_returns_static_path(self, temp_storage, sample_content):
        """get_url returns correct static path."""
        temp_storage.upload(sample_content, 'test.txt')
        url = temp_storage.get_url('test.txt')

        assert url == '/static/uploads/test.txt'

    def test_get_url_raises_for_missing(self, temp_storage):
        """get_url raises StorageError for missing file."""
        with pytest.raises(StorageError) as exc_info:
            temp_storage.get_url('nonexistent.txt')

        assert 'not found' in str(exc_info.value).lower()

    def test_get_url_ignores_expires_in(self, temp_storage, sample_content):
        """get_url ignores expires_in for local storage."""
        temp_storage.upload(sample_content, 'test.txt')

        # Both should return the same URL
        url1 = temp_storage.get_url('test.txt', expires_in=60)
        url2 = temp_storage.get_url('test.txt', expires_in=86400)

        assert url1 == url2 == '/static/uploads/test.txt'

    def test_get_url_works_with_subdirectories(self, temp_storage, sample_content):
        """get_url returns correct path for subdirectories."""
        temp_storage.upload(sample_content, 'images/photo.jpg')
        url = temp_storage.get_url('images/photo.jpg')

        assert url == '/static/uploads/images/photo.jpg'


# =============================================================================
# Test Content Type Detection
# =============================================================================

class TestContentTypeDetection:
    """Tests for content type detection."""

    def test_detect_image_jpeg(self, temp_storage):
        """Detects JPEG content type."""
        content_type = temp_storage.get_content_type('photo.jpg')
        assert content_type == 'image/jpeg'

    def test_detect_image_png(self, temp_storage):
        """Detects PNG content type."""
        content_type = temp_storage.get_content_type('image.png')
        assert content_type == 'image/png'

    def test_detect_text_plain(self, temp_storage):
        """Detects plain text content type."""
        content_type = temp_storage.get_content_type('readme.txt')
        assert content_type == 'text/plain'

    def test_detect_json(self, temp_storage):
        """Detects JSON content type."""
        content_type = temp_storage.get_content_type('data.json')
        assert content_type == 'application/json'

    def test_detect_pdf(self, temp_storage):
        """Detects PDF content type."""
        content_type = temp_storage.get_content_type('document.pdf')
        assert content_type == 'application/pdf'

    def test_unknown_extension_returns_octet_stream(self, temp_storage):
        """Unknown extensions return application/octet-stream."""
        content_type = temp_storage.get_content_type('file.xyz123')
        assert content_type == 'application/octet-stream'


# =============================================================================
# Test GCS Storage Class
# =============================================================================

class TestGCSStorageClass:
    """Tests that GCSStorage class exists and follows interface."""

    def test_gcs_storage_is_importable(self):
        """GCSStorage class is importable."""
        from feather.storage.gcs import GCSStorage
        assert GCSStorage is not None

    def test_gcs_storage_extends_storage_backend(self):
        """GCSStorage extends StorageBackend."""
        from feather.storage.gcs import GCSStorage
        from feather.storage.base import StorageBackend

        assert issubclass(GCSStorage, StorageBackend)

    def test_gcs_storage_has_required_methods(self):
        """GCSStorage has all required interface methods."""
        from feather.storage.gcs import GCSStorage

        required_methods = ['upload', 'download', 'delete', 'get_url', 'exists']
        for method in required_methods:
            assert hasattr(GCSStorage, method), f"GCSStorage missing {method}"


# =============================================================================
# Test get_storage Factory
# =============================================================================

class TestGetStorageFactory:
    """Tests for the get_storage factory function."""

    def test_get_storage_returns_local_by_default(self):
        """get_storage returns LocalStorage when STORAGE_BACKEND is 'local'."""
        from tests.conftest import feather_app

        with feather_app(STORAGE_BACKEND='local') as app:
            with app.app_context():
                from feather.storage import get_storage
                storage = get_storage()

                assert isinstance(storage, LocalStorage)

    def test_get_storage_uses_static_folder(self):
        """get_storage uses app's static folder."""
        from tests.conftest import feather_app

        with feather_app(STORAGE_BACKEND='local') as app:
            with app.app_context():
                from feather.storage import get_storage
                storage = get_storage()

                assert storage.static_folder == Path(app.static_folder)
