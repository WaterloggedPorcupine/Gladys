import re
from typing import Protocol

_TENANT_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
_SHA256 = re.compile(r"[0-9a-f]{64}")


class InvalidTenantId(ValueError):
    pass


def validate_tenant_id(tenant_id: str) -> str:
    """Allow only ``[A-Za-z0-9_-]{1,64}``, so a tenant ID can never escape a storage root or prefix."""
    # fullmatch, not match + "$": "$" also matches before a trailing newline.
    if not _TENANT_ID.fullmatch(tenant_id):
        raise InvalidTenantId(f"invalid tenant id: {tenant_id!r}")
    return tenant_id


def validate_sha256(digest: str) -> str:
    if not _SHA256.fullmatch(digest):
        raise ValueError("invalid sha256")
    return digest


class BlobStore(Protocol):
    """Content-addressed bytes, partitioned by tenant. Adapters validate IDs with the helpers above."""

    async def put(self, tenant_id: str, content: bytes) -> str: ...
    async def get(self, tenant_id: str, sha256: str) -> bytes: ...
    async def exists(self, tenant_id: str, sha256: str) -> bool: ...
