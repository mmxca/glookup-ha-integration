"""Config flow for Glooko: Home Assistant collects and stores the credentials."""

from __future__ import annotations

from collections.abc import Mapping
import logging
import secrets
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from . import build_client
from .api import GlookoAuthError, GlookoError, GlookoTwoFactorError
from .const import (
    CONF_DEVICE_ID,
    CONF_REGION,
    CONF_SCAN_INTERVAL,
    CONF_SERIAL,
    CONF_STALE_MINUTES,
    CONF_SYNC_TRIGGER,
    DEFAULT_REGION,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STALE_MINUTES,
    DEFAULT_SYNC_TRIGGER,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MAX_SYNC_TRIGGER,
    MIN_SCAN_INTERVAL,
    MIN_SYNC_TRIGGER,
    REGIONS,
)

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): TextSelector(TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
        ),
        vol.Required(CONF_REGION, default=DEFAULT_REGION): SelectSelector(
            SelectSelectorConfig(options=list(REGIONS), mode=SelectSelectorMode.DROPDOWN, translation_key="region")
        ),
    }
)


async def _validate(hass, data: dict[str, Any]) -> tuple[str | None, dict[str, str]]:
    """Try a real sign-in. Returns (glooko_code, errors)."""
    try:
        code = await build_client(hass, data).async_login()
    except GlookoTwoFactorError:
        return None, {"base": "two_factor"}
    except GlookoAuthError:
        return None, {"base": "invalid_auth"}
    except GlookoError:
        return None, {"base": "cannot_connect"}
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Unexpected error validating Glooko credentials")
        return None, {"base": "unknown"}
    return code, {}


class GlookoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Glooko."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {
                **user_input,
                CONF_EMAIL: user_input[CONF_EMAIL].strip(),
                # Stable per-install identity so Glooko sees one device, not a new one each login.
                CONF_DEVICE_ID: secrets.token_hex(8),
                CONF_SERIAL: secrets.token_hex(12),
            }
            code, errors = await _validate(self.hass, data)
            if not errors:
                await self.async_set_unique_id(code)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=f"Glooko ({data[CONF_EMAIL]})", data=data)
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            data = {**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
            code, errors = await _validate(self.hass, data)
            if not errors:
                await self.async_set_unique_id(code)
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]})
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {vol.Required(CONF_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))}
            ),
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return GlookoOptionsFlow()


class GlookoOptionsFlow(OptionsFlow):
    """Polling interval and staleness threshold."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            values = {k: int(v) for k, v in user_input.items()}
            trigger = values.get(CONF_SYNC_TRIGGER, DEFAULT_SYNC_TRIGGER)
            if 0 < trigger < MIN_SYNC_TRIGGER:
                errors[CONF_SYNC_TRIGGER] = "sync_too_frequent"
            else:
                return self.async_create_entry(data=values)
        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): NumberSelector(
                    NumberSelectorConfig(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL, step=1,
                                         unit_of_measurement="min", mode=NumberSelectorMode.BOX)
                ),
                vol.Required(CONF_STALE_MINUTES, default=opts.get(CONF_STALE_MINUTES, DEFAULT_STALE_MINUTES)): NumberSelector(
                    NumberSelectorConfig(min=30, max=1440, step=5, unit_of_measurement="min", mode=NumberSelectorMode.BOX)
                ),
                vol.Required(CONF_SYNC_TRIGGER, default=opts.get(CONF_SYNC_TRIGGER, DEFAULT_SYNC_TRIGGER)): NumberSelector(
                    NumberSelectorConfig(min=0, max=MAX_SYNC_TRIGGER, step=5, unit_of_measurement="min", mode=NumberSelectorMode.BOX)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
