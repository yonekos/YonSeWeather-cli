# YonSeWeather

Утилита командной строки для получения текущей погоды с сервиса [OpenWeatherMap](https://openweathermap.org/).

## Требования
- Python 3.9+
- Библиотека [`requests`](https://pypi.org/project/requests/)
- API-ключ OpenWeatherMap

## Установка зависимостей
```bash
pip install requests
```

## Использование
Передайте название города в качестве аргумента или введите его по запросу. API-ключ можно указать через флаг `--api-key` или переменную окружения `OPENWEATHER_API_KEY`.

```bash
export OPENWEATHER_API_KEY="ваш_api_ключ"
python YonSeWeather.py Москва
```

Дополнительные параметры можно посмотреть через флаг `--help`.
