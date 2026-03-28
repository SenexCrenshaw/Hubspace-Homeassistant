"""Test freezer-specific entity handling."""

from aioafero import AferoState
from homeassistant.helpers import entity_registry as er
import pytest

from .utils import create_devices_from_data, modify_state

freezer_from_file = create_devices_from_data("freezer.json")
freezer = freezer_from_file[0]

freezer_parent_child_from_file = create_devices_from_data("freezer-parent-child.json")
freezer_parent_child = next(
    device
    for device in freezer_parent_child_from_file
    if device.device_class == "freezer"
)

FREEZER_ENTITY_IDS = {
    "number.friendly_device_0_freezer_target_temperature": -20.0,
    "number.friendly_device_0_fridge_target_temperature": 5.0,
    "select.friendly_device_0_mode": "freezer",
    "select.friendly_device_0_temperature_units": "fahrenheit",
    "switch.friendly_device_0_super_cold": "off",
    "sensor.friendly_device_0_freezer_super_cold_status": "complete",
    "sensor.friendly_device_0_refrigerator_super_cold_status": "complete",
}

FREEZER_PARENT_CHILD_ENTITY_IDS = {
    "number.outside_1_freezer_target_temperature": -11.0,
    "number.outside_1_fridge_target_temperature": 41.0,
    "select.outside_1_mode": "freezer",
    "select.outside_1_temperature_units": "fahrenheit",
    "switch.outside_1_super_cold": "on",
    "sensor.outside_1_freezer_super_cold_status": "on",
    "sensor.outside_1_refrigerator_super_cold_status": "complete",
}


@pytest.fixture
async def mocked_freezer(mocked_entry):
    """Initialize a mocked freezer and register it within Home Assistant."""
    hass, entry, bridge = mocked_entry
    await bridge.generate_devices_from_data(freezer_from_file)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    yield hass, entry, bridge
    await bridge.close()


@pytest.mark.asyncio
async def test_freezer_entities_setup(mocked_entry):
    """Ensure freezer entities are properly discovered and registered."""
    try:
        hass, entry, bridge = mocked_entry
        await bridge.generate_devices_from_data(freezer_from_file)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        entity_reg = er.async_get(hass)
        for entity_id, expected in FREEZER_ENTITY_IDS.items():
            assert entity_reg.async_get(entity_id) is not None
            entity = hass.states.get(entity_id)
            assert entity is not None
            if entity_id.startswith("number."):
                assert float(entity.state) == expected
            else:
                assert entity.state == expected
    finally:
        await bridge.close()


@pytest.mark.asyncio
async def test_freezer_entities_setup_parent_child_dump(mocked_entry):
    """Ensure freezer entities are created when the dump includes a parent wrapper."""
    try:
        hass, entry, bridge = mocked_entry
        await bridge.generate_devices_from_data(freezer_parent_child_from_file)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        entity_reg = er.async_get(hass)
        for entity_id, expected in FREEZER_PARENT_CHILD_ENTITY_IDS.items():
            assert entity_reg.async_get(entity_id) is not None
            entity = hass.states.get(entity_id)
            assert entity is not None
            if entity_id.startswith("number."):
                assert float(entity.state) == expected
            else:
                assert entity.state == expected
    finally:
        await bridge.close()


@pytest.mark.asyncio
async def test_freezer_number_select_and_switch_services(mocked_freezer):
    """Ensure freezer controls can be adjusted from Home Assistant."""
    hass, _, bridge = mocked_freezer
    await hass.services.async_call(
        "number",
        "set_value",
        {
            "entity_id": "number.friendly_device_0_freezer_target_temperature",
            "value": -18,
        },
        blocking=True,
    )
    await hass.services.async_call(
        "select",
        "select_option",
        {
            "entity_id": "select.friendly_device_0_mode",
            "option": "refrigerator",
        },
        blocking=True,
    )
    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": "switch.friendly_device_0_super_cold"},
        blocking=True,
    )
    await bridge.async_block_until_done()
    await hass.async_block_till_done()

    freezer_number = hass.states.get(
        "number.friendly_device_0_freezer_target_temperature"
    )
    mode_select = hass.states.get("select.friendly_device_0_mode")
    super_cold = hass.states.get("switch.friendly_device_0_super_cold")

    assert freezer_number is not None
    assert float(freezer_number.state) == -18
    assert mode_select is not None
    assert mode_select.state == "refrigerator"
    assert super_cold is not None
    assert super_cold.state == "on"


@pytest.mark.asyncio
async def test_freezer_entity_updates_from_raw_events(mocked_entry):
    """Ensure freezer entities react to raw freezer state updates."""
    hass, entry, bridge = mocked_entry
    await bridge.generate_devices_from_data(freezer_from_file)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    freezer_update = create_devices_from_data("freezer.json")[0]
    modify_state(
        freezer_update,
        AferoState(
            functionClass="temperature",
            functionInstance="freezer-target",
            value=-16.0,
        ),
    )
    modify_state(
        freezer_update,
        AferoState(
            functionClass="mode",
            functionInstance=None,
            value="refrigerator",
        ),
    )
    modify_state(
        freezer_update,
        AferoState(
            functionClass="super-cold",
            functionInstance="super-cold",
            value="on",
        ),
    )
    modify_state(
        freezer_update,
        AferoState(
            functionClass="super-cold-completed",
            functionInstance="freezer",
            value="on",
        ),
    )
    await bridge.generate_devices_from_data([freezer_update])
    await hass.async_block_till_done()

    freezer_number = hass.states.get(
        "number.friendly_device_0_freezer_target_temperature"
    )
    mode_select = hass.states.get("select.friendly_device_0_mode")
    super_cold = hass.states.get("switch.friendly_device_0_super_cold")
    freezer_status = hass.states.get(
        "sensor.friendly_device_0_freezer_super_cold_status"
    )

    assert freezer_number is not None
    assert float(freezer_number.state) == -16
    assert mode_select is not None
    assert mode_select.state == "refrigerator"
    assert super_cold is not None
    assert super_cold.state == "on"
    assert freezer_status is not None
    assert freezer_status.state == "on"
