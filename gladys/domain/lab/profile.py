from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import cast


class RobotModel(StrEnum):
    OT2 = "OT-2"
    FLEX = "Flex"


@dataclass(frozen=True)
class MountedPipette:
    mount: str
    model: str

    def to_dict(self) -> dict[str, str]:
        return {"mount": self.mount, "model": self.model}

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> MountedPipette:
        return cls(str(data["mount"]), str(data["model"]))


@dataclass(frozen=True)
class LabProfile:
    profile_id: str
    name: str
    robot_model: RobotModel
    mounted_pipettes: tuple[MountedPipette, ...] = ()
    modules: tuple[str, ...] = ()
    allowed_labware: tuple[str, ...] = ()
    deck_constraints: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "name": self.name,
            "robot_model": self.robot_model.value,
            "mounted_pipettes": [p.to_dict() for p in self.mounted_pipettes],
            "modules": list(self.modules),
            "allowed_labware": list(self.allowed_labware),
            "deck_constraints": list(self.deck_constraints),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> LabProfile:
        pipettes = cast(list[dict[str, object]], data.get("mounted_pipettes", []))
        return cls(
            str(data["profile_id"]),
            str(data["name"]),
            RobotModel(str(data["robot_model"])),
            tuple(MountedPipette.from_dict(p) for p in pipettes),
            tuple(map(str, cast(list[object], data.get("modules", [])))),
            tuple(map(str, cast(list[object], data.get("allowed_labware", [])))),
            tuple(map(str, cast(list[object], data.get("deck_constraints", [])))),
        )
