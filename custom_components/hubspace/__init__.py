"""Hubspace integration."""

import logging
from pathlib import Path

from aioafero import InvalidAuth
from aioafero.v1 import AferoBridgeV1
from homeassistant.components.frontend import (
    async_register_built_in_panel,
    async_remove_panel,
)
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_TIMEOUT, CONF_TOKEN, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client, device_registry as dr

from .bridge import HubspaceBridge
from .const import (
    CONF_CLIENT,
    DEFAULT_CLIENT,
    DEFAULT_POLLING_INTERVAL_SEC,
    DEFAULT_TIMEOUT,
    DOMAIN,
    POLLING_TIME_STR,
)
from .services import async_register_services

_LOGGER = logging.getLogger(__name__)

PANEL_URL_PATH = "hubspace-freezers"
PANEL_TITLE = "Hubspace Freezers"
PANEL_ICON = "mdi:snowflake"
PANEL_ELEMENT = "hubspace-freezer-panel"
PANEL_STATIC_URL = "/hubspace_panel/hubspace-panel.js"
PANEL_DATA_KEY = f"{DOMAIN}_panel"


async def _async_register_panel(hass: HomeAssistant) -> bool:
    """Register the Hubspace freezer control panel."""
    panel_file = Path(__file__).resolve().parent / "frontend" / "hubspace-panel.js"
    panel_data = hass.data.setdefault(PANEL_DATA_KEY, {})
    if hass.http is None:
        _LOGGER.debug("Skipping Hubspace freezer panel registration; HTTP not ready")
        return False
    if not panel_data.get("static_registered"):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(PANEL_STATIC_URL, str(panel_file), cache_headers=False)]
        )
        panel_data["static_registered"] = True
    async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        frontend_url_path=PANEL_URL_PATH,
        config={
            "_panel_custom": {
                "name": PANEL_ELEMENT,
                "module_url": PANEL_STATIC_URL,
                "embed_iframe": False,
                "trust_external": True,
            },
            "title": PANEL_TITLE,
        },
        require_admin=False,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Hubspace as config entry."""
    bridge = HubspaceBridge(hass, entry)
    if not await bridge.async_initialize_bridge():
        return False

    async_register_services(hass)
    panel_data = hass.data.setdefault(PANEL_DATA_KEY, {})
    if not panel_data.get("registered"):
        panel_data["registered"] = await _async_register_panel(hass)
        if panel_data["registered"]:
            panel_data["entry_count"] = 0
    if panel_data.get("registered"):
        panel_data["entry_count"] = int(panel_data.get("entry_count", 0)) + 1

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={
            (DOMAIN, bridge.config_entry.data[CONF_USERNAME]),
        },
        name=f"hubspace-{bridge.config_entry.data[CONF_USERNAME]}",
        manufacturer="Hubspace",
        model="Cloud API",
    )
    return True


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate to the latest version."""
    _LOGGER.debug(
        "Migrating configuration from version %s.%s",
        config_entry.version,
        config_entry.minor_version,
    )
    res = True
    if config_entry.version == 1:
        await perform_v2_migration(hass, config_entry)
    if config_entry.version == 2 and config_entry.minor_version == 0:
        await perform_v3_migration(hass, config_entry)
    if config_entry.version == 3 and config_entry.minor_version == 0:
        res = await perform_v4_migration(hass, config_entry)
    if config_entry.version == 4 and config_entry.minor_version == 0:
        res = await perform_v5_migration(hass, config_entry)
    _LOGGER.debug(
        "Migration to configuration version %s.%s successful",
        config_entry.version,
        config_entry.minor_version,
    )
    return res


async def perform_v2_migration(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Perform version 2 migration of the configuration entry.

    * Ensure CONF_TIMEOUT is present in the data
    """
    new_data = {**config_entry.data}
    new_data[CONF_TIMEOUT] = DEFAULT_TIMEOUT
    hass.config_entries.async_update_entry(
        config_entry, data=new_data, version=2, minor_version=0
    )


async def perform_v3_migration(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Perform version 3 migration of the configuration entry.

    * Ensure CONF_TIMEOUT is present in options and removed from data
    * Ensure POLLING_TIME_STR is set in options and removed from data (dev build)
    * Ensure unique_id is set to the account in lowercase
    * Ensure the title is set to the account in lowercase
    """
    options = {**config_entry.options}
    data = {**config_entry.data}
    options[POLLING_TIME_STR] = (
        data.pop(POLLING_TIME_STR, None)
        or options.get(POLLING_TIME_STR)
        or DEFAULT_POLLING_INTERVAL_SEC
    )
    options[CONF_TIMEOUT] = (
        data.pop(CONF_TIMEOUT, None) or options.get(CONF_TIMEOUT) or DEFAULT_TIMEOUT
    )
    # Previous versions may have used None for the unique ID
    unique_id = config_entry.data[CONF_USERNAME].lower()
    hass.config_entries.async_update_entry(
        config_entry,
        data=data,
        options=options,
        version=3,
        minor_version=0,
        unique_id=unique_id,
        title=unique_id,
    )


async def perform_v4_migration(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Perform version 4 migration of the configuration entry.

    * Ensure CONF_TOKEN is set
    """
    options = {**config_entry.options}
    data = {**config_entry.data}
    # Generate the new token
    api = AferoBridgeV1(
        config_entry.data[CONF_USERNAME],
        config_entry.data[CONF_PASSWORD],
        session=aiohttp_client.async_get_clientsession(hass),
        polling_interval=config_entry.options[POLLING_TIME_STR],
    )
    try:
        await api.get_account_id()
    except InvalidAuth:
        config_entry.async_start_reauth(hass)
        return False
    data[CONF_TOKEN] = api.refresh_token
    # Previous versions may have used None for the unique ID
    unique_id = config_entry.data[CONF_USERNAME].lower()
    hass.config_entries.async_update_entry(
        config_entry,
        data=data,
        options=options,
        version=4,
        minor_version=0,
        unique_id=unique_id,
        title=unique_id,
    )
    return True


async def perform_v5_migration(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Perform version 5 migration of the configuration entry.

    * Ensure client is set
    """
    new_data = {**config_entry.data}
    new_data[CONF_CLIENT] = DEFAULT_CLIENT
    hass.config_entries.async_update_entry(
        config_entry, data=new_data, version=5, minor_version=0
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    try:
        unload_success = await hass.data[DOMAIN][entry.entry_id].async_reset()
    except KeyError:
        unload_success = True
    panel_data = hass.data.get(PANEL_DATA_KEY)
    if unload_success and panel_data and panel_data.get("registered"):
        remaining = max(int(panel_data.get("entry_count", 1)) - 1, 0)
        panel_data["entry_count"] = remaining
        if remaining == 0:
            async_remove_panel(hass, PANEL_URL_PATH)
            panel_data["registered"] = False
    if not hass.data.get(DOMAIN):
        hass.data.pop(DOMAIN)
    return unload_success
