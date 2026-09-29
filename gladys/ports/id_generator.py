from typing import Protocol


class IdGenerator(Protocol):
    def new_id(self) -> str: ...
