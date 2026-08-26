"""天气工具：城市提取、和风 API 数据映射与上下文格式化。"""

import asyncio
import urllib.parse

import pytest

import app.services.weather as weather_mod
from app.services.weather import (
    CityInfo,
    WeatherError,
    WeatherForecast,
    WeatherResult,
    extract_city_name,
    fetch_weather_summary,
    format_weather_context,
    resolve_city,
)


def test_extract_city_name_with_suffix_and_known_cities():
    assert extract_city_name("北京今天天气怎么样") == "北京"
    assert extract_city_name("帮我看看上海的天气") == "上海"
    assert extract_city_name("北京昌平区下雨吗") == "北京"
    assert extract_city_name("杭州明天温度多少") == "杭州"
    assert extract_city_name("你好呀今天过得怎么样") is None
    assert extract_city_name("今天心情不错") is None


def test_resolve_city_maps_to_coordinates(monkeypatch):
    monkeypatch.setattr(weather_mod, "WEATHER_API_KEY", "test-key")
    city = resolve_city("北京")
    assert city.name == "北京"
    assert city.id == "116.4074,39.9042"


def test_resolve_city_missing_city_raises(monkeypatch):
    monkeypatch.setattr(weather_mod, "WEATHER_API_KEY", "test-key")
    with pytest.raises(WeatherError) as exc:
        resolve_city("不存在的地方")
    assert exc.value.code == "city_not_found"


def test_resolve_city_disabled_without_key(monkeypatch):
    monkeypatch.setattr(weather_mod, "WEATHER_API_KEY", "")
    with pytest.raises(WeatherError) as exc:
        resolve_city("北京")
    assert exc.value.code == "weather_disabled"


def test_fetch_weather_summary_builds_result(monkeypatch):
    monkeypatch.setattr(
        weather_mod,
        "resolve_city",
        lambda name: CityInfo("101010100", "北京", "北京市"),
    )
    monkeypatch.setattr(
        weather_mod,
        "fetch_now",
        lambda cid: {
            "obsTime": "2026-08-25T08:55:00+08:00",
            "temp": "28",
            "feelsLike": "32",
            "text": "大雨",
            "windDir": "西北风",
            "windScale": "3",
            "humidity": "93",
            "pressure": "1005",
        },
    )
    monkeypatch.setattr(
        weather_mod,
        "fetch_forecast",
        lambda cid: [
            {
                "fxDate": "2026-08-25",
                "tempMin": "22",
                "tempMax": "29",
                "textDay": "雷阵雨",
                "textNight": "小雨",
            },
        ],
    )

    result = asyncio.run(fetch_weather_summary("北京"))

    assert result.city == "北京"
    assert result.province == "北京市"
    assert result.temp == "28"
    assert result.feels_like == "32"
    assert result.text == "大雨"
    assert result.wind_dir == "西北风"
    assert result.forecast[0].day == "2026-08-25"
    assert result.forecast[0].temp_min == "22"
    event = result.as_event()
    assert event["temp"] == "28"
    assert event["forecast"][0]["temp_max"] == "29"


def test_format_weather_context_uses_real_data_only():
    weather = WeatherResult(
        city="北京",
        province="北京市",
        obs_time="2026-08-25 16:55",
        temp="28",
        feels_like="32",
        text="大雨",
        wind_dir="西北风",
        wind_scale="3",
        humidity="93",
        pressure="1005",
        forecast=(WeatherForecast("2026-08-25", "22", "29", "雷阵雨", "小雨"),),
    )

    text = format_weather_context(weather)

    assert "28℃" in text
    assert "大雨" in text
    assert "西北风" in text
    assert "22" in text and "29" in text
    assert "编造" in text
