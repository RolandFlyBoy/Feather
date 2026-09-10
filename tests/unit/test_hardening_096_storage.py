"""0.9.6 hardening: LocalStorage path traversal and upload extension blocking.

Every public LocalStorage method takes a caller-supplied path. Before 0.9.6
``self.upload_path / path`` was never normalised, so ``../x`` and absolute
paths escaped the upload directory. Uploaded ``.html``/``.svg`` files were
also served from the app origin with a script-capable content type.
"""

import io
import tempfile
from pathlib import Path

import pytest

from feather.exceptions import StorageError
from feather.storage.local import LocalStorage

pytestmark = pytest.mark.unit


@pytest.fixture
def static_dir():
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def storage(static_dir):
    return LocalStorage(static_dir, upload_dir="uploads")


TRAVERSAL_PATHS = [
    "../escape.txt",
    "../../escape.txt",
    "images/../../escape.txt",
    "images/../../../escape.txt",
    "/etc/passwd",
    "/tmp/escape.txt",
]


class TestPathTraversal:
    """Every method must refuse paths that resolve outside the upload dir."""

    @pytest.mark.parametrize("path", TRAVERSAL_PATHS)
    def test_upload_rejects_traversal(self, storage, static_dir, path):
        with pytest.raises(StorageError):
            storage.upload(b"payload", path)

        # Nothing was written outside uploads/
        assert not (static_dir / "escape.txt").exists()
        assert not (static_dir.parent / "escape.txt").exists()

    @pytest.mark.parametrize("path", TRAVERSAL_PATHS)
    def test_download_rejects_traversal(self, storage, static_dir, path):
        (static_dir / "escape.txt").write_bytes(b"secret")
        with pytest.raises(StorageError):
            storage.download(path)

    @pytest.mark.parametrize("path", TRAVERSAL_PATHS)
    def test_delete_rejects_traversal(self, storage, static_dir, path):
        outside = static_dir / "escape.txt"
        outside.write_bytes(b"keep me")
        with pytest.raises(StorageError):
            storage.delete(path)
        assert outside.exists()

    @pytest.mark.parametrize("path", TRAVERSAL_PATHS)
    def test_exists_rejects_traversal(self, storage, static_dir, path):
        (static_dir / "escape.txt").write_bytes(b"x")
        with pytest.raises(StorageError):
            storage.exists(path)

    @pytest.mark.parametrize("path", TRAVERSAL_PATHS)
    def test_get_url_rejects_traversal(self, storage, static_dir, path):
        (static_dir / "escape.txt").write_bytes(b"x")
        with pytest.raises(StorageError):
            storage.get_url(path)

    def test_empty_and_dot_paths_rejected(self, storage):
        for path in ("", ".", "./", "images/.."):
            with pytest.raises(StorageError):
                storage.upload(b"x", path)

    def test_symlink_escape_rejected(self, storage, static_dir):
        outside = static_dir.parent / "outside-target"
        outside.mkdir(exist_ok=True)
        link = storage.upload_path / "link"
        link.symlink_to(outside, target_is_directory=True)
        try:
            with pytest.raises(StorageError):
                storage.upload(b"x", "link/escape.txt")
            assert not (outside / "escape.txt").exists()
        finally:
            link.unlink()
            for child in outside.iterdir():
                child.unlink()
            outside.rmdir()

    def test_nested_paths_still_work(self, storage):
        """Legitimate nested paths and dot segments that stay inside are fine."""
        url = storage.upload(b"data", "images/avatars/./user1.jpg")
        assert url == "/static/uploads/images/avatars/user1.jpg"
        assert storage.exists("images/avatars/user1.jpg")
        assert storage.download("images/avatars/user1.jpg") == b"data"
        assert storage.get_url("images/avatars/user1.jpg") == "/static/uploads/images/avatars/user1.jpg"
        assert storage.delete("images/avatars/user1.jpg") is True

    def test_returned_url_is_normalised(self, storage):
        url = storage.upload(b"data", "images//photo.jpg")
        assert url == "/static/uploads/images/photo.jpg"


class TestExtensionBlocking:
    """Script-capable file types are blocked by default under static/."""

    @pytest.mark.parametrize(
        "name",
        [
            "page.html", "page.HTML", "page.htm", "image.svg", "doc.xhtml",
            "data.xml", "script.js", "module.mjs", "shell.php", "shell.phtml",
        ],
    )
    def test_default_block_list(self, storage, name):
        with pytest.raises(StorageError) as exc_info:
            storage.upload(b"<svg onload=alert(1)>", name)
        assert "extension" in str(exc_info.value).lower()
        assert not storage.upload_path.joinpath(name).exists()

    def test_block_applies_to_nested_paths_and_file_objects(self, storage):
        with pytest.raises(StorageError):
            storage.upload(io.BytesIO(b"<html>"), "pages/index.html")

    @pytest.mark.parametrize("name", ["photo.jpg", "photo.png", "doc.pdf", "notes.txt", "README"])
    def test_safe_extensions_allowed(self, storage, name):
        assert storage.upload(b"ok", name) == f"/static/uploads/{name}"

    def test_custom_block_list_replaces_default(self, static_dir):
        storage = LocalStorage(static_dir, blocked_extensions=["exe"])
        # svg is no longer blocked, exe is
        storage.upload(b"<svg/>", "logo.svg")
        with pytest.raises(StorageError):
            storage.upload(b"MZ", "setup.exe")

    def test_allow_list_restricts_uploads(self, static_dir):
        storage = LocalStorage(static_dir, allowed_extensions=["jpg", ".png", "SVG"])
        storage.upload(b"x", "a.jpg")
        storage.upload(b"x", "b.PNG")
        storage.upload(b"x", "c.svg")  # explicitly allowed wins over the default block
        with pytest.raises(StorageError):
            storage.upload(b"x", "d.gif")
        with pytest.raises(StorageError):
            storage.upload(b"x", "e.html")

    def test_comma_separated_strings_accepted(self, static_dir):
        storage = LocalStorage(static_dir, blocked_extensions="html, js")
        storage.upload(b"<svg/>", "logo.svg")
        with pytest.raises(StorageError):
            storage.upload(b"x", "a.js")

    def test_get_storage_reads_config(self, static_dir):
        from tests.conftest import feather_app
        from feather.storage import get_storage

        with feather_app(
            STORAGE_BACKEND="local",
            STORAGE_ALLOWED_EXTENSIONS="jpg,svg",
        ) as app:
            app.static_folder = str(static_dir)
            with app.app_context():
                storage = get_storage()
                storage.upload(b"x", "ok.svg")
                with pytest.raises(StorageError):
                    storage.upload(b"x", "no.png")

        with feather_app(
            STORAGE_BACKEND="local",
            STORAGE_BLOCKED_EXTENSIONS="exe",
        ) as app:
            app.static_folder = str(static_dir)
            with app.app_context():
                storage = get_storage()
                storage.upload(b"x", "allowed-now.html")
                with pytest.raises(StorageError):
                    storage.upload(b"x", "no.exe")

    def test_get_storage_default_blocks_html(self, static_dir):
        from tests.conftest import feather_app
        from feather.storage import get_storage

        with feather_app(STORAGE_BACKEND="local") as app:
            app.static_folder = str(static_dir)
            with app.app_context():
                with pytest.raises(StorageError):
                    get_storage().upload(b"x", "x.html")
