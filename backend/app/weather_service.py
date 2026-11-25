"""
LYFTR AI - Live Weather Service
Integrates Open-Meteo Geocoding and Forecast APIs without static/hardcoded weather data.
"""

from datetime import datetime, timezone
import httpx

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

WMO_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def describe_wmo_code(code: int | None) -> str:
    """Return a human-readable weather condition for a WMO code."""
    if code is None:
        return "Unknown"
    return WMO_CODES.get(int(code), f"Weather code {code}")


async def fetch_live_weather(location: str) -> dict:
    """
    Fetch live current weather and 5-day forecast from Open-Meteo.

    Raises ValueError if the location is empty or cannot be geocoded.
    Raises RuntimeError if Open-Meteo is unreachable or returns an invalid response.
    """
    query = (location or "").strip()
    if not query:
        raise ValueError("Location must not be empty.")

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            geo_resp = await client.get(
                GEOCODING_URL,
                params={"name": query, "count": 1, "language": "en", "format": "json"},
            )
            geo_resp.raise_for_status()
            geo_data = geo_resp.json()

            results = geo_data.get("results") or []
            if not results:
                raise ValueError(f"Location '{query}' could not be found.")

            place = results[0]
            lat = place["latitude"]
            lon = place["longitude"]
            name_parts = [place.get("name"), place.get("admin1"), place.get("country")]
            resolved_name = ", ".join(p for p in name_parts if p)

            fc_resp = await client.get(
                FORECAST_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,rain,precipitation,weather_code,wind_speed_10m",
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
                    "timezone": "auto",
                    "forecast_days": 5,
                },
            )
            fc_resp.raise_for_status()
            fc_data = fc_resp.json()
    except ValueError:
        raise
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Weather API request failed: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"Unexpected weather service error: {exc}") from exc

    current = fc_data.get("current") or {}
    daily = fc_data.get("daily") or {}

    rainfall = current.get("rain")
    if rainfall is None:
        rainfall = current.get("precipitation")

    dates = daily.get("time") or []
    codes = daily.get("weather_code") or []
    tmax = daily.get("temperature_2m_max") or []
    tmin = daily.get("temperature_2m_min") or []
    precip = daily.get("precipitation_sum") or []

    forecast = []
    for i, d in enumerate(dates):
        forecast.append({
            "date": d,
            "condition": describe_wmo_code(codes[i] if i < len(codes) else None),
            "temp_max_c": tmax[i] if i < len(tmax) else None,
            "temp_min_c": tmin[i] if i < len(tmin) else None,
            "precipitation_mm": precip[i] if i < len(precip) else None,
        })

    return {
        "query": query,
        "resolved_name": resolved_name,
        "latitude": lat,
        "longitude": lon,
        "timezone": fc_data.get("timezone", "UTC"),
        "source": "Open-Meteo",
        "fetched_at": current.get("time") or datetime.now(timezone.utc).isoformat(),
        "current": {
            "temperature_c": current.get("temperature_2m"),
            "humidity_pct": current.get("relative_humidity_2m"),
            "rainfall_mm": rainfall,
            "wind_speed_kmh": current.get("wind_speed_10m"),
            "condition": describe_wmo_code(current.get("weather_code")),
        },
        "forecast": forecast,
    }
