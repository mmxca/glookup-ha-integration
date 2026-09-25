"""Shared fixtures for Home Assistant tests (pytest-homeassistant-custom-component)."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow loading custom_components/glooko in every HA test."""
    yield
