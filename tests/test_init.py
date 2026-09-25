"""Home Assistant-level tests. Requires pytest-homeassistant-custom-component."""

import json
import pathlib
from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from homeassistant import config_entries  # noqa: E402
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD  # noqa: E402
from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.data_entry_flow import FlowResultType  # noqa: E402

from custom_components.glooko.api import GlookoAuthError, GlookoTwoFactorError  # noqa: E402
from custom_components.glooko.const import CONF_DEVICE_ID, CONF_REGION, CONF_SERIAL, DOMAIN  # noqa: E402

FIX = json.loads((pathlib.Path(__file__).parent / "fixtures" / "synthetic.json").read_text())
USER = {CONF_EMAIL: "someone@example.com", CONF_PASSWORD: "hunter2", CONF_REGION: "us"}


def _fake_get(path, params=None):
    return {
        "/api/v3/graph/data": FIX["graph"],
        "/api/v3/devices_and_settings": FIX["devices"],
        "/api/v3/cloud_connections": FIX["connections"],
        "/api/v3/graph/statistics/overall": FIX["stats"],
    }[path]


@pytest.fixture
def mock_client():
    with (
        patch("custom_components.glooko.api.GlookoClient.async_login", new=AsyncMock(return_value="blue-test-0001")) as login,
        patch("custom_components.glooko.api.GlookoClient.async_get", new=AsyncMock(side_effect=_fake_get)) as get,
        patch("custom_components.glooko.api.GlookoClient.async_trigger_sync", new=AsyncMock()),
    ):
        yield login, get


async def test_user_flow_creates_entry(hass: HomeAssistant, mock_client):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_EMAIL] == "someone@example.com"
    assert result["data"][CONF_PASSWORD] == "hunter2"
    assert len(result["data"][CONF_DEVICE_ID]) == 16
    assert result["result"].unique_id == "blue-test-0001"


@pytest.mark.parametrize(("exc", "error"), [(GlookoAuthError("x"), "invalid_auth"), (GlookoTwoFactorError("x"), "two_factor")])
async def test_user_flow_errors(hass: HomeAssistant, exc, error):
    with patch("custom_components.glooko.api.GlookoClient.async_login", new=AsyncMock(side_effect=exc)):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_duplicate_account_aborts(hass: HomeAssistant, mock_client):
    MockConfigEntry(domain=DOMAIN, unique_id="blue-test-0001", data={}).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


def _entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="blue-test-0001",
        title="Glooko (someone@example.com)",
        data={**USER, CONF_DEVICE_ID: "a" * 16, CONF_SERIAL: "b" * 24},
    )
    entry.add_to_hass(hass)
    return entry


async def test_setup_creates_entities(hass: HomeAssistant, mock_client):
    await hass.config.async_set_time_zone("America/Chicago")
    entry = _entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is config_entries.ConfigEntryState.LOADED

    states = {s.entity_id: s for s in hass.states.async_all() if s.entity_id.split(".")[1].startswith("glooko")}
    assert len(states) == 20, sorted(states)
    assert hass.states.get("sensor.glooko_pump_mode").state == "automated"
    assert hass.states.get("binary_sensor.glooko_automated_mode").state == "on"
    assert hass.states.get("sensor.glooko_pod_changed").state.startswith("2026-01-14T18:49:38")  # 12:49 CST in UTC
    assert hass.states.get("sensor.glooko_time_in_range_14d").state == "71"
    assert hass.states.get("sensor.glooko_last_bolus").attributes["iob_at_bolus"] == 0.6

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_auth_failure_starts_reauth(hass: HomeAssistant):
    entry = _entry(hass)
    with patch("custom_components.glooko.api.GlookoClient.async_login", new=AsyncMock(side_effect=GlookoAuthError("x"))):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is config_entries.ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == config_entries.SOURCE_REAUTH for f in flows)


async def test_reauth_updates_password(hass: HomeAssistant, mock_client):
    entry = _entry(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    with patch("custom_components.glooko.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PASSWORD: "newpass"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "newpass"
