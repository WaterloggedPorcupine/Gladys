from collections.abc import Callable
from pathlib import Path

import pytest

from gladys.adapters.blobstore import FilesystemBlobStore, InMemoryBlobStore
from gladys.ports import BlobStore


async def blob_contract(store: BlobStore) -> None:
    digest = await store.put(b"protocol")
    assert len(digest) == 64
    assert await store.exists(digest)
    assert await store.get(digest) == b"protocol"
    assert await store.put(b"protocol") == digest
    with pytest.raises(FileNotFoundError):
        await store.get("0" * 64)


@pytest.mark.parametrize("factory", [InMemoryBlobStore])
async def test_memory_blob_contract(factory: Callable[[], BlobStore]) -> None:
    await blob_contract(factory())


async def test_filesystem_blob_contract(tmp_path: Path) -> None:
    await blob_contract(FilesystemBlobStore(tmp_path))


async def test_filesystem_rejects_invalid_digest(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        await FilesystemBlobStore(tmp_path).exists("../escape")
