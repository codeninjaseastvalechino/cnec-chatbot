"""Tests for config/settings.py — Settings.validate() required-key enforcement.

validate() reads instance attributes, so we construct a Settings and override the
attrs directly (class attributes are evaluated once from env at import time).
"""
import pytest

from config.settings import Settings


def _settings_with(**overrides):
    s = Settings()
    # Baseline: everything the validator requires is present.
    s.LINELEADER_USERNAME = "user@codeninjas.com"
    s.LINELEADER_PASSWORD = "pw"
    s.MYSTUDIO_COMPANY_ID = "578"
    s.MYSTUDIO_USER_ID = "9901"
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


class TestValidate:
    def test_passes_when_all_required_present(self):
        _settings_with().validate()  # should not raise

    def test_missing_mystudio_company_id_raises(self):
        with pytest.raises(EnvironmentError) as exc:
            _settings_with(MYSTUDIO_COMPANY_ID="").validate()
        assert "MYSTUDIO_COMPANY_ID" in str(exc.value)

    def test_missing_mystudio_user_id_raises(self):
        with pytest.raises(EnvironmentError) as exc:
            _settings_with(MYSTUDIO_USER_ID="").validate()
        assert "MYSTUDIO_USER_ID" in str(exc.value)

    def test_missing_lineleader_creds_raises(self):
        with pytest.raises(EnvironmentError) as exc:
            _settings_with(LINELEADER_USERNAME="", LINELEADER_PASSWORD="").validate()
        msg = str(exc.value)
        assert "LINELEADER_USERNAME" in msg
        assert "LINELEADER_PASSWORD" in msg

    def test_error_lists_all_missing_keys_together(self):
        with pytest.raises(EnvironmentError) as exc:
            _settings_with(MYSTUDIO_COMPANY_ID="", MYSTUDIO_USER_ID="").validate()
        msg = str(exc.value)
        assert "MYSTUDIO_COMPANY_ID" in msg and "MYSTUDIO_USER_ID" in msg
