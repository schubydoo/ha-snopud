"""Tests for the config flow."""

from unittest.mock import patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.snopud.api import (
    CannotConnect,
    ExtraLoginStep,
    InvalidAuth,
    PortalError,
)
from custom_components.snopud.const import DOMAIN

LOGIN = "custom_components.snopud.config_flow.SnoPUDClient.async_login"
USER = {CONF_USERNAME: " User@Example.com ", CONF_PASSWORD: "pw"}


async def test_user_flow(hass: HomeAssistant) -> None:
    """A good login creates the entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    with (
        patch(LOGIN) as login,
        patch("custom_components.snopud.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert login.call_count == 1
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "User@Example.com"
    assert result["data"] == {CONF_USERNAME: "User@Example.com", CONF_PASSWORD: "pw"}
    assert result["result"].unique_id == "user@example.com"


@pytest.mark.parametrize(
    ("error", "key"),
    [
        (InvalidAuth, "invalid_auth"),
        (ExtraLoginStep, "extra_login_step"),
        (CannotConnect, "cannot_connect"),
        (PortalError, "unexpected_page"),
        (ValueError, "unknown"),
    ],
)
async def test_user_flow_errors(hass: HomeAssistant, error, key) -> None:
    """Each failure shows its own message, and the user can retry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    with patch(LOGIN, side_effect=error):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": key}
    with (
        patch(LOGIN),
        patch("custom_components.snopud.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_already_configured(hass: HomeAssistant) -> None:
    """The same email cannot be added twice."""
    MockConfigEntry(domain=DOMAIN, unique_id="user@example.com").add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(hass: HomeAssistant) -> None:
    """Reauthentication stores the new password."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="user@example.com",
        data={CONF_USERNAME: "user@example.com", CONF_PASSWORD: "old"},
    )
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    with patch(LOGIN, side_effect=InvalidAuth):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "still-wrong"}
        )
    assert result["errors"] == {"base": "invalid_auth"}
    with (
        patch(LOGIN),
        patch("custom_components.snopud.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "new"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "new"
