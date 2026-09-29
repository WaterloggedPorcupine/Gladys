import asyncio
import hashlib

import pytest

from gladys.ports import BlobStore, InvalidTenantId


class BlobStoreContract:
    """Behavior every ``BlobStore`` adapter must share. Subclasses provide a ``store`` fixture."""

    async def test_put_get_exists_round_trip(self, store: BlobStore) -> None:
        digest = await store.put("tenant-a", b"protocol")
        assert digest == hashlib.sha256(b"protocol").hexdigest()
        assert await store.exists("tenant-a", digest)
        assert await store.get("tenant-a", digest) == b"protocol"
        assert await store.put("tenant-a", b"protocol") == digest

    async def test_missing_blob_raises_file_not_found(self, store: BlobStore) -> None:
        assert not await store.exists("tenant-a", "0" * 64)
        with pytest.raises(FileNotFoundError):
            await store.get("tenant-a", "0" * 64)

    async def test_one_tenant_cannot_see_another_tenants_blob(self, store: BlobStore) -> None:
        digest = await store.put("tenant-a", b"secret protocol")
        assert not await store.exists("tenant-b", digest)
        with pytest.raises(FileNotFoundError):
            await store.get("tenant-b", digest)

    @pytest.mark.parametrize("tenant_id", ["", "../escape", "a/b", r"a\b", "..", "t" * 65, "tenant\n", "tenänt"])
    async def test_invalid_tenant_id_is_rejected(self, store: BlobStore, tenant_id: str) -> None:
        with pytest.raises(InvalidTenantId):
            await store.put(tenant_id, b"x")
        with pytest.raises(InvalidTenantId):
            await store.exists(tenant_id, "0" * 64)
        with pytest.raises(InvalidTenantId):
            await store.get(tenant_id, "0" * 64)

    @pytest.mark.parametrize("digest", ["../escape", "A" * 64, "0" * 63])
    async def test_invalid_digest_is_rejected(self, store: BlobStore, digest: str) -> None:
        with pytest.raises(ValueError):
            await store.exists("tenant-a", digest)

    async def test_concurrent_puts_of_the_same_content_all_succeed(self, store: BlobStore) -> None:
        content = b"same bytes" * 10_000
        digests = await asyncio.gather(*(store.put("tenant-a", content) for _ in range(20)))
        assert set(digests) == {hashlib.sha256(content).hexdigest()}
        assert await store.get("tenant-a", digests[0]) == content
