import hashlib


class InMemoryBlobStore:
    def __init__(self) -> None:
        self._content: dict[str, bytes] = {}

    async def put(self, content: bytes) -> str:
        digest = hashlib.sha256(content).hexdigest()
        self._content.setdefault(digest, content)
        return digest

    async def get(self, sha256: str) -> bytes:
        try:
            return self._content[sha256]
        except KeyError as error:
            raise FileNotFoundError(sha256) from error

    async def exists(self, sha256: str) -> bool:
        return sha256 in self._content
