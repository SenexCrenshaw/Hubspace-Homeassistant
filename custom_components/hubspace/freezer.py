"""Shared helpers for Hubspace freezer entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from aioafero import AferoDevice, AferoState
from aioafero.device import get_capability_from_device, get_function_from_device
from aioafero.v1.controllers.device import DeviceController
from aioafero.v1.controllers.event import EventType
from aioafero.v1.models.device import Device
from aioafero.v1.models.features import NumbersFeature, SelectFeature
from homeassistant.const import UnitOfTemperature
from homeassistant.core import callback

from .const import DEVICE_CLASS_FREEZER
from .entity import HubspaceBaseEntity

if TYPE_CHECKING:
    from .bridge import HubspaceBridge


type FreezerKey = tuple[str, str | None]


@dataclass(frozen=True)
class FreezerDescription:
    """Common freezer entity description."""

    key: FreezerKey
    name: str


@dataclass
class FreezerUpdate:
    """Freezer update payload for the generic device controller."""

    numbers: dict[FreezerKey, NumbersFeature] = field(default_factory=dict)
    selects: dict[FreezerKey, SelectFeature] = field(default_factory=dict)


FREEZER_NUMBERS: Final[dict[FreezerKey, FreezerDescription]] = {
    ("temperature", "freezer-target"): FreezerDescription(
        key=("temperature", "freezer-target"),
        name="Freezer Target Temperature",
    ),
    ("temperature", "fridge-target"): FreezerDescription(
        key=("temperature", "fridge-target"),
        name="Fridge Target Temperature",
    ),
}

FREEZER_SELECTS: Final[dict[FreezerKey, FreezerDescription]] = {
    ("mode", None): FreezerDescription(
        key=("mode", None),
        name="Mode",
    ),
    ("temperature-units", None): FreezerDescription(
        key=("temperature-units", None),
        name="Temperature Units",
    ),
}

FREEZER_SWITCHES: Final[dict[FreezerKey, FreezerDescription]] = {
    ("super-cold", "super-cold"): FreezerDescription(
        key=("super-cold", "super-cold"),
        name="Super Cold",
    ),
}

FREEZER_SENSORS: Final[dict[FreezerKey, FreezerDescription]] = {
    ("super-cold-completed", "freezer"): FreezerDescription(
        key=("super-cold-completed", "freezer"),
        name="Freezer Super Cold Status",
    ),
    ("super-cold-completed", "refrigerator"): FreezerDescription(
        key=("super-cold-completed", "refrigerator"),
        name="Refrigerator Super Cold Status",
    ),
}

FREEZER_EVENT_FILTER: Final[tuple[EventType, ...]] = (
    EventType.RESOURCE_UPDATED,
    EventType.RESOURCE_UPDATE_RESPONSE,
)

TEMPERATURE_UNIT_MAPPING: Final[dict[str, UnitOfTemperature]] = {
    "celsius": UnitOfTemperature.CELSIUS,
    "fahrenheit": UnitOfTemperature.FAHRENHEIT,
}


def is_freezer_resource(resource: Device) -> bool:
    """Return whether the device resource represents a freezer."""
    return resource.device_information.device_class == DEVICE_CLASS_FREEZER


def get_freezer_raw_device(
    bridge: HubspaceBridge, resource: Device
) -> AferoDevice | None:
    """Get the raw freezer device for a tracked device resource."""
    raw_device = bridge.api.get_afero_device(resource.id)
    if raw_device is None or raw_device.device_class != DEVICE_CLASS_FREEZER:
        return None
    return raw_device


def has_freezer_feature(raw_device: AferoDevice, key: FreezerKey) -> bool:
    """Return whether the raw freezer device contains the given function."""
    return get_function_from_device(raw_device.functions, key[0], key[1]) is not None


def merge_freezer_states(
    current_states: dict[FreezerKey, Any], states: list[AferoState]
) -> None:
    """Merge raw freezer states into an entity-local cache."""
    for state in states:
        current_states[(state.functionClass, state.functionInstance)] = state.value


class HubspaceFreezerEntity(HubspaceBaseEntity):
    """Base class for freezer entities backed by raw Afero state."""

    def __init__(
        self,
        bridge: HubspaceBridge,
        controller: DeviceController,
        resource: Device,
        raw_device: AferoDevice,
        instance: str,
    ) -> None:
        """Initialize the freezer entity."""
        super().__init__(bridge, controller, resource, instance=instance)
        self._raw_device = raw_device
        self._states: dict[FreezerKey, Any] = {}
        merge_freezer_states(self._states, raw_device.states)

    async def async_added_to_hass(self) -> None:
        """Subscribe to both resource and raw freezer updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.bridge.api.events.subscribe(
                self.handle_freezer_event,
                event_filter=FREEZER_EVENT_FILTER,
                resource_filter=(DEVICE_CLASS_FREEZER,),
            )
        )

    @callback
    def handle_freezer_event(
        self, event_type: EventType, event_data: dict | None
    ) -> None:
        """Merge raw freezer state updates."""
        if event_data is None:
            return
        raw_device: AferoDevice | None = event_data.get("device")
        if raw_device is None or raw_device.id != self.resource.id:
            return
        self._raw_device = raw_device
        merge_freezer_states(self._states, raw_device.states)
        self.on_freezer_update()
        self.async_write_ha_state()

    @callback
    def on_freezer_update(self) -> None:
        """Update cached resource features in subclasses."""

    def get_freezer_state(self, key: FreezerKey) -> Any:
        """Get the current raw freezer state."""
        return self._states.get(key)

    def get_number_feature(
        self, description: FreezerDescription
    ) -> NumbersFeature | None:
        """Build a NumbersFeature from the raw freezer data."""
        range_data = self.get_number_range(description.key)
        value = self.get_freezer_state(description.key)
        if range_data is None or value is None:
            return None
        return NumbersFeature(
            value=float(value),
            min=range_data["min"],
            max=range_data["max"],
            step=range_data["step"],
            name=description.name,
            unit=self.get_temperature_unit(),
        )

    def get_number_range(self, key: FreezerKey) -> dict[str, float] | None:
        """Find the min/max/step for a freezer temperature setting."""
        capability = get_capability_from_device(
            self._raw_device.capabilities,
            key[0],
            key[1],
        )
        if capability and capability.options.get("range"):
            return capability.options["range"]

        function = get_function_from_device(self._raw_device.functions, key[0], key[1])
        if function and function.get("values"):
            return function["values"][0].get("range")
        return None

    def get_select_feature(
        self, description: FreezerDescription
    ) -> SelectFeature | None:
        """Build a SelectFeature from the raw freezer data."""
        value = self.get_freezer_state(description.key)
        options = self.get_select_options(description.key)
        if value is None or not options:
            return None
        return SelectFeature(
            selected=str(value),
            selects=set(options),
            name=description.name,
        )

    def get_select_options(self, key: FreezerKey) -> list[str]:
        """Find all supported options for a freezer category function."""
        function = get_function_from_device(self._raw_device.functions, key[0], key[1])
        if function and function.get("values"):
            return [
                str(value["name"])
                for value in function["values"]
                if value.get("name") is not None
            ]

        capability = get_capability_from_device(
            self._raw_device.capabilities,
            key[0],
            key[1],
        )
        if capability:
            return [
                str(value)
                for value in capability.options.get("values", [])
                if value is not None
            ]
        return []

    def get_temperature_unit(self) -> str | None:
        """Get the current freezer temperature unit."""
        unit = self.get_freezer_state(("temperature-units", None))
        if unit is None:
            return None
        return TEMPERATURE_UNIT_MAPPING.get(str(unit))
