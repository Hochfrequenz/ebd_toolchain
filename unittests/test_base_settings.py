# mypy: disable-error-code="call-arg"
import pytest
from _pytest.monkeypatch import MonkeyPatch
from pydantic import ValidationError

from ebd_toolchain.main import Settings


def test_settings_from_env(monkeypatch: MonkeyPatch) -> None:
    # Mock environment variables to simulate the .env behavior
    monkeypatch.setenv("KROKI_PORT", "8000")
    monkeypatch.setenv("KROKI_HOST", "localhost")

    # Instantiate the Settings class
    settings = Settings()

    # Assert the settings have loaded correctly from environment
    assert settings.kroki_port == 8000
    assert settings.kroki_host == "localhost"


def test_settings_missing_required_fields(monkeypatch: MonkeyPatch) -> None:
    # Ensure no environment variables are set
    monkeypatch.delenv("KROKI_PORT", raising=False)
    monkeypatch.delenv("KROKI_HOST", raising=False)

    # Expecting ValidationError due to missing required environment variables
    with pytest.raises(ValidationError):
        Settings(_env_file="foo.env")  # change env file to avoid loading from .env


def test_invalid_port_value(monkeypatch: MonkeyPatch) -> None:
    # Set invalid environment variables
    monkeypatch.setenv("KROKI_PORT", "not_an_integer")
    monkeypatch.setenv("KROKI_HOST", "localhost")

    # Expecting ValidationError because KROKI_PORT is not a valid integer
    with pytest.raises(ValidationError):
        Settings()
