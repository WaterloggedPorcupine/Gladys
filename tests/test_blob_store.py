import os
from pathlib import Path

import pytest

from gladys.adapters.blobstore import FilesystemBlobStore, InMemoryBlobStore
from tests.contracts.blob_store import BlobStoreContract


class TestInMemoryBlobStore(BlobStoreContract):
    @pytest.fixture
    def store(self) -> InMemoryBlobStore:
        return InMemoryBlobStore()


class TestFilesystemBlobStore(BlobStoreContract):
    @pytest.fixture
    def store(self, tmp_path: Path) -> FilesystemBlobStore:
        return FilesystemBlobStore(tmp_path)

    async def test_layout_is_root_tenant_prefix_rest(self, store: FilesystemBlobStore, tmp_path: Path) -> None:
        digest = await store.put("tenant-a", b"protocol")
        assert (tmp_path / "tenant-a" / digest[:2] / digest[2:]).read_bytes() == b"protocol"
        assert not list(tmp_path.rglob("*.tmp"))

    async def test_replace_losing_a_race_to_an_identical_blob_succeeds(
        self, store: FilesystemBlobStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def racing_replace(source: Path, target: Path) -> None:
            Path(target).write_bytes(b"protocol")  # another writer got there first
            raise PermissionError("in use")

        monkeypatch.setattr(os, "replace", racing_replace)
        digest = await store.put("tenant-a", b"protocol")
        assert await store.get("tenant-a", digest) == b"protocol"
        assert not list(tmp_path.rglob("*.tmp"))

    async def test_replace_permission_error_without_a_winner_is_raised(
        self, store: FilesystemBlobStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def denied(source: Path, target: Path) -> None:
            raise PermissionError("denied")

        monkeypatch.setattr(os, "replace", denied)
        with pytest.raises(PermissionError):
            await store.put("tenant-a", b"protocol")
        assert not list(tmp_path.rglob("*.tmp"))
