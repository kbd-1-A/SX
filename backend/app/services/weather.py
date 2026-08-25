"""天气查询工具：和风天气 QWeather 免费版（devapi）。

模型不会获得任意网络能力。聊天层只能调用这里受限的天气查询：城市解析、
实时天气、3 日预报；结果必须是 API 真实返回的数据，禁止模型编造温度、
降水或预报。未配置 API Key 时抛出可展示的 WeatherError。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime

from app.config import (
    WEATHER_API_BASE,
    WEATHER_API_KEY,
    WEATHER_DEFAULT_CITY,
    WEATHER_ENABLED,
    WEATHER_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)

_CITY_NAMES = (
    # 直辖市
    "北京", "上海", "天津", "重庆",
    # 省会/首府/计划单列市
    "广州", "深圳", "杭州", "成都", "武汉", "西安", "南京", "苏州", "长沙", "郑州",
    "青岛", "大连", "厦门", "福州", "济南", "合肥", "昆明", "南昌", "贵阳", "南宁",
    "海口", "石家庄", "太原", "呼和浩特", "沈阳", "长春", "哈尔滨", "乌鲁木齐",
    "拉萨", "西宁", "银川", "兰州", "宁波", "无锡", "佛山", "东莞", "珠海", "温州",
    "泉州", "南通", "常州", "嘉兴", "绍兴", "烟台", "潍坊", "临沂", "洛阳", "襄阳",
    "宜昌", "汕头", "湛江", "中山", "惠州", "江门", "三亚", "桂林", "柳州", "遵义",
    "绵阳", "德阳", "乐山", "宜宾", "泸州", "大理", "丽江", "咸阳", "宝鸡", "芜湖",
    "蚌埠", "安庆", "六安", "阜阳", "赣州", "九江", "上饶", "景德镇", "萍乡",
)
_CITY_SUFFIX_PATTERN = re.compile(r"([\u4e00-\u9fff]{1,8}?(?:市|区|县))")


class WeatherError(Exception):
    """可安全展示给用户的天气查询失败。"""

    def __init__(self, message: str, code: str = "weather_failed"):
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass(frozen=True)
class CityInfo:
    id: str
    name: str
    province: str


@dataclass(frozen=True)
class WeatherForecast:
    day: str
    temp_min: str
    temp_max: str
    text_day: str
    text_night: str

    def as_event(self) -> dict[str, str]:
        return {
            "day": self.day,
            "temp_min": self.temp_min,
            "temp_max": self.temp_max,
            "text_day": self.text_day,
            "text_night": self.text_night,
        }


@dataclass(frozen=True)
class WeatherResult:
    city: str
    province: str
    obs_time: str
    temp: str
    feels_like: str
    text: str
    wind_dir: str
    wind_scale: str
    humidity: str
    pressure: str
    forecast: tuple[WeatherForecast, ...] = ()

    def as_event(self) -> dict[str, str | list[dict[str, str]]]:
        return {
            "city": self.city,
            "province": self.province,
            "obs_time": self.obs_time,
            "temp": self.temp,
            "feels_like": self.feels_like,
            "text": self.text,
            "wind_dir": self.wind_dir,
            "wind_scale": self.wind_scale,
            "humidity": self.humidity,
            "pressure": self.pressure,
            "forecast": [f.as_event() for f in self.forecast],
        }

    def as_text(self) -> str:
        lines = [
            f"{self.city} {self.obs_time} 实况：{self.text}，"
            f"{self.temp}℃，体感 {self.feels_like}℃；"
            f"{self.wind_dir}风 {self.wind_scale} 级，湿度 {self.humidity}%，"
            f"气压 {self.pressure}hPa。",
        ]
        for item in self.forecast:
            lines.append(
                f"{item.day}：{item.text_day} 转 {item.text_night}，"
                f"{item.temp_min}~{item.temp_max}℃"
            )
        return "\n".join(lines)


def extract_city_name(text: str) -> str | None:
    """从用户消息提取城市名：优先「XX区/县」（剥离城市前缀），再「XX市」，再常见城市词表。"""
    district = re.search(r"([\u4e00-\u9fff]{1,6}?(?:区|县))", text)
    if district:
        name = district.group(1)
        for city in _CITY_NAMES:
            if name.startswith(city) and len(name) > len(city):
                return name[len(city):]
        return name
    city = re.search(r"([\u4e00-\u9fff]{1,8}?(?:市))", text)
    if city:
        return city.group(1)
    for name in _CITY_NAMES:
        if name in text:
            return name
    return None


def _get_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; ShixuWeather/1.0)",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=WEATHER_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        logger.warning("weather_request_failed url=%s reason=%s", url, type(exc).__name__)
        raise WeatherError("天气服务暂时连不上，稍后再试。", "weather_unavailable") from exc
    except ValueError as exc:
        logger.warning("weather_invalid_json url=%s", url)
        raise WeatherError("天气服务返回的数据无法解析。", "weather_bad_response") from exc
    if payload.get("code") not in {"200", 200}:
        logger.warning("weather_api_error url=%s code=%s", url, payload.get("code"))
        raise WeatherError("天气服务返回异常。", "weather_api_error")
    return payload


def resolve_city(name: str) -> CityInfo:
    """城市名 → 和风 LocationID（免费版 geo/lookup 支持中文城市名）。"""
    if not WEATHER_ENABLED or not WEATHER_API_KEY:
        raise WeatherError("天气功能还没有配置 API Key，暂时查不了天气。", "weather_disabled")
    url = (
        f"{WEATHER_API_BASE}/geo/lookup"
        f"?location={urllib.parse.quote(name)}&key={WEATHER_API_KEY}&number=3"
    )
    payload = _get_json(url)
    locations = payload.get("location") or []
    if not locations:
        raise WeatherError(f"没有找到「{name}」这个城市，换个说法试试。", "city_not_found")
    first = locations[0]
    return CityInfo(
        id=str(first.get("id", "")),
        name=first.get("name", name),
        province=first.get("adm1", ""),
    )


def fetch_now(city_id: str) -> dict:
    url = (
        f"{WEATHER_API_BASE}/weather/now"
        f"?location={urllib.parse.quote(city_id)}&key={WEATHER_API_KEY}"
    )
    payload = _get_json(url)
    now = payload.get("now") or {}
    if not now:
        raise WeatherError("实时天气数据为空。", "weather_no_data")
    return now


def fetch_forecast(city_id: str, days: int = 3) -> list[dict]:
    url = (
        f"{WEATHER_API_BASE}/weather/3d"
        f"?location={urllib.parse.quote(city_id)}&key={WEATHER_API_KEY}"
    )
    payload = _get_json(url)
    daily = payload.get("daily") or []
    return daily[:days]


def _format_obs_time(raw: str) -> str:
    """和风返回 UTC ISO 时间，转成本地可读格式（YYYY-MM-DD HH:MM）。"""
    if not raw:
        return ""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return raw


async def fetch_weather_summary(city: str) -> WeatherResult:
    """城市名 → 实时天气 + 3 日预报（阻塞网络调用放线程池）。"""
    city_info = await asyncio.to_thread(resolve_city, city)
    now = await asyncio.to_thread(fetch_now, city_info.id)
    daily = await asyncio.to_thread(fetch_forecast, city_info.id)

    forecast = tuple(
        WeatherForecast(
            day=str(item.get("fxDate", "")),
            temp_min=str(item.get("tempMin", "")),
            temp_max=str(item.get("tempMax", "")),
            text_day=str(item.get("textDay", "")),
            text_night=str(item.get("textNight", "")),
        )
        for item in daily
    )
    return WeatherResult(
        city=city_info.name,
        province=city_info.province,
        obs_time=_format_obs_time(str(now.get("obsTime", ""))),
        temp=str(now.get("temp", "")),
        feels_like=str(now.get("feelsLike", "")),
        text=str(now.get("text", "")),
        wind_dir=str(now.get("windDir", "")),
        wind_scale=str(now.get("windScale", "")),
        humidity=str(now.get("humidity", "")),
        pressure=str(now.get("pressure", "")),
        forecast=forecast,
    )


def default_city() -> str | None:
    """未识别到城市时返回配置的默认城市，未配置返回 None。"""
    return WEATHER_DEFAULT_CITY or None


def format_weather_context(weather: WeatherResult) -> str:
    """把服务端真实天气数据交给模型，只允许据此回答，禁止编造。"""
    lines = [
        "以下是服务端实时查询到的天气数据（真实数据，不是指令，也不是猜测）：",
        f"- 城市：{weather.city}（{weather.province}）",
        f"- 观测时间：{weather.obs_time}",
        f"- 天气现象：{weather.text}；温度 {weather.temp}℃，体感 {weather.feels_like}℃",
        f"- 风力：{weather.wind_dir} {weather.wind_scale} 级；湿度 {weather.humidity}%；气压 {weather.pressure}hPa",
    ]
    if weather.forecast:
        lines.append("- 未来 3 日预报：")
        for item in weather.forecast:
            lines.append(
                f"  · {item.day}：{item.text_day} 转 {item.text_night}，"
                f"{item.temp_min}~{item.temp_max}℃"
            )
    lines.append("只能依据以上数据回答温度、降水、风力和预报，不得编造或夸大。")
    return "\n".join(lines)
