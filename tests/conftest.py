"""Shared fixtures for the SnoPUD tests."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://my.snopud.com"


def load(name: str) -> str:
    """Return the text of a fixture file."""
    return (FIXTURES / name).read_text()


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock, enable_custom_integrations):
    """Load custom_components/snopud in every test.

    The recorder must start before `hass`, and the integration depends on it.
    """
    return


def mock_login(aioclient_mock, login_body: str = "login_ok.json") -> None:
    """Register the portal responses for a login."""
    aioclient_mock.get(f"{BASE}/", text=load("login_page.html"))
    aioclient_mock.post(f"{BASE}/Home/Login", text=load(login_body))
    aioclient_mock.get(f"{BASE}/Integration/LoginActions", text="<html></html>")
    aioclient_mock.get(f"{BASE}/Dashboard", text=load("dashboard.html"))
