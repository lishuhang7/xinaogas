from __future__ import annotations

import hashlib
import random
import re
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout
from homeassistant.util import dt as dt_util

from .const import APPKEY_SECRET, BALANCE_URL, BILL_URL, BIND_CARDS_URL, IOT_DEVICE_DETAIL_URL, USER_AGENT


class EcejGasApiError(Exception):
    pass


class EcejGasAuthError(EcejGasApiError):
    pass


def generate_app_key() -> str:
    date_str = dt_util.now().strftime("%Y%m%d%H%M%S")
    value = hashlib.md5((date_str + APPKEY_SECRET).encode("utf-8")).hexdigest()
    return f"{date_str}{value}"


def _to_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).strip())
    return float(match.group(0)) if match else None


def _first(value: Any) -> dict[str, Any]:
    if isinstance(value, list) and value:
        return value[0] if isinstance(value[0], dict) else {}
    return value if isinstance(value, dict) else {}


def _meter_type(card: dict[str, Any]) -> str | None:
    business_name = card.get("businessName")
    if business_name:
        return str(business_name)
    business_type = str(card.get("businessType") or "")
    if business_type == "4":
        return "燃气普表"
    if business_type == "21":
        return "物联表"
    return None


def _card_key(card: dict[str, Any]) -> tuple[str, str]:
    return str(card.get("cardbindID") or card.get("cardbindId") or ""), str(card.get("platformCardNo") or "")


class EcejGasApi:
    def __init__(
        self,
        session: ClientSession,
        token: str,
        city_id: str,
        cardbind_id: str | None = None,
        platform_card_no: str | None = None,
        device_id: str | None = None,
        device_type: str | None = None,
    ) -> None:
        self._session = session
        self._token = token.strip()
        self._city_id = city_id.strip()
        self._cardbind_id = (cardbind_id or "").strip()
        self._platform_card_no = (platform_card_no or "").strip()
        self._device_id = (device_id or "").strip()
        self._device_type = (device_type or "").strip()

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "*/*",
            "Accept-Language": "zh-Hans-CN;q=1.0",
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "Host": "lp.ecej.com",
            "OSVersion": "26.4.2",
            "platform": "ios",
            "version": "101387",
            "random": str(random.randint(1000, 9999)),
            "cityId": self._city_id,
            "User-Agent": USER_AGENT,
        }

    def _iot_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh-Hans;q=0.9",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._token}",
            "X-Requested-With": "XMLHttpRequest",
            "X-Request-Scope": "ecejappuser",
            "User-Agent": USER_AGENT,
            "Origin": "https://iot.ecej.com",
            "Referer": f"https://iot.ecej.com/smart/ecej-gasMeter.html?token={self._token}&cityId={self._city_id}",
        }

    def _check(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise EcejGasApiError("接口返回格式异常")

        result_code = str(payload.get("resultCode"))
        message = payload.get("message") or payload.get("msg") or "接口返回失败"

        if result_code == "200":
            return payload
        if result_code in {"401", "403", "1001", "1002", "1003"} or "token" in str(message).lower():
            raise EcejGasAuthError(f"认证失败：{message}")
        raise EcejGasApiError(f"{message}（{result_code}）")

    def _check_iot(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise EcejGasApiError("IoT接口返回格式异常")
        code = payload.get("code")
        if code == 200:
            return payload
        message = payload.get("message") or payload.get("msg") or "IoT接口返回失败"
        if code in (401, 403) or "token" in str(message).lower():
            raise EcejGasAuthError(f"IoT认证失败：{message}")
        raise EcejGasApiError(f"IoT错误：{message}（code={code}）")

    async def _get(self, url: str, params: dict[str, str]) -> dict[str, Any]:
        try:
            async with self._session.get(
                url,
                headers=self._headers(),
                params=params,
                timeout=ClientTimeout(total=25),
            ) as response:
                response.raise_for_status()
                return self._check(await response.json(content_type=None))
        except ClientError as err:
            raise EcejGasApiError(str(err)) from err
        except ValueError as err:
            raise EcejGasApiError("接口返回无法解析") from err

    async def _post(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        try:
            async with self._session.post(
                url,
                headers=self._headers(),
                data=data,
                timeout=ClientTimeout(total=25),
            ) as response:
                response.raise_for_status()
                return self._check(await response.json(content_type=None))
        except ClientError as err:
            raise EcejGasApiError(str(err)) from err
        except ValueError as err:
            raise EcejGasApiError("接口返回无法解析") from err

    async def async_get_bind_cards(self) -> list[dict[str, Any]]:
        payload = await self._get(
            BIND_CARDS_URL,
            {
                "appKey": generate_app_key(),
                "cityId": self._city_id,
                "token": self._token,
            },
        )

        cards: list[tuple[str, dict[str, Any]]] = []
        for business in payload.get("data") or []:
            if not isinstance(business, dict):
                continue
            business_type = str(business.get("businessType") or "")
            business_name = business.get("businessName")
            for card in business.get("cardList") or []:
                if not isinstance(card, dict):
                    continue
                if not card.get("cardbindID") or not card.get("platformCardNo"):
                    continue
                card = dict(card)
                card["businessType"] = card.get("businessType") or business_type
                card["businessName"] = card.get("businessName") or business_name
                cards.append((business_type, card))

        sorted_cards: list[dict[str, Any]] = []
        used: set[tuple[str, str]] = set()
        for business_type in ("4", "21"):
            for item_type, card in cards:
                key = _card_key(card)
                if item_type == business_type and key not in used:
                    sorted_cards.append(card)
                    used.add(key)
        for _, card in cards:
            key = _card_key(card)
            if key not in used:
                sorted_cards.append(card)
                used.add(key)

        if not sorted_cards:
            raise EcejGasApiError("未找到绑定的燃气户号")
        return sorted_cards

    async def async_get_bind_card(self) -> dict[str, Any]:
        cards = await self.async_get_bind_cards()
        if self._cardbind_id or self._platform_card_no:
            for card in cards:
                cardbind_id, platform_card_no = _card_key(card)
                if self._cardbind_id and cardbind_id == self._cardbind_id:
                    return card
                if self._platform_card_no and platform_card_no == self._platform_card_no:
                    return card
        return cards[0]

    async def async_get_balance(self, cardbind_id: str) -> dict[str, Any]:
        return await self._post(
            BALANCE_URL,
            {
                "appKey": generate_app_key(),
                "cardbindId": str(cardbind_id),
                "cityId": self._city_id,
                "token": self._token,
            },
        )

    async def async_get_bill(self, platform_card_no: str) -> dict[str, Any]:
        return await self._post(
            BILL_URL,
            {
                "appKey": generate_app_key(),
                "debug": "true",
                "platformOnlyCardNo": str(platform_card_no),
                "token": self._token,
            },
        )

    async def async_get_device_detail(self, device_id: str, device_type: str) -> dict[str, Any]:
        if not device_id or not device_type:
            raise EcejGasApiError("缺少设备ID或设备类型")
        body = {
            "deviceId": str(device_id),
            "deviceType": str(device_type),
        }
        try:
            async with self._session.post(
                IOT_DEVICE_DETAIL_URL,
                headers=self._iot_headers(),
                json=body,
                timeout=ClientTimeout(total=25),
            ) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
                return self._check_iot(payload)
        except ClientError as err:
            raise EcejGasApiError(f"IoT请求失败：{err}") from err
        except ValueError as err:
            raise EcejGasApiError("IoT接口返回无法解析") from err

    async def async_get_data(self) -> dict[str, Any]:
        card = await self.async_get_bind_card()
        cardbind_id = str(card.get("cardbindID") or card.get("cardbindId") or "")
        platform_card_no = str(card.get("platformCardNo") or "")

        if not cardbind_id or not platform_card_no:
            raise EcejGasApiError("户号信息不完整")

        balance = _first((await self.async_get_balance(cardbind_id)).get("data"))
        bill = _first((await self.async_get_bill(platform_card_no)).get("data"))
        ladder = _first(bill.get("ordinaryMeterLadderList"))

        result = {
            "balance": _to_number(balance.get("billingData")),
            "meter_reading": _to_number(bill.get("thisMeterReading")),
            "last_meter_reading": _to_number(bill.get("lastTimeMeterReading")),
            "latest_bill_gas": _to_number(bill.get("thisGasConsumption")),
            "latest_bill_amount": _to_number(bill.get("totalAmount") or ladder.get("total")),
            "gas_price": _to_number(ladder.get("gasPrice")),
            "ladder": ladder.get("jTName"),
            "query_date": bill.get("sortDate") or bill.get("statementDate"),
            "meter_reading_date": bill.get("meterReadingDate"),
            "bill_status": bill.get("status"),
            "meter_type": _meter_type(card),
            "last_update_time": dt_util.now().strftime("%Y-%m-%d %H:%M:%S"),
            "cardbind_id": cardbind_id,
            "platform_only_card_no": platform_card_no,
            "pay_no": card.get("payNo"),
            "family_account_name": card.get("familyAccounName") or card.get("familyAccountName"),
            "user_name": card.get("userName"),
            "address": card.get("address"),
            "company_name": card.get("companyName"),
            "company_code": card.get("companyCode"),
            "business_type": card.get("businessType"),
            "business_name": card.get("businessName"),
            "city_id": card.get("cityId") or self._city_id,
        }

        # 如果配置了 IoT 设备信息，则附加累计/昨日用量及设备状态
        if self._device_id and self._device_type:
            try:
                device_data = _first((await self.async_get_device_detail(self._device_id, self._device_type)).get("data"))
                result["accumulate_total"] = _to_number(device_data.get("accumulateTotal"))
                result["yesterday_gas_total"] = _to_number(device_data.get("yesterdayGasTotal"))

                # 阀门状态
                valve_status_code = device_data.get("valveStatus")
                valve_map = {0: "未知", 1: "开启", 2: "关闭", 3: "强制关闭"}
                result["valve_status"] = valve_map.get(valve_status_code, "未知")

                # 报警状态（设备状态）
                alarm_status_str = str(device_data.get("alarmStatus", "0"))
                alarm_status_vos = device_data.get("alarmStatusVOS", [])
                if alarm_status_str == "0" and all(item.get("alarmStatus") == 0 for item in alarm_status_vos):
                    result["alarm_status"] = "正常"
                else:
                    alarm_texts = [item.get("statusText") for item in alarm_status_vos if item.get("alarmStatus") != 0]
                    result["alarm_status"] = ", ".join(alarm_texts) if alarm_texts else "异常"

                # 电池电量
                electricity_status_code = device_data.get("electricityStatus")
                electricity_map = {0: "未知", 1: "充足", 2: "不足", 3: "耗尽"}
                result["electricity_status"] = electricity_map.get(electricity_status_code, "未知")

                # 近 7 天 & 近 12 个月统计
                week_statistic = device_data.get("weekStatistic", [])
                month_statistic = device_data.get("monthStatistic", [])
                result["week_statistic"] = week_statistic
                result["month_statistic"] = month_statistic

                # 最近一日/一月用量（用于传感器当前值）
                if week_statistic:
                    last_week = week_statistic[-1]
                    result["week_usage"] = _to_number(last_week.get("count"))
                else:
                    result["week_usage"] = None

                if month_statistic:
                    last_month = month_statistic[-1]
                    result["month_usage"] = _to_number(last_month.get("count"))
                else:
                    result["month_usage"] = None

            except EcejGasApiError:
                # IoT 接口失败不影响主流程
                pass

        return result
