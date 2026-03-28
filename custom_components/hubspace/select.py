"""Home Assistant entity for interacting with Afero Select."""

from dataclasses import fields

from aioafero.v1 import AferoController, AferoModelResource
from aioafero.v1.controllers.device import DeviceController
from aioafero.v1.controllers.event import EventType
from aioafero.v1.models.device import Device
from aioafero.v1.models.features import SelectFeature
from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import HubspaceBridge
from .const import DOMAIN
from .entity import HubspaceBaseEntity
from .freezer import (
    FREEZER_SELECTS,
    FreezerDescription,
    FreezerUpdate,
    HubspaceFreezerEntity,
    get_freezer_raw_device,
    has_freezer_feature,
    is_freezer_resource,
)


class AferoSelectEntitiy(HubspaceBaseEntity, SelectEntity):
    """Representation of an Afero Select."""

    def __init__(
        self,
        bridge: HubspaceBridge,
        controller: AferoController,
        resource: AferoModelResource,
        identifier: tuple[str, str],
    ) -> None:
        """Initialize an Afero Select."""

        super().__init__(bridge, controller, resource, instance=str(identifier))
        self._identifier: tuple[str, str] = identifier
        self._attr_name = resource.selects[identifier].name

    @property
    def current_option(self) -> str:
        """The current select option."""
        return str(self.resource.selects[self._identifier].selected)

    @property
    def options(self) -> list:
        """A list of available options as strings."""
        return sorted([str(x) for x in self.resource.selects[self._identifier].selects])

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await self.bridge.async_request_call(
            self.controller.set_state,
            device_id=self.resource.id,
            selects={
                self._identifier: option,
            },
        )


class HubspaceFreezerSelectEntity(HubspaceFreezerEntity, SelectEntity):
    """Representation of a freezer select derived from raw device state."""

    def __init__(
        self,
        bridge: HubspaceBridge,
        controller: DeviceController,
        resource: Device,
        description: FreezerDescription,
    ) -> None:
        """Initialize a freezer select entity."""
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
    def current_option(self) -> str | None:
        """Return the current freezer option."""
        value = self.get_freezer_state(self.description.key)
        return None if value is None else str(value)

    @property
    def options(self) -> list[str]:
        """Return all available freezer options."""
        return sorted(self.get_select_options(self.description.key))

    @callback
    def on_freezer_update(self) -> None:
        """Sync the current raw freezer state onto the device resource."""
        return

    async def async_select_option(self, option: str) -> None:
        """Change the selected freezer option."""
        current_feature = self.get_select_feature(self.description)
        if current_feature is None:
            return
        await self.bridge.async_request_call(
            self.controller.update,
            device_id=self.resource.id,
            obj_in=FreezerUpdate(
                selects={
                    self.description.key: SelectFeature(
                        selected=option,
                        selects=current_feature.selects,
                        name=current_feature.name,
                    )
                }
            ),
        )
        self._states[self.description.key] = option
        self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up entities."""
    bridge: HubspaceBridge = hass.data[DOMAIN][config_entry.entry_id]

    # add all current items in the controller
    entities = []
    for controller in bridge.api.controllers:
        if "selects" not in [x.name for x in fields(controller.ITEM_CLS)]:
            continue
        config_entry.async_on_unload(
            controller.subscribe(
                await generate_callback(bridge, controller, async_add_entities),
                event_filter=EventType.RESOURCE_ADDED,
            )
        )
        # Add any currently tracked entities
        entities.extend(
            [
                AferoSelectEntitiy(bridge, controller, resource, select)
                for resource in controller
                for select in resource.selects
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
            HubspaceFreezerSelectEntity(bridge, device_controller, resource, description)
            for resource in device_controller
            if is_freezer_resource(resource)
            for description in FREEZER_SELECTS.values()
            if (raw_device := get_freezer_raw_device(bridge, resource)) is not None
            and has_freezer_feature(raw_device, description.key)
        ]
    )

    async_add_entities(entities)


async def generate_callback(bridge, controller, async_add_entities: callback):
    """Generate a callback function for handling new select entities.

    Args:
        bridge: HubspaceBridge instance for managing device communication
        controller: AferoController instance managing the device
        async_add_entities: Callback function to register new entities

    Returns:
        Callback function that adds new select entities when resources are added

    """

    async def add_entity_controller(
        event_type: EventType, resource: AferoModelResource
    ) -> None:
        """Add one or more Selects."""
        async_add_entities(
            [
                AferoSelectEntitiy(bridge, controller, resource, select)
                for select in resource.selects
            ]
        )

    return add_entity_controller


async def generate_freezer_callback(
    bridge: HubspaceBridge,
    controller: DeviceController,
    async_add_entities: callback,
):
    """Generate a callback function for handling new freezer select entities."""

    async def add_freezer_entities(event_type: EventType, resource: Device) -> None:
        """Add freezer select entities for a newly discovered freezer."""
        raw_device = get_freezer_raw_device(bridge, resource)
        if not is_freezer_resource(resource) or raw_device is None:
            return
        async_add_entities(
            [
                HubspaceFreezerSelectEntity(bridge, controller, resource, description)
                for description in FREEZER_SELECTS.values()
                if has_freezer_feature(raw_device, description.key)
            ]
        )

    return add_freezer_entities
