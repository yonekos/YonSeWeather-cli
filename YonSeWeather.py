import requests
import time

city_name = input("Введите название города: ")
print("------------------------------")
api_key = "Your Api key from openweathermap"
weather_url = f"http://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={api_key}&units=metric&lang=ru"


response = requests.get(weather_url)
weather_data = response.json()

if weather_data["cod"] == 200:
   
    temp = weather_data["main"]["temp"] 
    feels_like = weather_data["main"]["feels_like"] 
    pressure = weather_data["main"]["pressure"] 
    humidity = weather_data["main"]["humidity"] 
    wind_speed = weather_data["wind"]["speed"] 
    wind_deg = weather_data["wind"]["deg"] 
    clouds = weather_data["clouds"]["all"] 
    description = weather_data["weather"][0]["description"] 

    
    temp_min = weather_data["main"]["temp_min"] 
    temp_max = weather_data["main"]["temp_max"] 
    visibility = weather_data["visibility"] 
    sunrise = weather_data["sys"]["sunrise"] 
    sunset = weather_data["sys"]["sunset"] 
    # преобрараразааза UNIX время в московское время 
    moscow_time_offset = 3 * 60 * 60 # смещение часового пояса Москвы от UTC в секундах
    sunrise_moscow_time = time.strftime("%H:%M:%S", time.gmtime(sunrise + moscow_time_offset))
    sunset_moscow_time = time.strftime("%H:%M:%S", time.gmtime(sunset + moscow_time_offset)) 

    # словарик
    weather_dict = {"Температура": f"{temp} °C", 
                    "Кажется что": f"{feels_like} °C",
                    "Моральное давление": f"{pressure} гПа",
                    "Влажность": f"{humidity} %",
                    "Скорость ветра": f"{wind_speed} м/с",
                    "Направление ветра куда тебя унесет": f"{wind_deg} °",
                    "Емае ОБЛАКА": f"{clouds} %",
                    "Короче": description,
                    "Минимальная температура": f"{temp_min} °C",
                    "Максимальная температура": f"{temp_max} °C",
                    "Твоя видимость": f"{visibility} м",
                    "Солнце встает в (МСК)": sunrise_moscow_time,
                    "Солнце падает в (МСК)": sunset_moscow_time}

    # вывод
    print(f"Погода от YonSe в городе {city_name}:")
    for key, value in weather_dict.items():
        print(f"{key}: {value}")



        
    print("------------------")
    input("Спасибо за использование YonSeПогода!")  

          
else:
    # если ошибка
    print(f"Погода для города {city_name} не найдена. Пожалуйста, проверьте правильность написания названия города.")

    print("------------------")
    input("Спасибо за использование YonSeПогода!")  
