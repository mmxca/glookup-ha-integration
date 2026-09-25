"""Tests for the web sign-in sync trigger."""

import copy
import json
import pathlib
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed  # noqa: E402

from homeassistant.config_entries import ConfigEntryState  # noqa: E402
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD  # noqa: E402
from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.data_entry_flow import FlowResultType  # noqa: E402
from homeassistant.util import dt as dt_util  # noqa: E402

from custom_components.glooko.api import GlookoAuthError, GlookoClient, GlookoConnectionError, authenticity_token  # noqa: E402
from custom_components.glooko.const import (  # noqa: E402
    CONF_DEVICE_ID, CONF_REGION, CONF_SCAN_INTERVAL, CONF_SERIAL, CONF_STALE_MINUTES, CONF_SYNC_TRIGGER, DOMAIN,
)

FIX = json.loads((pathlib.Path(__file__).parent / "fixtures" / "synthetic.json").read_text())
WEB = "https://us.my.glooko.com"
SIGNIN_HTML = '<form><input type="hidden" name="authenticity_token" value="tok123" autocomplete="off"></form>'


def _connections(sync_state):
    conns = copy.deepcopy(FIX["connections"])
    for c in conns:
        if c["integration"] == "INSULET_OMNIPOD_5_CLOUD":
            c["syncState"] = sync_state
    return conns


def _getter(sync_state):
    def _get(path, params=None):
        return {
            "/api/v3/graph/data": FIX["graph"],
            "/api/v3/devices_and_settings": FIX["devices"],
            "/api/v3/cloud_connections": _connections(sync_state),
            "/api/v3/graph/statistics/overall": FIX["stats"],
        }[path]
    return _get


def _entry(hass, **options):
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="blue-test-0001", title="Glooko",
        data={CONF_EMAIL: "someone@example.com", CONF_PASSWORD: "hunter2", CONF_REGION: "us", CONF_DEVICE_ID: "a" * 16, CONF_SERIAL: "b" * 24},
        options=options,
    )
    entry.add_to_hass(hass)
    return entry


# ---------- api ----------

def test_authenticity_token_both_attribute_orders():
    assert authenticity_token(SIGNIN_HTML) == "tok123"
    assert authenticity_token('<input value="abc" name="authenticity_token">') == "abc"
    assert authenticity_token('<meta name="csrf-token" content="meta1">') == "meta1"
    assert authenticity_token("<html></html>") is None


async def test_trigger_sync_posts_form_and_accepts_redirect(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(f"{WEB}/users/sign_in", text=SIGNIN_HTML, headers={"Set-Cookie": "_logbook-web_session=pre; path=/"})
    aioclient_mock.post(f"{WEB}/users/sign_in", status=302, headers={"Location": f"{WEB}/"})
    session = aioclient_mock.create_session(hass.loop)
    client = GlookoClient(session, "someone@example.com", "hunter2", "us", "d" * 16, "s" * 24)
    await client.async_trigger_sync()
    method, url, data, headers = aioclient_mock.mock_calls[-1]
    assert method == "POST"
    assert url.query["id"] == "login_form"
    assert data["authenticity_token"] == "tok123"
    assert data["user[email]"] == "someone@example.com"
    assert headers["Cookie"] == "_logbook-web_session=pre"
    await session.close()


async def test_trigger_sync_rejected_when_redirected_back_to_sign_in(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(f"{WEB}/users/sign_in", text=SIGNIN_HTML)
    aioclient_mock.post(f"{WEB}/users/sign_in", status=302, headers={"Location": f"{WEB}/users/sign_in"})
    session = aioclient_mock.create_session(hass.loop)
    client = GlookoClient(session, "x@example.com", "bad", "us", "d" * 16, "s" * 24)
    with pytest.raises(GlookoAuthError):
        await client.async_trigger_sync()
    await session.close()


async def test_trigger_sync_page_error(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(f"{WEB}/users/sign_in", status=503)
    session = aioclient_mock.create_session(hass.loop)
    client = GlookoClient(session, "x@example.com", "pw", "us", "d" * 16, "s" * 24)
    with pytest.raises(GlookoConnectionError):
        await client.async_trigger_sync()
    await session.close()


# ---------- coordinator ----------

@pytest.fixture
def patch_client():
    def _make(sync_state="SYNC_ALLOWED", trigger_side_effect=None):
        login = patch("custom_components.glooko.api.GlookoClient.async_login", new=AsyncMock(return_value="blue-test-0001"))
        get = patch("custom_components.glooko.api.GlookoClient.async_get", new=AsyncMock(side_effect=_getter(sync_state)))
        trig = patch("custom_components.glooko.api.GlookoClient.async_trigger_sync", new=AsyncMock(side_effect=trigger_side_effect))
        return login, get, trig
    return _make


async def test_triggers_when_sync_allowed_and_refreshes_later(hass: HomeAssistant, patch_client):
    login, get, trig = patch_client("SYNC_ALLOWED")
    with login, get as g, trig as t:
        entry = _entry(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert t.await_count == 1
        calls_before = g.await_count
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=95))
        await hass.async_block_till_done()
        assert g.await_count > calls_before  # delayed re-poll happened
        assert t.await_count == 1  # but no second trigger inside the interval
        attrs = hass.states.get("sensor.glooko_last_glooko_sync").attributes
        assert attrs["sync_trigger_result"] == "ok"
        assert attrs["sync_state"] == "SYNC_ALLOWED"
        assert attrs["last_sync_trigger"]
        await hass.config_entries.async_unload(entry.entry_id)


async def test_no_trigger_during_cooldown(hass: HomeAssistant, patch_client):
    login, get, trig = patch_client("ALREADY_SYNCED")
    with login, get, trig as t:
        entry = _entry(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert t.await_count == 0
        await hass.config_entries.async_unload(entry.entry_id)


async def test_trigger_disabled_by_option(hass: HomeAssistant, patch_client):
    login, get, trig = patch_client("SYNC_ALLOWED")
    with login, get, trig as t:
        entry = _entry(hass, **{CONF_SYNC_TRIGGER: 0})
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert t.await_count == 0
        await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("exc", [GlookoConnectionError("boom"), RuntimeError("unexpected")])
async def test_trigger_failure_does_not_break_update(hass: HomeAssistant, patch_client, caplog, exc):
    login, get, trig = patch_client("SYNC_ALLOWED", trigger_side_effect=exc)
    with login, get, trig as t:
        entry = _entry(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
        assert t.await_count == 1
        assert hass.states.get("sensor.glooko_pump_mode").state == "automated"
        assert hass.states.get("sensor.glooko_last_glooko_sync").attributes["sync_trigger_result"].startswith("failed")
        assert "sync trigger failed" in caplog.text
        await hass.config_entries.async_unload(entry.entry_id)


# ---------- options ----------

async def test_options_validate_sync_interval(hass: HomeAssistant, patch_client):
    login, get, trig = patch_client("ALREADY_SYNCED")
    with login, get, trig:
        entry = _entry(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        result = await hass.config_entries.options.async_init(entry.entry_id)
        base = {CONF_SCAN_INTERVAL: 10, CONF_STALE_MINUTES: 120}
        result = await hass.config_entries.options.async_configure(result["flow_id"], {**base, CONF_SYNC_TRIGGER: 10})
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {CONF_SYNC_TRIGGER: "sync_too_frequent"}
        result = await hass.config_entries.options.async_configure(result["flow_id"], {**base, CONF_SYNC_TRIGGER: 15})
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert entry.options[CONF_SYNC_TRIGGER] == 15
        await hass.async_block_till_done()
        await hass.config_entries.async_unload(entry.entry_id)
