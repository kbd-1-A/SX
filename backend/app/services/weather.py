"""天气查询工具：和风天气 QWeather（账号专属 API Host）。

模型不会获得任意网络能力。聊天层只能调用这里受限的天气查询：城市解析、
实时天气、3 日预报；结果必须是 API 真实返回的数据，禁止模型编造温度、
降水或预报。未配置 API Key 时抛出可展示的 WeatherError。

说明：和风新版控制台（Console V4）的专属 API Host 上，GeoAPI 城市搜索
端点（geo/lookup）不可用/受限，因此城市解析改为内置常用城市经纬度表，
实时与预报接口直接使用经纬度查询。
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import re
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

# 常用城市经纬度（近似市中心坐标）。和风专属 API Host 的 GeoAPI 不可用，
# 天气接口直接用经纬度查询（location=经度,纬度）。
_CITY_COORDS: dict[str, tuple[float, float]] = {
    "北京": (116.4074, 39.9042),
    "上海": (121.4737, 31.2304),
    "天津": (117.2009, 39.0842),
    "重庆": (106.5516, 29.5630),
    "广州": (113.2644, 23.1291),
    "深圳": (114.0579, 22.5431),
    "杭州": (120.1551, 30.2741),
    "成都": (104.0665, 30.5723),
    "武汉": (114.3054, 30.5931),
    "西安": (108.9398, 34.3416),
    "南京": (118.7969, 32.0603),
    "苏州": (120.5853, 31.2989),
    "长沙": (112.9388, 28.2282),
    "郑州": (113.6254, 34.7466),
    "青岛": (120.3826, 36.0671),
    "大连": (121.6147, 38.9140),
    "厦门": (118.0894, 24.4798),
    "福州": (119.2965, 26.0745),
    "济南": (117.1201, 36.6512),
    "合肥": (117.2272, 31.8206),
    "昆明": (102.8329, 24.8801),
    "南昌": (115.8582, 28.6829),
    "贵阳": (106.6302, 26.6470),
    "南宁": (108.3669, 22.8170),
    "海口": (110.1999, 20.0444),
    "石家庄": (114.5149, 38.0428),
    "太原": (112.5489, 37.8706),
    "呼和浩特": (111.7492, 40.8426),
    "沈阳": (123.4315, 41.8057),
    "长春": (125.3235, 43.8171),
    "哈尔滨": (126.5349, 45.8038),
    "乌鲁木齐": (87.6168, 43.8256),
    "拉萨": (91.1409, 29.6456),
    "西宁": (101.7782, 36.6171),
    "银川": (106.2309, 38.4872),
    "兰州": (103.8343, 36.0611),
    "宁波": (121.5503, 29.8746),
    "无锡": (120.3119, 31.4912),
    "佛山": (113.1214, 23.0215),
    "东莞": (113.7518, 23.0207),
    "珠海": (113.5767, 22.2707),
    "温州": (120.6994, 27.9943),
    "泉州": (118.6759, 24.8741),
    "南通": (120.8943, 31.9802),
    "常州": (119.9741, 31.8107),
    "嘉兴": (120.7555, 30.7469),
    "绍兴": (120.5802, 30.0304),
    "烟台": (121.4479, 37.4638),
    "潍坊": (119.1618, 36.7069),
    "临沂": (118.3564, 35.1047),
    "洛阳": (112.4540, 34.6197),
    "襄阳": (112.1224, 32.0090),
    "宜昌": (111.2865, 30.6919),
    "汕头": (116.6819, 23.3541),
    "湛江": (110.3594, 21.2707),
    "中山": (113.3928, 22.5176),
    "惠州": (114.4162, 23.1115),
    "江门": (113.0816, 22.5791),
    "三亚": (109.5119, 18.2528),
    "桂林": (110.2900, 25.2736),
    "柳州": (109.4159, 24.3255),
    "遵义": (106.9272, 27.7257),
    "绵阳": (104.6796, 31.4675),
    "德阳": (104.3979, 31.1268),
    "乐山": (103.7656, 29.5521),
    "宜宾": (104.6430, 28.7513),
    "泸州": (105.4423, 28.8718),
    "大理": (100.2677, 25.6065),
    "丽江": (100.2278, 26.8550),
    "咸阳": (108.7089, 34.3296),
    "宝鸡": (107.2373, 34.3619),
    "芜湖": (118.4331, 31.3525),
    "蚌埠": (117.3892, 32.9163),
    "安庆": (117.0638, 30.5435),
    "六安": (116.5219, 31.7337),
    "阜阳": (115.8140, 32.8905),
    "赣州": (114.9350, 25.8311),
    "九江": (116.0019, 29.7051),
    "上饶": (117.9434, 28.4549),
    "景德镇": (117.1784, 29.2687),
    "萍乡": (113.8546, 27.6229),
}


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
    """从用户消息提取城市名：优先「XX区/县」，再「XX市」，再常见城市词表。

    区县剥离城市前缀后若不在内置坐标表，则回退到所属城市（如
    "北京昌平区"→"昌平区"不在表→返回"北京"），保证能查到坐标。
    """
    district = re.search(r"([\u4e00-\u9fff]{1,6}?(?:区|县))", text)
    if district:
        name = district.group(1)
        for city in _CITY_NAMES:
            if name.startswith(city) and len(name) > len(city):
                district_name = name[len(city):]
                if district_name in _CITY_COORDS:
                    return district_name
                return city
        if name in _CITY_COORDS:
            return name
        for city in _CITY_NAMES:
            if city in text:
                return city
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
            raw = response.read()
            if response.headers.get("Content-Encoding", "").lower() == "gzip":
                raw = gzip.decompress(raw)
            payload = json.loads(raw.decode("utf-8"))
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
    """城市名 → 经纬度（内置常用城市表）。

    和风新版控制台（Console V4）的账号专属 API Host 上 GeoAPI（geo/lookup）
    不可用，因此城市解析改用内置经纬度表；实时与预报接口直接以经纬度查询。
    """
    if not WEATHER_ENABLED or not WEATHER_API_KEY:
        raise WeatherError("天气功能还没有配置 API Key，暂时查不了天气。", "weather_disabled")
    coords = _CITY_COORDS.get(name)
    if coords is None:
        raise WeatherError(
            f"暂时支持常用城市查询，没找到「{name}」，换个城市试试。", "city_not_found"
        )
    lon, lat = coords
    return CityInfo(id=f"{lon:.4f},{lat:.4f}", name=name, province="")


def fetch_now(city_id: str) -> dict:
    url = f"{WEATHER_API_BASE}/weather/now?location={city_id}&key={WEATHER_API_KEY}"
    payload = _get_json(url)
    now = payload.get("now") or {}
    if not now:
        raise WeatherError("实时天气数据为空。", "weather_no_data")
    return now


def fetch_forecast(city_id: str, days: int = 3) -> list[dict]:
    url = f"{WEATHER_API_BASE}/weather/3d?location={city_id}&key={WEATHER_API_KEY}"
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
