import hashlib

from gladys.ports.blob_store import validate_sha256, validate_tenant_id


class InMemoryBlobStore:
    def __init__(self) -> None:
        self._content: dict[tuple[str, str], bytes] = {}

    async def put(self, tenant_id: str, content: bytes) -> str:
        digest = hashlib.sha256(content).hexdigest()
        self._content.setdefault((validate_tenant_id(tenant_id), digest), content)
        return digest

    async def get(self, tenant_id: str, sha256: str) -> bytes:
        try:
            return self._content[(validate_tenant_id(tenant_id), validate_sha256(sha256))]
        except KeyError as error:
            raise FileNotFoundError(sha256) from error

    async def exists(self, tenant_id: str, sha256: str) -> bool:
        return (validate_tenant_id(tenant_id), validate_sha256(sha256)) in self._content
