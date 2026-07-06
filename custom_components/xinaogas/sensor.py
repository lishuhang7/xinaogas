from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EcejGasCoordinator


@dataclass(frozen=True, kw_only=True)
class EcejGasSensorDescription(SensorEntityDescription):
    pass


SENSORS: tuple[EcejGasSensorDescription, ...] = (
    EcejGasSensorDescription(
        key="balance",
        translation_key="balance",
        native_unit_of_measurement="元",
        icon="mdi:currency-cny",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    EcejGasSensorDescription(
        key="meter_reading",
        translation_key="meter_reading",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        icon="mdi:counter",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    EcejGasSensorDescription(
        key="last_meter_reading",
        translation_key="last_meter_reading",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        icon="mdi:counter",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    EcejGasSensorDescription(
        key="latest_bill_gas",
        translation_key="latest_bill_gas",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        icon="mdi:receipt-text",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    EcejGasSensorDescription(
        key="latest_bill_amount",
        translation_key="latest_bill_amount",
        native_unit_of_measurement="元",
        icon="mdi:receipt-text",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    EcejGasSensorDescription(
        key="gas_price",
        translation_key="gas_price",
        native_unit_of_measurement="元/m³",
        icon="mdi:cash-multiple",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    EcejGasSensorDescription(key="ladder", translation_key="ladder", icon="mdi:stairs"),
    EcejGasSensorDescription(key="query_date", translation_key="query_date", icon="mdi:calendar-search"),
    EcejGasSensorDescription(key="meter_reading_date", translation_key="meter_reading_date", icon="mdi:calendar-check"),
    EcejGasSensorDescription(key="bill_status", translation_key="bill_status", icon="mdi:receipt-text-check"),
    EcejGasSensorDescription(key="meter_type", translation_key="meter_type", icon="mdi:meter-gas"),
    EcejGasSensorDescription(key="company_name", translation_key="company_name", icon="mdi:domain"),
    EcejGasSensorDescription(key="last_update_time", translation_key="last_update_time", icon="mdi:update"),
    EcejGasSensorDescription(
        key="accumulate_total",
        translation_key="accumulate_total",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        icon="mdi:sigma",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    EcejGasSensorDescription(
        key="yesterday_gas_total",
        translation_key="yesterday_gas_total",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        icon="mdi:calendar-arrow-left",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # 新增：阀门状态
    EcejGasSensorDescription(
        key="valve_status",
        translation_key="valve_status",
        icon="mdi:valve",
    ),
    # 新增：设备状态（报警）
    EcejGasSensorDescription(
        key="alarm_status",
        translation_key="alarm_status",
        icon="mdi:shield-check",
    ),
    # 新增：电池电量
    EcejGasSensorDescription(
        key="electricity_status",
        translation_key="electricity_status",
        icon="mdi:battery",
    ),
    # 新增：近 7 天用量（传感器显示最新一天）
    EcejGasSensorDescription(
        key="week_usage",
        translation_key="week_usage",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        icon="mdi:chart-bar",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # 新增：近 12 个月用量（传感器显示最新一月）
    EcejGasSensorDescription(
        key="month_usage",
        translation_key="month_usage",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        icon="mdi:chart-line",
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EcejGasCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(EcejGasSensor(coordinator, entry, description) for description in SENSORS)


class EcejGasSensor(CoordinatorEntity[EcejGasCoordinator], SensorEntity):
    entity_description: EcejGasSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EcejGasCoordinator,
        entry: ConfigEntry,
        description: EcejGasSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        data = self.coordinator.data or {}
        return data.get(self.entity_description.key)

    @property
    def device_info(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        cardbind_id = str(data.get("cardbind_id") or self.entry.entry_id)
        pay_no = str(data.get("pay_no") or "").strip()
        name = f"新奥燃气 {pay_no}" if pay_no else "新奥燃气"
        return {
            "identifiers": {(DOMAIN, cardbind_id)},
            "name": name,
            "manufacturer": "新奥燃气",
            "model": data.get("company_name") or "e城e家",
        }

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self.coordinator.data or {}
        attrs = {
            "家庭名称": data.get("family_account_name"),
            "用户名称": data.get("user_name"),
            "缴费号": data.get("pay_no"),
            "地址": data.get("address"),
            "燃气公司": data.get("company_name"),
            "配置城市": data.get("configured_city_name"),
            "cityId": data.get("city_id"),
            "cardbindId": data.get("cardbind_id"),
            "platformOnlyCardNo": data.get("platform_only_card_no"),
            "累计燃气用量": data.get("accumulate_total"),
            "昨日燃气用量": data.get("yesterday_gas_total"),
            # 图表数据
            "近7天用气明细": data.get("week_statistic"),
            "近12个月用气明细": data.get("month_statistic"),
        }
        return {key: value for key, value in attrs.items() if value not in (None, "", [], {})} or None
