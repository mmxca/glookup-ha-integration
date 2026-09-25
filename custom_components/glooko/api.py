"""Minimal, read-only async client for the Glooko web API.

The only non-GET request this client ever sends is the sign-in POST.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import aiohttp

from .const import REGIONS, WEB_ORIGINS

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=45)
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)


class GlookoError(Exception):
    """Base Glooko error."""


class GlookoAuthError(GlookoError):
    """Credentials rejected or session expired."""


class GlookoTwoFactorError(GlookoAuthError):
    """Account requires two-factor authentication (not supported)."""


class GlookoConnectionError(GlookoError):
    """Network / server problem."""


_TOKEN_PATTERNS = (
    re.compile(r'name=["\']authenticity_token["\'][^>]*value=["\']([^"\']+)["\']', re.I),
    re.compile(r'value=["\']([^"\']+)["\'][^>]*name=["\']authenticity_token["\']', re.I),
    re.compile(r'name=["\']csrf-token["\'][^>]*content=["\']([^"\']+)["\']', re.I),
    re.compile(r'content=["\']([^"\']+)["\'][^>]*name=["\']csrf-token["\']', re.I),
)


def authenticity_token(html: str) -> str | None:
    """Extract the Rails CSRF token from the web sign-in page."""
    for pattern in _TOKEN_PATTERNS:
        if match := pattern.search(html or ""):
            return match.group(1)
    return None


class GlookoClient:
    """Async Glooko client bound to one account."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
        region: str,
        device_id: str,
        serial_number: str,
    ) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._base = REGIONS[region]
        origin = WEB_ORIGINS[region]
        self._web = origin
        self._headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "User-Agent": _UA,
            "Origin": origin,
            "Referer": origin + "/",
        }
        self._device_id = device_id
        self._serial = serial_number
        self._cookie: str | None = None
        self.glooko_code: str | None = None
        self._login_lock = asyncio.Lock()

    @staticmethod
    def _session_cookie(resp: aiohttp.ClientResponse) -> str | None:
        """Return 'name=value' pairs from Set-Cookie headers."""
        pairs = [
            raw.split(";", 1)[0]
            for raw in resp.headers.getall("Set-Cookie", [])
            if "=" in raw.split(";", 1)[0]
        ]
        return "; ".join(pairs) or None

    async def _post_json(self, path: str, body: dict[str, Any]) -> tuple[int, Any, str | None]:
        try:
            async with self._session.post(
                self._base + path, json=body, headers=self._headers, timeout=_TIMEOUT
            ) as resp:
                data = await resp.json(content_type=None) if resp.content_length != 0 else None
                return resp.status, data, self._session_cookie(resp)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise GlookoConnectionError(str(err)) from err

    async def async_login(self) -> str:
        """Sign in; return the patient's Glooko code."""
        async with self._login_lock:
            body = {
                "userLogin": {"email": self._email, "password": self._password},
                "deviceInformation": {
                    "applicationType": "logbook",
                    "os": "android",
                    "osVersion": "33",
                    "device": "Home Assistant",
                    "deviceManufacturer": "Home Assistant",
                    "deviceModel": "Home Assistant",
                    "serialNumber": self._serial,
                    "clinicalResearch": False,
                    "deviceId": self._device_id,
                    "applicationVersion": "6.1.3",
                    "buildNumber": "0",
                    "gitHash": "g4fbed2011b",
                },
            }
            status, data, cookie = await self._post_json("/api/v2/users/sign_in", body)
            if status == 422:
                # Some accounts only accept the v3 sign-in.
                status, data, cookie = await self._post_json(
                    "/api/v3/users/sign_in",
                    {"user": {"email": self._email, "password": self._password}},
                )
            if status in (401, 403, 422):
                raise GlookoAuthError(f"sign-in rejected (HTTP {status})")
            if status != 200:
                raise GlookoConnectionError(f"sign-in failed (HTTP {status})")
            data = data or {}
            if data.get("twoFaRequired") or data.get("two_fa_required"):
                raise GlookoTwoFactorError("two-factor authentication is required")
            if not cookie:
                raise GlookoAuthError("sign-in returned no session cookie")
            self._cookie = cookie
            code = (data.get("userLogin") or {}).get("glookoCode")
            if not code:
                profile = await self._get("/api/v3/session/users", None)
                for key in ("currentUser", "currentPatient", "user"):
                    code = code or ((profile or {}).get(key) or {}).get("glookoCode")
            if not code:
                raise GlookoError("could not determine Glooko patient code")
            self.glooko_code = code
            return code

    async def _get(self, path: str, params: Any) -> Any:
        headers = dict(self._headers)
        if self._cookie:
            headers["Cookie"] = self._cookie
        try:
            async with self._session.get(
                self._base + path, params=params, headers=headers, timeout=_TIMEOUT
            ) as resp:
                if resp.status in (401, 403):
                    raise GlookoAuthError(f"HTTP {resp.status} on {path}")
                if resp.status != 200:
                    raise GlookoConnectionError(f"HTTP {resp.status} on {path}")
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise GlookoConnectionError(str(err)) from err

    async def async_get(self, path: str, params: Any = None) -> Any:
        """GET with one transparent re-login on session expiry."""
        if not self._cookie:
            await self.async_login()
        try:
            return await self._get(path, params)
        except GlookoAuthError:
            _LOGGER.debug("Glooko session expired; signing in again")
            await self.async_login()
            return await self._get(path, params)

    async def async_trigger_sync(self) -> None:
        """Sign in through the Glooko *website*.

        Glooko starts an ON_DEMAND pull from connected pump clouds (e.g. Insulet Omnipod 5)
        when a user signs in on the website; the API sign-in used for polling does not.
        This is a sign-in only: nothing in the account is read or changed by it.
        """
        headers = {"User-Agent": _UA, "Accept": "text/html,application/xhtml+xml"}
        try:
            async with self._session.get(
                self._web + "/users/sign_in", params={"locale": "en"}, headers=headers, timeout=_TIMEOUT
            ) as resp:
                if resp.status != 200:
                    raise GlookoConnectionError(f"web sign-in page HTTP {resp.status}")
                html = await resp.text()
                cookie = self._session_cookie(resp)
            token = authenticity_token(html)
            if not token:
                raise GlookoError("web sign-in page had no authenticity token")
            form = {
                "utf8": "\u2713",
                "authenticity_token": token,
                "user[email]": self._email,
                "user[password]": self._password,
                "language": "en",
                "redirect_to": "/",
                "commit": "Log in",
            }
            post_headers = {
                **headers,
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": self._web,
                "Referer": self._web + "/users/sign_in",
            }
            if cookie:
                post_headers["Cookie"] = cookie
            async with self._session.post(
                self._web + "/users/sign_in",
                params={"id": "login_form"},
                data=form,
                headers=post_headers,
                timeout=_TIMEOUT,
                allow_redirects=False,
            ) as resp:
                status, location = resp.status, resp.headers.get("Location", "")
        except (aiohttp.ClientError, TimeoutError) as err:
            raise GlookoConnectionError(str(err)) from err
        if status in (301, 302, 303) and "sign_in" not in location:
            return
        raise GlookoAuthError(f"web sign-in rejected (HTTP {status})")
