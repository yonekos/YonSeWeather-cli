from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import json
from pathlib import Path

import requests
from colorama import Fore, Style, init

# Инициализация colorama для Windows
init(autoreset=True)

API_URL = "https://api.openweathermap.org/data/2.5/weather"
FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"
ONECALL_URL = "https://api.openweathermap.org/data/3.0/onecall"
AIR_QUALITY_URL = "https://api.openweathermap.org/data/2.5/air_pollution"
DEFAULT_LANGUAGE = "ru"
DEFAULT_UNITS = "metric"
DEFAULT_TIMEOUT = 10
ENV_API_KEY = "OPENWEATHER_API_KEY"
DEFAULT_API_KEY = "28d56bf4dcd8a7981f7266b0779e38b9"
CACHE_DIR = Path.home() / ".yonse_weather_cache"


UNITS_LABELS: Dict[str, Tuple[str, str]] = {
    "metric": ("°C", "м/с"),
    "imperial": ("°F", "mph"),
    "standard": ("K", "м/с"),
}


WEATHER_EMOJI = {
    "clear sky": "☀️",
    "few clouds": "🌤️",
    "scattered clouds": "⛅",
    "broken clouds": "☁️",
    "overcast clouds": "☁️",
    "shower rain": "🌧️",
    "rain": "🌧️",
    "light rain": "🌦️",
    "moderate rain": "🌧️",
    "heavy intensity rain": "⛈️",
    "thunderstorm": "⛈️",
    "snow": "❄️",
    "mist": "🌫️",
    "fog": "🌫️",
    "haze": "🌫️",
}


AIR_QUALITY_LABELS = {
    1: ("Отличное", Fore.GREEN),
    2: ("Хорошее", Fore.LIGHTGREEN_EX),
    3: ("Умеренное", Fore.YELLOW),
    4: ("Плохое", Fore.LIGHTRED_EX),
    5: ("Очень плохое", Fore.RED),
}


UV_LABELS = [
    (0, 2, "Низкий", Fore.GREEN),
    (3, 5, "Умеренный", Fore.YELLOW),
    (6, 7, "Высокий", Fore.LIGHTYELLOW_EX),
    (8, 10, "Очень высокий", Fore.LIGHTRED_EX),
    (11, float('inf'), "Экстремальный", Fore.RED),
]


class WeatherError(RuntimeError):
    """Пользовательская ошибка, означающая проблемы с получением прогноза."""


@dataclass(frozen=True)
class WeatherSnapshot:
    """Снимок погодных данных, полученных от OpenWeatherMap."""

    city: str
    country: Optional[str]
    description: str
    temperature: float
    feels_like: float
    pressure: int
    humidity: int
    wind_speed: float
    wind_direction: Optional[int]
    cloudiness: int
    temperature_min: float
    temperature_max: float
    visibility: Optional[int]
    sunrise: Optional[datetime]
    sunset: Optional[datetime]
    tz: timezone
    units: str
    uv_index: Optional[float] = None
    air_quality_index: Optional[int] = None
    air_quality_components: Optional[Dict[str, float]] = None
    weather_alerts: Optional[List[Dict[str, Any]]] = None


@dataclass(frozen=True)
class ForecastItem:
    """Один элемент прогноза погоды."""

    timestamp: datetime
    temperature: float
    feels_like: float
    description: str
    humidity: int
    wind_speed: float
    cloudiness: int
    precipitation_probability: float
    rain_volume: Optional[float] = None
    snow_volume: Optional[float] = None


def parse_arguments(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    """Разобрать аргументы командной строки."""

    parser = argparse.ArgumentParser(
        description="Получение текущей погоды из OpenWeatherMap",
    )
    parser.add_argument(
        "city",
        nargs="?",
        help="Название города (например, Москва). Если не указано — будет запрошено",  # noqa: E501
    )
    parser.add_argument(
        "--api-key",
        dest="api_key",
        help=(
            "API ключ OpenWeatherMap. Можно также задать через переменную "
            f"окружения {ENV_API_KEY}."
        ),
    )
    parser.add_argument(
        "--units",
        choices=sorted(UNITS_LABELS),
        default=DEFAULT_UNITS,
        help="Единицы измерения (metric, imperial или standard)",
    )
    parser.add_argument(
        "--lang",
        default=DEFAULT_LANGUAGE,
        help="Язык описания погоды (например, ru, en)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="Таймаут запроса к API в секундах",
    )
    parser.add_argument(
        "--forecast",
        action="store_true",
        help="Показать прогноз на 5 дней",
    )
    parser.add_argument(
        "--hourly",
        action="store_true",
        help="Показать почасовой прогноз на 24 часа",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Отключить цветной вывод",
    )
    parser.add_argument(
        "--extended",
        action="store_true",
        help="Показать расширенную информацию (UV-индекс, качество воздуха)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Не использовать кэш",
    )
    parser.add_argument(
        "--chart",
        action="store_true",
        help="Показать ASCII-график температуры",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Точка входа для утилиты."""

    args = parse_arguments(argv)

    # Отключение colorama ес над
    if args.no_color:
        init(strip=True, convert=False)

    city = args.city or input("Введите название города: ").strip()
    if not city:
        print("Название города не указано. Попробуйте снова.")
        return 1

    try:
        api_key = resolve_api_key(args.api_key)

        # Основная погода
        payload = fetch_weather(
            city=city,
            api_key=api_key,
            units=args.units,
            language=args.lang,
            timeout=args.timeout,
            use_cache=not args.no_cache,
        )
        snapshot = parse_weather_payload(payload, fallback_city=city, units=args.units)

        # Расширенные данные
        if args.extended:
            try:
                lat = payload.get("coord", {}).get("lat")
                lon = payload.get("coord", {}).get("lon")
                if lat and lon:
                    
                    air_data = fetch_air_quality(lat, lon, api_key, args.timeout)
                    snapshot = add_air_quality_to_snapshot(snapshot, air_data)

                    
                    try:
                        onecall_data = fetch_onecall(lat, lon, api_key, args.units, args.timeout)
                        snapshot = add_uv_and_alerts_to_snapshot(snapshot, onecall_data)
                    except WeatherError:
                        pass  
            except Exception as e:
                print(f"{Fore.YELLOW}⚠️  Не удалось получить расширенные данные: {e}{Style.RESET_ALL}")

        # Вывод текущей погоды
        print(format_weather(snapshot, use_color=not args.no_color))

        # Прогноз на несколько дней
        if args.forecast:
            forecast_data = fetch_forecast(
                city=city,
                api_key=api_key,
                units=args.units,
                language=args.lang,
                timeout=args.timeout,
                use_cache=not args.no_cache,
            )
            forecast_items = parse_forecast_payload(forecast_data, snapshot.tz, args.units)
            print("\n" + format_daily_forecast(forecast_items, args.units, use_color=not args.no_color))

        # Почасовой прогноз
        if args.hourly:
            forecast_data = fetch_forecast(
                city=city,
                api_key=api_key,
                units=args.units,
                language=args.lang,
                timeout=args.timeout,
                use_cache=not args.no_cache,
            )
            forecast_items = parse_forecast_payload(forecast_data, snapshot.tz, args.units)
            print("\n" + format_hourly_forecast(forecast_items, args.units, use_color=not args.no_color))

            
            if args.chart:
                chart = create_temperature_chart(forecast_items)
                if chart:
                    print("\n" + chart)

        
        elif args.chart and args.forecast:
            forecast_data = fetch_forecast(
                city=city,
                api_key=api_key,
                units=args.units,
                language=args.lang,
                timeout=args.timeout,
                use_cache=not args.no_cache,
            )
            forecast_items = parse_forecast_payload(forecast_data, snapshot.tz, args.units)
            chart = create_temperature_chart(forecast_items)
            if chart:
                print("\n" + chart)

    except WeatherError as exc:
        print(f"{Fore.RED}❌ Ошибка: {exc}{Style.RESET_ALL}")
        return 1
    except requests.RequestException as exc:
        print(f"{Fore.RED}❌ Не удалось выполнить запрос: {exc}{Style.RESET_ALL}")
        return 1

    print(f"\n{Fore.CYAN}✨ Спасибо за использование YonSeWeather! ✨{Style.RESET_ALL}")
    return 0


def resolve_api_key(cli_key: Optional[str]) -> str:
    """Получить API-ключ из аргумента или переменной окружения."""

    api_key = cli_key or os.getenv(ENV_API_KEY) or DEFAULT_API_KEY
    if not api_key:
        raise WeatherError(
            "API ключ OpenWeatherMap не указан. Передайте его через --api-key "
            f"или задайте переменную окружения {ENV_API_KEY}."
        )
    return api_key


def get_cache_path(cache_key: str) -> Path:
    """Получить путь к файлу кэша."""
    CACHE_DIR.mkdir(exist_ok=True)
    return CACHE_DIR / f"{cache_key}.json"


def load_from_cache(cache_key: str, max_age_minutes: int = 10) -> Optional[Dict[str, Any]]:
    """Загрузить данные из кэша, если они не устарели."""
    cache_path = get_cache_path(cache_key)
    if not cache_path.exists():
        return None

    try:
        cache_age = datetime.now().timestamp() - cache_path.stat().st_mtime
        if cache_age > max_age_minutes * 60:
            return None

        with cache_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return None


def save_to_cache(cache_key: str, data: Dict[str, Any]) -> None:
    """Сохранить данные в кэш."""
    try:
        cache_path = get_cache_path(cache_key)
        with cache_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except IOError:
        pass  


def fetch_weather(
    *,
    city: str,
    api_key: str,
    units: str,
    language: str,
    timeout: float,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """Выполнить запрос к OpenWeatherMap и вернуть результат в виде словаря."""

    cache_key = f"weather_{city}_{units}_{language}"
    if use_cache:
        cached = load_from_cache(cache_key)
        if cached:
            return cached

    params = {
        "q": city,
        "appid": api_key,
        "units": units,
        "lang": language,
    }

    try:
        response = requests.get(API_URL, params=params, timeout=timeout)
    except requests.RequestException as exc:  # pragma: no cover - сетевые ошибки
        raise WeatherError("Не удалось связаться с OpenWeatherMap") from exc

    data = decode_response(response)
    check_for_api_error(data, response.status_code)

    if use_cache:
        save_to_cache(cache_key, data)

    return data


def fetch_forecast(
    *,
    city: str,
    api_key: str,
    units: str,
    language: str,
    timeout: float,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """Получить прогноз погоды на 5 дней."""

    cache_key = f"forecast_{city}_{units}_{language}"
    if use_cache:
        cached = load_from_cache(cache_key, max_age_minutes=30)
        if cached:
            return cached

    params = {
        "q": city,
        "appid": api_key,
        "units": units,
        "lang": language,
    }

    try:
        response = requests.get(FORECAST_URL, params=params, timeout=timeout)
    except requests.RequestException as exc:
        raise WeatherError("Не удалось получить прогноз погоды") from exc

    data = decode_response(response)
    check_for_api_error(data, response.status_code)

    if use_cache:
        save_to_cache(cache_key, data)

    return data


def fetch_air_quality(lat: float, lon: float, api_key: str, timeout: float) -> Dict[str, Any]:
    """Получить данные о качестве воздуха."""

    params = {
        "lat": lat,
        "lon": lon,
        "appid": api_key,
    }

    try:
        response = requests.get(AIR_QUALITY_URL, params=params, timeout=timeout)
    except requests.RequestException as exc:
        raise WeatherError("Не удалось получить данные о качестве воздуха") from exc

    data = decode_response(response)
    return data


def fetch_onecall(
    lat: float, lon: float, api_key: str, units: str, timeout: float
) -> Dict[str, Any]:
    """Получить расширенные данные через OneCall API."""

    params = {
        "lat": lat,
        "lon": lon,
        "appid": api_key,
        "units": units,
        "exclude": "minutely",
    }

    try:
        response = requests.get(ONECALL_URL, params=params, timeout=timeout)
    except requests.RequestException as exc:
        raise WeatherError("Не удалось получить данные OneCall") from exc

    data = decode_response(response)
    check_for_api_error(data, response.status_code)
    return data


def decode_response(response: requests.Response) -> Dict[str, Any]:
    """Преобразовать ответ в JSON и обработать ошибки."""

    try:
        return response.json()
    except ValueError as exc:
        raise WeatherError("Не удалось разобрать ответ OpenWeatherMap") from exc


def check_for_api_error(payload: Dict[str, Any], status_code: int) -> None:
    """Проверить, что API не вернуло ошибку."""

    code = payload.get("cod", status_code)
    try:
        numeric_code = int(code)
    except (TypeError, ValueError) as exc:
        raise WeatherError(f"Некорректный код ответа API: {code!r}") from exc

    if numeric_code != 200:
        message = payload.get("message") or "Неизвестная ошибка OpenWeatherMap"
        raise WeatherError(f"OpenWeatherMap вернул ошибку: {message}")


def parse_weather_payload(
    payload: Dict[str, Any],
    *,
    fallback_city: str,
    units: str,
) -> WeatherSnapshot:
    """Построить :class:`WeatherSnapshot` из словаря с данными погоды."""

    try:
        main_block = payload["main"]
        sys_block = payload["sys"]
    except KeyError as exc:
        raise WeatherError("Ответ не содержит необходимых данных") from exc

    weather_list: List[Dict[str, Any]] = payload.get("weather") or []
    weather_details = weather_list[0] if weather_list else {}
    description = _format_description(weather_details.get("description"))

    timezone_offset = payload.get("timezone", 0)
    tz = timezone(timedelta(seconds=timezone_offset))

    sunrise = _to_local_time(sys_block.get("sunrise"), tz)
    sunset = _to_local_time(sys_block.get("sunset"), tz)

    temperature = _required_float(main_block, "temp")
    feels_like = _required_float(main_block, "feels_like")
    pressure = _required_int(main_block, "pressure")
    humidity = _required_int(main_block, "humidity")
    wind_speed = _float_with_default(_safe_get(payload.get("wind"), "speed"), default=0.0)
    wind_direction = _optional_int(_safe_get(payload.get("wind"), "deg"))
    cloudiness = _int_with_default(_safe_get(payload.get("clouds"), "all"), default=0)
    temperature_min = _float_with_default(main_block.get("temp_min"), default=temperature)
    temperature_max = _float_with_default(main_block.get("temp_max"), default=temperature)
    visibility = _optional_int(payload.get("visibility"))

    snapshot = WeatherSnapshot(
        city=payload.get("name") or fallback_city,
        country=sys_block.get("country"),
        description=description,
        temperature=temperature,
        feels_like=feels_like,
        pressure=pressure,
        humidity=humidity,
        wind_speed=wind_speed,
        wind_direction=wind_direction,
        cloudiness=cloudiness,
        temperature_min=temperature_min,
        temperature_max=temperature_max,
        visibility=visibility,
        sunrise=sunrise,
        sunset=sunset,
        tz=tz,
        units=units,
    )
    return snapshot


def _safe_get(block: Optional[Dict[str, Any]], key: str, default: Any = None) -> Any:
    """Безопасно получить значение из словаря, возвращая ``default`` если словарь пуст."""

    if not isinstance(block, dict):
        return default
    return block.get(key, default)


def _optional_int(value: Any) -> Optional[int]:
    """Преобразовать значение в ``int`` или вернуть ``None``."""

    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise WeatherError(f"Ожидалось целое число, получено {value!r}") from exc


def _required_float(block: Dict[str, Any], key: str) -> float:
    """Получить обязательное значение ``float`` из словаря."""

    try:
        value = block[key]
    except KeyError as exc:
        raise WeatherError(f"Ответ не содержит поле {key!r}") from exc
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise WeatherError(f"Некорректное значение в поле {key!r}: {value!r}") from exc


def _required_int(block: Dict[str, Any], key: str) -> int:
    """Получить обязательное значение ``int`` из словаря."""

    try:
        value = block[key]
    except KeyError as exc:
        raise WeatherError(f"Ответ не содержит поле {key!r}") from exc
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise WeatherError(f"Некорректное значение в поле {key!r}: {value!r}") from exc


def _optional_float(value: Any) -> Optional[float]:
    """Преобразовать значение в ``float`` или вернуть ``None``."""

    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise WeatherError(f"Некорректное значение: {value!r}") from exc


def _float_with_default(value: Any, *, default: float) -> float:
    """Вернуть ``float`` с использованием значения по умолчанию."""

    coerced = _optional_float(value)
    return default if coerced is None else coerced


def _int_with_default(value: Any, *, default: int) -> int:
    """Вернуть ``int`` с использованием значения по умолчанию."""

    coerced = _optional_int(value)
    return default if coerced is None else coerced


def _format_description(description: Optional[str]) -> str:
    """Отформатировать описание погоды."""

    if not description:
        return "Нет данных"
    return description.strip().capitalize()


def _to_local_time(timestamp: Optional[int], tz: timezone) -> Optional[datetime]:
    """Преобразовать Unix timestamp в локальное время."""

    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(tz)


def format_weather(snapshot: WeatherSnapshot, use_color: bool = True) -> str:
    """Превратить погодный снимок в красиво оформленный текст."""

    temp_unit, wind_unit = UNITS_LABELS.get(snapshot.units, ("°", "м/с"))
    location = snapshot.city
    if snapshot.country:
        location = f"{location}, {snapshot.country}"

    
    emoji = WEATHER_EMOJI.get(snapshot.description.lower(), "🌈")
    header = f"{emoji} Погода от YonSe в городе {location}"
    if use_color:
        header = f"{Fore.CYAN}{Style.BRIGHT}{header}{Style.RESET_ALL}"

    timezone_label = _format_timezone(snapshot.tz)

    
    temp_color = Fore.WHITE
    if use_color:
        if snapshot.temperature < 0:
            temp_color = Fore.BLUE
        elif snapshot.temperature < 10:
            temp_color = Fore.CYAN
        elif snapshot.temperature < 20:
            temp_color = Fore.GREEN
        elif snapshot.temperature < 30:
            temp_color = Fore.YELLOW
        else:
            temp_color = Fore.RED

    
    humidity_bar = create_humidity_bar(snapshot.humidity, width=25)
    wind_arrow = create_wind_arrow(snapshot.wind_direction) if snapshot.wind_direction is not None else ""

    rows: List[Tuple[str, str, str]] = [
        ("🌤️  Кратко", snapshot.description, Fore.WHITE),
        ("🌡️  Температура", f"{temp_color}{snapshot.temperature:.1f} {temp_unit}{Style.RESET_ALL if use_color else ''}", Fore.WHITE),
        ("🤔 Ощущается как", f"{temp_color}{snapshot.feels_like:.1f} {temp_unit}{Style.RESET_ALL if use_color else ''}", Fore.WHITE),
        (
            "📊 Давление",
            f"{snapshot.pressure} гПа (~{snapshot.pressure * 0.75006:.0f} мм рт. ст.)",
            Fore.WHITE,
        ),
        ("💧 Влажность", humidity_bar, Fore.LIGHTBLUE_EX if use_color else Fore.WHITE),
        ("💨 Скорость ветра", f"{snapshot.wind_speed:.1f} {wind_unit}", Fore.LIGHTCYAN_EX if use_color else Fore.WHITE),
    ]

    if snapshot.wind_direction is not None:
        rows.append(
            (
                "🧭 Направление ветра",
                f"{wind_arrow} {snapshot.wind_direction}° ({_format_wind_direction(snapshot.wind_direction)})",
                Fore.WHITE,
            )
        )

    rows.extend(
        [
            ("☁️  Облачность", f"{snapshot.cloudiness}%", Fore.WHITE),
            ("🔽 Мин. температура", f"{snapshot.temperature_min:.1f} {temp_unit}", Fore.BLUE if use_color else Fore.WHITE),
            ("🔼 Макс. температура", f"{snapshot.temperature_max:.1f} {temp_unit}", Fore.RED if use_color else Fore.WHITE),
        ]
    )

    if snapshot.visibility is not None:
        rows.append(("👁️  Видимость", _format_visibility(snapshot.visibility), Fore.WHITE))

    rows.extend(
        [
            ("🌅 Восход", _format_time(snapshot.sunrise, timezone_label), Fore.LIGHTYELLOW_EX if use_color else Fore.WHITE),
            ("🌇 Закат", _format_time(snapshot.sunset, timezone_label), Fore.LIGHTMAGENTA_EX if use_color else Fore.WHITE),
        ]
    )

    # Расширенные данные
    if snapshot.uv_index is not None:
        uv_label, uv_color = get_uv_label(snapshot.uv_index)
        uv_str = f"{snapshot.uv_index:.1f} ({uv_label})"
        if use_color:
            uv_str = f"{uv_color}{uv_str}{Style.RESET_ALL}"
        rows.append(("☀️  UV-индекс", uv_str, Fore.WHITE))

    if snapshot.air_quality_index is not None:
        aqi_label, aqi_color = AIR_QUALITY_LABELS.get(
            snapshot.air_quality_index, ("Неизвестно", Fore.WHITE)
        )
        aqi_str = f"{snapshot.air_quality_index} ({aqi_label})"
        if use_color:
            aqi_str = f"{aqi_color}{aqi_str}{Style.RESET_ALL}"
        rows.append(("🌬️  Качество воздуха", aqi_str, Fore.WHITE))

        
        if snapshot.air_quality_components:
            comp = snapshot.air_quality_components
            if "pm2_5" in comp:
                rows.append(("   • PM2.5", f"{comp['pm2_5']:.1f} μg/m³", Fore.LIGHTBLACK_EX if use_color else Fore.WHITE))
            if "pm10" in comp:
                rows.append(("   • PM10", f"{comp['pm10']:.1f} μg/m³", Fore.LIGHTBLACK_EX if use_color else Fore.WHITE))

    key_width = max(len(key) for key, _, _ in rows)
    lines = [header, "=" * 70]

    for key, value, color in rows:
        if use_color and color != Fore.WHITE and "Style.RESET_ALL" not in value:
            lines.append(f"{key:<{key_width}} : {color}{value}{Style.RESET_ALL}")
        else:
            lines.append(f"{key:<{key_width}} : {value}")

    # Предупреждения о погоде
    if snapshot.weather_alerts:
        lines.append("\n" + ("=" * 70))
        alert_header = "⚠️  ПОГОДНЫЕ ПРЕДУПРЕЖДЕНИЯ"
        if use_color:
            alert_header = f"{Fore.RED}{Style.BRIGHT}{alert_header}{Style.RESET_ALL}"
        lines.append(alert_header)
        lines.append("=" * 70)

        for alert in snapshot.weather_alerts:
            event = alert.get("event", "Предупреждение")
            description = alert.get("description", "Нет описания")
            start = alert.get("start")
            end = alert.get("end")

            if use_color:
                lines.append(f"{Fore.YELLOW}• {event}{Style.RESET_ALL}")
            else:
                lines.append(f"• {event}")

            if start and end:
                start_time = datetime.fromtimestamp(start).strftime("%d.%m %H:%M")
                end_time = datetime.fromtimestamp(end).strftime("%d.%m %H:%M")
                lines.append(f"  Период: {start_time} - {end_time}")

            lines.append(f"  {description[:200]}...")

    return "\n".join(lines)


def _format_wind_direction(degrees: int) -> str:
    """Вернуть кардинальное направление ветра по градусам."""

    directions = [
        "С", "ССВ", "СВ", "ВСВ", "В", "ВЮВ", "ЮВ", "ЮЮВ",
        "Ю", "ЮЮЗ", "ЮЗ", "ЗЮЗ", "З", "ЗСЗ", "СЗ", "ССЗ",
    ]
    index = int((degrees % 360) / 22.5 + 0.5) % len(directions)
    return directions[index]


def _format_visibility(visibility: int) -> str:
    """Форматирование видимости в метрах и километрах."""

    kilometres = visibility / 1000
    return f"{visibility} м ({kilometres:.1f} км)"


def _format_time(moment: Optional[datetime], timezone_label: str) -> str:
    """Форматировать время восхода/заката."""

    if moment is None:
        return "—"
    return f"{moment.strftime('%H:%M:%S')} ({timezone_label})"


def _format_timezone(tz: timezone) -> str:
    """Преобразовать объект ``timezone`` в строку вида UTC±HH:MM."""

    offset = tz.utcoffset(None)
    if offset is None:
        return "UTC"
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    hours, minutes = divmod(total_minutes, 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


def add_air_quality_to_snapshot(
    snapshot: WeatherSnapshot, air_data: Dict[str, Any]
) -> WeatherSnapshot:
    """Добавить данные о качестве воздуха в снимок."""
    air_list = air_data.get("list", [])
    if not air_list:
        return snapshot

    air_info = air_list[0]
    aqi = air_info.get("main", {}).get("aqi")
    components = air_info.get("components", {})

    
    return WeatherSnapshot(
        city=snapshot.city,
        country=snapshot.country,
        description=snapshot.description,
        temperature=snapshot.temperature,
        feels_like=snapshot.feels_like,
        pressure=snapshot.pressure,
        humidity=snapshot.humidity,
        wind_speed=snapshot.wind_speed,
        wind_direction=snapshot.wind_direction,
        cloudiness=snapshot.cloudiness,
        temperature_min=snapshot.temperature_min,
        temperature_max=snapshot.temperature_max,
        visibility=snapshot.visibility,
        sunrise=snapshot.sunrise,
        sunset=snapshot.sunset,
        tz=snapshot.tz,
        units=snapshot.units,
        uv_index=snapshot.uv_index,
        air_quality_index=aqi,
        air_quality_components=components,
        weather_alerts=snapshot.weather_alerts,
    )


def add_uv_and_alerts_to_snapshot(
    snapshot: WeatherSnapshot, onecall_data: Dict[str, Any]
) -> WeatherSnapshot:
    """Добавить UV-индекс и предупреждения в снимок."""
    current = onecall_data.get("current", {})
    uv_index = current.get("uvi")
    alerts = onecall_data.get("alerts", [])

    return WeatherSnapshot(
        city=snapshot.city,
        country=snapshot.country,
        description=snapshot.description,
        temperature=snapshot.temperature,
        feels_like=snapshot.feels_like,
        pressure=snapshot.pressure,
        humidity=snapshot.humidity,
        wind_speed=snapshot.wind_speed,
        wind_direction=snapshot.wind_direction,
        cloudiness=snapshot.cloudiness,
        temperature_min=snapshot.temperature_min,
        temperature_max=snapshot.temperature_max,
        visibility=snapshot.visibility,
        sunrise=snapshot.sunrise,
        sunset=snapshot.sunset,
        tz=snapshot.tz,
        units=snapshot.units,
        uv_index=uv_index,
        air_quality_index=snapshot.air_quality_index,
        air_quality_components=snapshot.air_quality_components,
        weather_alerts=alerts if alerts else None,
    )


def parse_forecast_payload(
    payload: Dict[str, Any], tz: timezone, units: str
) -> List[ForecastItem]:
    """Разобрать данные прогноза погоды."""
    forecast_list = payload.get("list", [])
    items = []

    for item in forecast_list:
        timestamp = datetime.fromtimestamp(item["dt"], tz=timezone.utc).astimezone(tz)
        main = item.get("main", {})
        weather_list = item.get("weather", [])
        weather_desc = weather_list[0].get("description", "") if weather_list else ""

        items.append(
            ForecastItem(
                timestamp=timestamp,
                temperature=main.get("temp", 0.0),
                feels_like=main.get("feels_like", 0.0),
                description=_format_description(weather_desc),
                humidity=main.get("humidity", 0),
                wind_speed=item.get("wind", {}).get("speed", 0.0),
                cloudiness=item.get("clouds", {}).get("all", 0),
                precipitation_probability=item.get("pop", 0.0) * 100,
                rain_volume=item.get("rain", {}).get("3h"),
                snow_volume=item.get("snow", {}).get("3h"),
            )
        )

    return items


def format_daily_forecast(
    items: List[ForecastItem], units: str, use_color: bool = True
) -> str:
    """Форматировать прогноз по дням."""
    if not items:
        return "Нет данных прогноза"

    temp_unit, wind_unit = UNITS_LABELS.get(units, ("°", "м/с"))

    
    days: Dict[str, List[ForecastItem]] = {}
    for item in items:
        day_key = item.timestamp.strftime("%Y-%m-%d")
        if day_key not in days:
            days[day_key] = []
        days[day_key].append(item)

    lines = []
    header = "📅 Прогноз погоды на 5 дней"
    if use_color:
        header = f"{Fore.CYAN}{Style.BRIGHT}{header}{Style.RESET_ALL}"
    lines.append(header)
    lines.append("=" * 60)

    for day_key, day_items in list(days.items())[:5]:
        date_obj = datetime.strptime(day_key, "%Y-%m-%d")
        day_name = date_obj.strftime("%A, %d %B")

        temps = [item.temperature for item in day_items]
        min_temp = min(temps)
        max_temp = max(temps)
        avg_temp = sum(temps) / len(temps)

        
        descriptions = [item.description for item in day_items]
        main_desc = max(set(descriptions), key=descriptions.count)

        
        max_precip = max(item.precipitation_probability for item in day_items)

        emoji = WEATHER_EMOJI.get(main_desc.lower(), "🌈")

        if use_color:
            day_line = f"{Fore.YELLOW}{emoji} {day_name}{Style.RESET_ALL}"
        else:
            day_line = f"{emoji} {day_name}"

        lines.append(f"\n{day_line}")
        lines.append(f"  {main_desc}")
        lines.append(f"  🌡️  Температура: {min_temp:.1f}{temp_unit} ... {max_temp:.1f}{temp_unit} (средняя {avg_temp:.1f}{temp_unit})")
        if max_precip > 10:
            lines.append(f"  💧 Вероятность осадков: {max_precip:.0f}%")

    return "\n".join(lines)


def format_hourly_forecast(
    items: List[ForecastItem], units: str, use_color: bool = True
) -> str:
    """Форматировать почасовой прогноз."""
    if not items:
        return "Нет данных прогноза"

    temp_unit, wind_unit = UNITS_LABELS.get(units, ("°", "м/с"))

    lines = []
    header = "⏰ Почасовой прогноз на 24 часа"
    if use_color:
        header = f"{Fore.CYAN}{Style.BRIGHT}{header}{Style.RESET_ALL}"
    lines.append(header)
    lines.append("=" * 80)

    
    for item in items[:8]:
        time_str = item.timestamp.strftime("%H:%M")
        emoji = WEATHER_EMOJI.get(item.description.lower(), "🌈")

        if use_color:
            time_line = f"{Fore.YELLOW}{time_str}{Style.RESET_ALL}"
        else:
            time_line = time_str

        line = f"{time_line} {emoji} {item.temperature:>5.1f}{temp_unit}  {item.description}"

        if item.precipitation_probability > 20:
            line += f"  💧 {item.precipitation_probability:.0f}%"

        lines.append(line)

    return "\n".join(lines)


def get_uv_label(uv: float) -> Tuple[str, str]:
    """Получить текстовую метку и цвет для UV-индекса."""
    for min_val, max_val, label, color in UV_LABELS:
        if min_val <= uv <= max_val:
            return label, color
    return "Неизвестно", Fore.WHITE


def create_temperature_chart(items: List[ForecastItem], width: int = 60) -> str:
    """Создать ASCII-график температуры."""
    if not items or len(items) < 2:
        return ""

    temps = [item.temperature for item in items[:8]]  
    min_temp = min(temps)
    max_temp = max(temps)
    temp_range = max_temp - min_temp if max_temp != min_temp else 1

    
    height = 10
    chart_lines = [[] for _ in range(height)]

    
    for temp in temps:
        normalized = (temp - min_temp) / temp_range
        pos = int(normalized * (height - 1))
        pos = height - 1 - pos  

        for row in range(height):
            if row == pos:
                chart_lines[row].append("●")
            elif row > pos:
                chart_lines[row].append(" ")
            else:
                chart_lines[row].append(" ")

    
    lines = []
    lines.append("📈 График температуры (24 часа)")
    lines.append("")

    for i, line in enumerate(chart_lines):
        temp_at_line = max_temp - (i / (height - 1)) * temp_range
        line_str = "".join(line)
        lines.append(f"{temp_at_line:>5.1f}° │{line_str}")

    lines.append(f"      └{'─' * len(chart_lines[0])}")

    
    times = [item.timestamp.strftime("%H:%M") for item in items[:8]]
    time_line = "        " + "  ".join(times[::2])  
    lines.append(time_line)

    return "\n".join(lines)


def create_humidity_bar(humidity: int, width: int = 30) -> str:
    """Создать горизонтальную полоску для влажности."""
    filled = int((humidity / 100) * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {humidity}%"


def create_wind_arrow(degrees: int) -> str:
    """Создать стрелку направления ветра."""
    arrows = ["↓", "↙", "←", "↖", "↑", "↗", "→", "↘"]
    index = int((degrees % 360) / 45)
    return arrows[index]


if __name__ == "__main__":
    sys.exit(main())

