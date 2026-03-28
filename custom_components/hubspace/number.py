"""Home Assistant entity for interacting with Afero Number."""

from dataclasses import fields

from aioafero.v1 import AferoController, AferoModelResource
from aioafero.v1.controllers.device import DeviceController
from aioafero.v1.controllers.event import EventType
from aioafero.v1.models.device import Device
from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import HubspaceBridge
from .const import DOMAIN
from .entity import HubspaceBaseEntity
from .freezer import (
    FREEZER_NUMBERS,
    FreezerDescription,
    FreezerUpdate,
    HubspaceFreezerEntity,
    get_freezer_raw_device,
    has_freezer_feature,
    is_freezer_resource,
)


class AferoNumberEntity(HubspaceBaseEntity, NumberEntity):
    """Representation of an Afero Number."""

    def __init__(
        self,
        bridge: HubspaceBridge,
        controller: AferoController,
        resource: AferoModelResource,
        identifier: tuple[str, str],
    ) -> None:
        """Initialize an Afero Number."""
        super().__init__(bridge, controller, resource, instance=str(identifier))
        self._identifier: tuple[str, str] = identifier
        self._attr_name = resource.numbers[identifier].name

    @property
    def native_max_value(self) -> float:
        """The maximum accepted value in the number's native_unit_of_measurement (inclusive)."""
        return self.resource.numbers[self._identifier].max

    @property
    def native_min_value(self) -> float:
        """The minimum accepted value in the number's native_unit_of_measurement (inclusive)."""
        return self.resource.numbers[self._identifier].min

    @property
    def native_step(self) -> float:
        """Defines the resolution of the values, i.e. the smallest increment or decrement in the number's."""
        return self.resource.numbers[self._identifier].step

    @property
    def native_value(self) -> float:
        """The value of the number in the number's native_unit_of_measurement."""
        return self.resource.numbers[self._identifier].value

    @property
    def native_unit_of_measurement(self) -> str:
        """The unit of measurement that the sensor's value is expressed in."""
        return self.resource.numbers[self._identifier].unit

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        await self.bridge.async_request_call(
            self.controller.set_state,
            device_id=self.resource.id,
            numbers={
                self._identifier: value,
            },
        )


class HubspaceFreezerNumberEntity(HubspaceFreezerEntity, NumberEntity):
    """Representation of a freezer number derived from raw device state."""

    def __init__(
        self,
        bridge: HubspaceBridge,
        controller: DeviceController,
        resource: Device,
        description: FreezerDescription,
    ) -> None:
        """Initialize a freezer number entity."""
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
        self._attr_name = description.name
        self.on_freezer_update()

    @property
    def native_max_value(self) -> float | None:
        """Return the maximum freezer setting."""
        range_data = self.get_number_range(self.description.key)
        return None if range_data is None else range_data["max"]

    @property
    def native_min_value(self) -> float | None:
        """Return the minimum freezer setting."""
        range_data = self.get_number_range(self.description.key)
        return None if range_data is None else range_data["min"]

    @property
    def native_step(self) -> float | None:
        """Return the freezer setting step."""
        range_data = self.get_number_range(self.description.key)
        return None if range_data is None else range_data["step"]

    @property
    def native_value(self) -> float | None:
        """Return the current freezer setting."""
        value = self.get_freezer_state(self.description.key)
        return None if value is None else float(value)

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the current freezer setting unit."""
        return self.get_temperature_unit()

    @callback
    def on_freezer_update(self) -> None:
        """Sync the current raw freezer state onto the device resource."""
        return

    async def async_set_native_value(self, value: float) -> None:
        """Update the current freezer value."""
        current_feature = self.get_number_feature(self.description)
        if current_feature is None:
            return
        await self.bridge.async_request_call(
            self.controller.update,
            device_id=self.resource.id,
            obj_in=FreezerUpdate(
                numbers={
                    self.description.key: type(current_feature)(
                        value=value,
                        min=current_feature.min,
                        max=current_feature.max,
                        step=current_feature.step,
                        name=current_feature.name,
                        unit=current_feature.unit,
                    )
                }
            ),
        )
        self._states[self.description.key] = value
        self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up entities."""
    bridge: HubspaceBridge = hass.data[DOMAIN][config_entry.entry_id]

    # add all current items in controller
    entities = []
    for controller in bridge.api.controllers:
        if "numbers" not in [x.name for x in fields(controller.ITEM_CLS)]:
            continue
        # Listen for new devices
        config_entry.async_on_unload(
            controller.subscribe(
                await generate_callback(bridge, controller, async_add_entities),
                event_filter=EventType.RESOURCE_ADDED,
            )
        )
        # Add any currently tracked entities
        entities.extend(
            [
                AferoNumberEntity(bridge, controller, resource, number)
                for resource in controller
                for number in resource.numbers
            ]
        )

    device_controller: DeviceController = bridge.api.devices
    config_entry.async_on_unload(
        device_controller.subscribe(
            await generate_freezer_callback(
                bridge, device_controller, async_add_entities
            ),
            event_filter=EventType.RESOURCE_ADDED,
        )
    )
    entities.extend(
        [
            HubspaceFreezerNumberEntity(
                bridge, device_controller, resource, description
            )
            for resource in device_controller
            if is_freezer_resource(resource)
            for description in FREEZER_NUMBERS.values()
            if (raw_device := get_freezer_raw_device(bridge, resource)) is not None
            and has_freezer_feature(raw_device, description.key)
        ]
    )
    async_add_entities(entities)


async def generate_callback(bridge, controller, async_add_entities: callback):
    """Generate a callback function for handling new number entities.

    Args:
        bridge: HubspaceBridge instance for managing device communication
        controller: AferoController instance managing the device
        async_add_entities: Callback function to register new entities

    Returns:
        Callback function that adds new number entities when resources are added

    """

    async def add_entity_controller(
        event_type: EventType, resource: AferoModelResource
    ) -> None:
        """Add an entity."""
        async_add_entities(
            [
                AferoNumberEntity(bridge, controller, resource, number)
                for number in resource.numbers
            ]
        )

    return add_entity_controller


async def generate_freezer_callback(
    bridge: HubspaceBridge,
    controller: DeviceController,
    async_add_entities: callback,
):
    """Generate a callback function for handling new freezer number entities."""

    async def add_freezer_entities(event_type: EventType, resource: Device) -> None:
        """Add freezer number entities for a newly discovered freezer."""
        raw_device = get_freezer_raw_device(bridge, resource)
        if not is_freezer_resource(resource) or raw_device is None:
            return
        async_add_entities(
            [
                HubspaceFreezerNumberEntity(bridge, controller, resource, description)
                for description in FREEZER_NUMBERS.values()
                if has_freezer_feature(raw_device, description.key)
            ]
        )

    return add_freezer_entities
