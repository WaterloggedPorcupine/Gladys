import asyncio
import hashlib
import os
import uuid
from pathlib import Path

from gladys.ports.blob_store import validate_sha256, validate_tenant_id


class FilesystemBlobStore:
    """Layout: ``root/<tenant_id>/<first two hex chars>/<remaining 62>``. Suitable for one node."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, tenant_id: str, digest: str) -> Path:
        validate_sha256(digest)
        return self._root / validate_tenant_id(tenant_id) / digest[:2] / digest[2:]

    async def put(self, tenant_id: str, content: bytes) -> str:
        digest = hashlib.sha256(content).hexdigest()
        path = self._path(tenant_id, digest)

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                return
            # A unique temp name per write: two concurrent puts in one process must not share a temp file.
            temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
            try:
                temporary.write_bytes(content)
                try:
                    os.replace(temporary, path)  # atomic: readers see all of the blob or none of it
                except PermissionError:
                    # Windows refuses to replace a file another writer is replacing at that instant. The name is
                    # the content hash, so if the target now exists it already holds these exact bytes.
                    if not path.is_file():
                        raise
            finally:
                temporary.unlink(missing_ok=True)

        await asyncio.to_thread(write)
        return digest

    async def get(self, tenant_id: str, sha256: str) -> bytes:
        path = self._path(tenant_id, sha256)
        try:
            return await asyncio.to_thread(path.read_bytes)
        except FileNotFoundError as error:
            raise FileNotFoundError(sha256) from error

    async def exists(self, tenant_id: str, sha256: str) -> bool:
        return await asyncio.to_thread(self._path(tenant_id, sha256).is_file)
