"""Утилита командной строки для получения прогноза погоды с OpenWeatherMap.

Пример использования:

    $ python YonSeWeather.py Москва

API-ключ можно передать через аргумент ``--api-key`` или переменную окружения
``OPENWEATHER_API_KEY``.
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

API_URL = "https://api.openweathermap.org/data/2.5/weather"
DEFAULT_LANGUAGE = "ru"
DEFAULT_UNITS = "metric"
DEFAULT_TIMEOUT = 10
ENV_API_KEY = "OPENWEATHER_API_KEY"

# Карта единиц измерения для различных режимов OpenWeatherMap.
UNITS_LABELS: Dict[str, Tuple[str, str]] = {
    "metric": ("°C", "м/с"),
    "imperial": ("°F", "mph"),
    "standard": ("K", "м/с"),
}


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
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Точка входа для утилиты."""

    args = parse_arguments(argv)
    city = args.city or input("Введите название города: ").strip()
    if not city:
        print("Название города не указано. Попробуйте снова.")
        return 1

    try:
        api_key = resolve_api_key(args.api_key)
        payload = fetch_weather(
            city=city,
            api_key=api_key,
            units=args.units,
            language=args.lang,
            timeout=args.timeout,
        )
        snapshot = parse_weather_payload(payload, fallback_city=city, units=args.units)
    except WeatherError as exc:
        print(f"Ошибка: {exc}")
        return 1
    except requests.RequestException as exc:
        print(f"Не удалось выполнить запрос: {exc}")
        return 1

    print(format_weather(snapshot))
    print("Спасибо за использование YonSeWeather!")
    return 0


def resolve_api_key(cli_key: Optional[str]) -> str:
    """Получить API-ключ из аргумента или переменной окружения."""

    api_key = cli_key or os.getenv(ENV_API_KEY)
    if not api_key:
        raise WeatherError(
            "API ключ OpenWeatherMap не указан. Передайте его через --api-key "
            f"или задайте переменную окружения {ENV_API_KEY}."
        )
    return api_key


def fetch_weather(
    *,
    city: str,
    api_key: str,
    units: str,
    language: str,
    timeout: float,
) -> Dict[str, Any]:
    """Выполнить запрос к OpenWeatherMap и вернуть результат в виде словаря."""

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


def format_weather(snapshot: WeatherSnapshot) -> str:
    """Превратить погодный снимок в красиво оформленный текст."""

    temp_unit, wind_unit = UNITS_LABELS.get(snapshot.units, ("°", "м/с"))
    location = snapshot.city
    if snapshot.country:
        location = f"{location}, {snapshot.country}"

    header = f"Погода от YonSe в городе {location}"
    timezone_label = _format_timezone(snapshot.tz)

    rows: List[Tuple[str, str]] = [
        ("Кратко", snapshot.description),
        ("Температура", f"{snapshot.temperature:.1f} {temp_unit}"),
        ("Ощущается как", f"{snapshot.feels_like:.1f} {temp_unit}"),
        (
            "Давление",
            f"{snapshot.pressure} гПа (~{snapshot.pressure * 0.75006:.0f} мм рт. ст.)",
        ),
        ("Влажность", f"{snapshot.humidity}%"),
        ("Скорость ветра", f"{snapshot.wind_speed:.1f} {wind_unit}"),
    ]

    if snapshot.wind_direction is not None:
        rows.append(
            (
                "Направление ветра",
                f"{snapshot.wind_direction}° ({_format_wind_direction(snapshot.wind_direction)})",
            )
        )

    rows.extend(
        [
            ("Облачность", f"{snapshot.cloudiness}%"),
            ("Мин. температура", f"{snapshot.temperature_min:.1f} {temp_unit}"),
            ("Макс. температура", f"{snapshot.temperature_max:.1f} {temp_unit}"),
        ]
    )

    if snapshot.visibility is not None:
        rows.append(("Видимость", _format_visibility(snapshot.visibility)))

    rows.extend(
        [
            ("Восход", _format_time(snapshot.sunrise, timezone_label)),
            ("Закат", _format_time(snapshot.sunset, timezone_label)),
        ]
    )

    key_width = max(len(key) for key, _ in rows)
    lines = [header, "-" * len(header)]
    lines.extend(f"{key:<{key_width}} : {value}" for key, value in rows)
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


if __name__ == "__main__":
    sys.exit(main())
