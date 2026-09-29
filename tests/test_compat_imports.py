import gladys.domain.records as records
import gladys.domain.validity as validity
import gladys.records as legacy_records
import gladys.validity as legacy_validity


def test_legacy_import_paths_re_export_the_domain_api() -> None:
    assert legacy_records.RunRecord is records.RunRecord
    assert set(legacy_records.__all__) == set(records.__all__)
    assert legacy_validity.ValidationResult is validity.ValidationResult is records.ValidationResult
