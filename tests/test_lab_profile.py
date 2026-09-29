from gladys.domain.lab import LabProfile, MountedPipette, RobotModel


def test_lab_profile_round_trip() -> None:
    profile = LabProfile(
        "lab-1",
        "Main lab",
        RobotModel.OT2,
        (MountedPipette("left", "p300_single_gen2"),),
        ("temperature module",),
        ("plate",),
        ("slot 4 reserved",),
    )
    assert LabProfile.from_dict(profile.to_dict()) == profile
