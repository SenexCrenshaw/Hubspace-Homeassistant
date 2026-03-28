"""Home Assistant entity for getting state from Afero sensors."""

import logging
from typing import Any

from aioafero.v1 import AferoController, AferoModelResource
from aioafero.v1.controllers.device import DeviceController
from aioafero.v1.controllers.event import EventType
from aioafero.v1.models.device import Device
from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import HubspaceBridge
from .const import DOMAIN, SENSORS_GENERAL
from .entity import HubspaceBaseEntity
from .freezer import (
    FREEZER_SENSORS,
    FreezerDescription,
    HubspaceFreezerEntity,
    get_freezer_raw_device,
    has_freezer_feature,
    is_freezer_resource,
)

LOGGER = logging.getLogger(__name__)


class AferoSensorEntity(HubspaceBaseEntity, SensorEntity):
    """Representation of an Afero sensor."""

    def __init__(
        self,
        bridge: HubspaceBridge,
        controller: AferoController,
        resource: AferoModelResource,
        sensor: str,
    ) -> None:
        """Initialize an Afero sensor."""
        super().__init__(bridge, controller, resource, instance=sensor)
        self.entity_description: SensorEntityDescription = SENSORS_GENERAL.get(sensor)
        self._attr_name = sensor

    @property
    def native_value(self) -> Any:
        """Return the current value."""
        return self.resource.sensors[self._attr_name].value


class HubspaceFreezerSensorEntity(HubspaceFreezerEntity, SensorEntity):
    """Representation of a freezer status sensor derived from raw device state."""

    def __init__(
        self,
        bridge: HubspaceBridge,
        controller: DeviceController,
        resource: Device,
        description: FreezerDescription,
    ) -> None:
        """Initialize a freezer status sensor."""
        raw_device = get_freezer_raw_device(bridge, resource)
        if raw_device is None:
            raise ValueError(f"Unable to find freezer device {resource.id}")
        super().__init__(
            bridge,
            controller,
            resource,
            raw_device,
            instance=description.name,
        )
        self.description = description
        self.entity_description = SensorEntityDescription(key=description.name)
        self._attr_name = description.name

    @property
    def native_value(self) -> Any:
        """Return the current freezer status value."""
        return self.get_freezer_state(self.description.key)


def get_sensors(
    bridge: HubspaceBridge, controller: AferoController, resource: AferoModelResource
) -> list[AferoSensorEntity]:
    """Get all sensors for a given resource."""
    sensor_entities: list[AferoSensorEntity] = []
    for sensor in resource.sensors:
        if sensor not in SENSORS_GENERAL:
            LOGGER.warning(
                "Unknown sensor %s found in %s %s. Please open a bug report",
                sensor,
                type(controller).__name__,
                resource.device_information.name,
            )
            continue
        sensor_entities.append(AferoSensorEntity(bridge, controller, resource, sensor))
    return sensor_entities


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up entities."""
    bridge: HubspaceBridge = hass.data[DOMAIN][config_entry.entry_id]

    for controller in bridge.api.controllers:
        # Listen for new devices
        if not controller.ITEM_SENSORS:
            continue
        config_entry.async_on_unload(
            controller.subscribe(
                await generate_callback(bridge, controller, async_add_entities),
                event_filter=EventType.RESOURCE_ADDED,
            )
        )
        # Add any currently tracked entities
        for resource in controller:
            if sensors := get_sensors(bridge, controller, resource):
                async_add_entities(sensors)

    device_controller: DeviceController = bridge.api.devices
    config_entry.async_on_unload(
        device_controller.subscribe(
            await generate_freezer_callback(
                bridge, device_controller, async_add_entities
            ),
            event_filter=EventType.RESOURCE_ADDED,
        )
    )
    if freezer_sensors := get_freezer_sensors(bridge, device_controller):
        async_add_entities(freezer_sensors)


async def generate_callback(bridge, controller, async_add_entities: callback):
    """Generate a callback function for handling new sensor entities.

    Args:
        bridge: HubspaceBridge instance for managing device communication
        controller: AferoController instance managing the device
        async_add_entities: Callback function to register new entities

    Returns:
        Callback function that adds new sensor entities when resources are added

    """

    async def add_entity_controller(
        event_type: EventType, resource: AferoModelResource
    ) -> None:
        """Add an entity."""
        if sensors := get_sensors(bridge, controller, resource):
            async_add_entities(sensors)

    return add_entity_controller


def get_freezer_sensors(
    bridge: HubspaceBridge, controller: DeviceController
) -> list[HubspaceFreezerSensorEntity]:
    """Get all freezer status sensors."""
    freezer_sensors: list[HubspaceFreezerSensorEntity] = []
    for resource in controller:
        raw_device = get_freezer_raw_device(bridge, resource)
        if not is_freezer_resource(resource) or raw_device is None:
            continue
        freezer_sensors.extend(
            [
                HubspaceFreezerSensorEntity(bridge, controller, resource, description)
                for description in FREEZER_SENSORS.values()
                if has_freezer_feature(raw_device, description.key)
            ]
        )
    return freezer_sensors


async def generate_freezer_callback(
    bridge: HubspaceBridge,
    controller: DeviceController,
    async_add_entities: callback,
):
    """Generate a callback function for handling new freezer sensors."""

    async def add_freezer_entities(event_type: EventType, resource: Device) -> None:
        """Add freezer sensors for a newly discovered freezer."""
        raw_device = get_freezer_raw_device(bridge, resource)
        if not is_freezer_resource(resource) or raw_device is None:
            return
        async_add_entities(
            [
                HubspaceFreezerSensorEntity(bridge, controller, resource, description)
                for description in FREEZER_SENSORS.values()
                if has_freezer_feature(raw_device, description.key)
            ]
        )

    return add_freezer_entities
