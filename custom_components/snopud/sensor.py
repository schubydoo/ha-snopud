"""Sensors that show how recent the SnoPUD data is."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ServiceType
from .const import DOMAIN
from .coordinator import SERVICE_KEYS, SnoPUDConfigEntry, SnoPUDCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SnoPUDConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add one sensor per service."""
    async_add_entities(
        SnoPUDLastReadingSensor(entry.runtime_data, service) for service in ServiceType
    )


class SnoPUDLastReadingSensor(CoordinatorEntity[SnoPUDCoordinator], SensorEntity):
    """Start of the newest hour of usage that the portal published."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: SnoPUDCoordinator, service: ServiceType) -> None:
        """Set the IDs and the device."""
        super().__init__(coordinator)
        self._service = service
        prop = coordinator.data.property
        key = SERVICE_KEYS[service]
        self._attr_translation_key = f"{key}_last_reading"
        self._attr_unique_id = f"{prop.id}_{key}_last_reading"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, prop.id)},
            name=f"SnoPUD {prop.name}",
            manufacturer="Snohomish County PUD",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> datetime | None:
        """Return the start of the newest hour."""
        return self.coordinator.data.last_reading.get(self._service)
