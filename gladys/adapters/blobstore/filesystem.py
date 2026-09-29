import asyncio
import hashlib
import os
from pathlib import Path


class FilesystemBlobStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, digest: str) -> Path:
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("invalid sha256")
        return self._root / digest[:2] / digest[2:]

    async def put(self, content: bytes) -> str:
        digest = hashlib.sha256(content).hexdigest()
        path = self._path(digest)

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                return
            temporary = path.with_suffix(f".{os.getpid()}.tmp")
            temporary.write_bytes(content)
            temporary.replace(path)

        await asyncio.to_thread(write)
        return digest

    async def get(self, sha256: str) -> bytes:
        try:
            return await asyncio.to_thread(self._path(sha256).read_bytes)
        except FileNotFoundError as error:
            raise FileNotFoundError(sha256) from error

    async def exists(self, sha256: str) -> bool:
        return await asyncio.to_thread(self._path(sha256).is_file)
