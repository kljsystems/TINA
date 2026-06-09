"""TINA Tool — Weather (OpenWeatherMap)"""
from config import OPENWEATHER_API_KEY

DEFINITIONS = [{
    "name": "get_weather",
    "description": "Get current weather for a city. Use when asked about weather, temperature, rain, or what to wear.",
    "input_schema": {"type":"object","properties":{"city":{"type":"string","description":"City name e.g. 'Sydney,AU'. Leave empty for default."}},"required":[]}
}]

DEFAULT_CITY = "Sydney,AU"

def handle(name: str, inputs: dict) -> str:
    city = inputs.get("city","").strip() or DEFAULT_CITY
    if not OPENWEATHER_API_KEY:
        return f"OpenWeatherMap not configured."
    try:
        import requests
        r = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q":city,"appid":OPENWEATHER_API_KEY,"units":"metric"},
            timeout=8
        )
        r.raise_for_status()
        d = r.json()
        return (
            f"Weather in {d['name']}, {d['sys']['country']}: "
            f"{d['weather'][0]['description'].capitalize()}, "
            f"{d['main']['temp']:.1f}°C (feels like {d['main']['feels_like']:.1f}°C), "
            f"humidity {d['main']['humidity']}%, wind {round(d['wind']['speed']*3.6,1)} km/h"
        )
    except Exception as e:
        return f"Weather fetch failed: {e}"