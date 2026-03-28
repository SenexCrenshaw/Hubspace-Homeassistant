"""Home Assistant entity for interacting with Afero Switch."""

from functools import partial
from typing import Any

from aioafero.v1 import AferoBridgeV1
from aioafero.v1.controllers.device import DeviceController
from aioafero.v1.controllers.event import EventType
from aioafero.v1.controllers.switch import SwitchController
from aioafero.v1.models.device import Device
from aioafero.v1.models.features import SelectFeature
from aioafero.v1.models.switch import Switch
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import HubspaceBridge
from .const import DOMAIN
from .entity import HubspaceBaseEntity
from .freezer import (
    FREEZER_SWITCHES,
    FreezerDescription,
    FreezerUpdate,
    HubspaceFreezerEntity,
    get_freezer_raw_device,
    has_freezer_feature,
    is_freezer_resource,
)


class HubspaceSwitch(HubspaceBaseEntity, SwitchEntity):
    """Representation of an Afero switch."""

    def __init__(
        self,
        bridge: HubspaceBridge,
        controller: SwitchController,
        resource: Switch,
        instance: str | None,
    ) -> None:
        """Initialize an Afero switch."""
        super().__init__(bridge, controller, resource, instance=instance)
        self.instance = instance

    @property
    def is_on(self) -> bool | None:
        """Determines if the switch is on."""
        feature = self.resource.on.get(self.instance, None)
        if feature:
            return feature.on
        return None

    async def async_turn_on(
        self,
        **kwargs: Any,
    ) -> None:
        """Turn on the entity."""
        self.logger.debug("Adjusting entity %s with %s", self.resource.id, kwargs)
        await self.bridge.async_request_call(
            self.controller.set_state,
            device_id=self.resource.id,
            on=True,
            instance=self.instance,
        )

    async def async_turn_off(
        self,
        **kwargs: Any,
    ) -> None:
        """Turn off the entity."""
        self.logger.debug("Adjusting entity %s with %s", self.resource.id, kwargs)
        await self.bridge.async_request_call(
            self.controller.set_state,
            device_id=self.resource.id,
            on=False,
            instance=self.instance,
        )


class HubspaceFreezerSwitch(HubspaceFreezerEntity, SwitchEntity):
    """Representation of a freezer switch derived from raw device state."""

    def __init__(
        self,
        bridge: HubspaceBridge,
        controller: DeviceController,
        resource: Device,
        description: FreezerDescription,
    ) -> None:
        """Initialize a freezer switch entity."""
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
    def is_on(self) -> bool | None:
        """Determine if the freezer switch is enabled."""
        return self.get_freezer_state(self.description.key) == "on"

    @callback
    def on_freezer_update(self) -> None:
        """Sync the current raw freezer state onto the device resource."""
        return

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the freezer switch."""
        await self._async_set_state("on")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the freezer switch."""
        await self._async_set_state("off")

    async def _async_set_state(self, value: str) -> None:
        """Set the current freezer switch value."""
        current_feature = self.get_select_feature(self.description)
        if current_feature is None:
            return
        await self.bridge.async_request_call(
            self.controller.update,
            device_id=self.resource.id,
            obj_in=FreezerUpdate(
                selects={
                    self.description.key: SelectFeature(
                        selected=value,
                        selects=current_feature.selects,
                        name=current_feature.name,
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
    api: AferoBridgeV1 = bridge.api
    controller: SwitchController = api.switches
    make_entity = partial(HubspaceSwitch, bridge, controller)

    def get_unique_entities(hs_resource: Switch) -> list[HubspaceSwitch]:
        instances = hs_resource.on.keys()
        return [
            make_entity(hs_resource, instance)
            for instance in instances
            if len(instances) == 1 or instance is not None
        ]

    @callback
    def async_add_entity(event_type: EventType, hs_resource: Switch) -> None:
        """Add an entity."""
        async_add_entities(get_unique_entities(hs_resource))

    # add all current items in controller
    entities: list[HubspaceSwitch] = []
    for resource in controller:
        entities.extend(get_unique_entities(resource))

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
            HubspaceFreezerSwitch(bridge, device_controller, resource, description)
            for resource in device_controller
            if is_freezer_resource(resource)
            for description in FREEZER_SWITCHES.values()
            if (raw_device := get_freezer_raw_device(bridge, resource)) is not None
            and has_freezer_feature(raw_device, description.key)
        ]
    )
    async_add_entities(entities)
    # register listener for new entities
    config_entry.async_on_unload(
        controller.subscribe(async_add_entity, event_filter=EventType.RESOURCE_ADDED)
    )


async def generate_freezer_callback(
    bridge: HubspaceBridge,
    controller: DeviceController,
    async_add_entities: callback,
):
    """Generate a callback function for handling new freezer switches."""

    async def add_freezer_entities(event_type: EventType, resource: Device) -> None:
        """Add freezer switch entities for a newly discovered freezer."""
        raw_device = get_freezer_raw_device(bridge, resource)
        if not is_freezer_resource(resource) or raw_device is None:
            return
        async_add_entities(
            [
                HubspaceFreezerSwitch(bridge, controller, resource, description)
                for description in FREEZER_SWITCHES.values()
                if has_freezer_feature(raw_device, description.key)
            ]
        )

    return add_freezer_entities
