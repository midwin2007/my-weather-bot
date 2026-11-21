import httpx
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# === НАСТРОЙКИ ===
BOT_TOKEN = "9245124017:AAHMeBKjYtKxypd5ULfwbNa-uXJLgx1ilcM"
MY_USER_ID = 1074643832  # Замени на свой ID (узнай у @userinfobot)
CITY_LAT = 55.7558      # Широта (пример: Москва)
CITY_LON = 37.6173      # Долгота (пример: Москва)

# Проверка, что пишет именно владелец
def is_owner(update: Update) -> bool:
    return update.effective_user.id == MY_USER_ID


async def get_weather_data():
    """Получает погоду, давление, ветер, осадки и влажность с Open-Meteo."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": CITY_LAT,
        "longitude": CITY_LON,
        # Добавили новые параметры в current:
        "current": "temperature_2m,surface_pressure,weather_code,wind_speed_10m,relative_humidity_2m,precipitation",
        "wind_speed_unit": "ms",  # Запрашиваем ветер в метрах в секунду (по умолчанию км/ч)
        "timezone": "auto"
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params)
        data = resp.json()
        current = data.get("current", {})

        temp = current.get("temperature_2m")
        pressure = current.get("surface_pressure")

        # Давление в гПа -> мм рт. ст.
        pressure_mm = round(pressure * 0.75006, 1) if pressure else "?"

        # Новые данные
        wind = current.get("wind_speed_10m", "?")
        humidity = current.get("relative_humidity_2m", "?")
        precip = current.get("precipitation", 0.0)  # Осадки в мм

        return temp, pressure_mm, wind, humidity, precip


async def get_kp_index():
    """Получает текущий Kp-индекс с сервера GFZ (Потсдам)."""
    # Запрашиваем данные за последние 24 часа, чтобы точно захватить свежий индекс
    url = "https://kp.gfz.de/app/json/?start=2026-01-30T00:00:00Z&end=2026-12-31T23:59:59Z&index=Kp"

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, timeout=15.0)
            resp.raise_for_status()
            data = resp.json()

            # GFZ возвращает данные в виде списка, где последний элемент — самый свежий
            # Формат ответа: {"Kp": [2.0, 1.5, ...], "status": [...]}
            if isinstance(data, dict) and "Kp" in data and data["Kp"]:
                # Берем последнее значение из списка
                kp_value = data["Kp"][-1]
                # Округляем до одного знака после запятой
                return round(float(kp_value), 1)
            else:
                print("GFZ: Не нашли Kp в ответе")
                return "?"

        except Exception as e:
            print(f"GFZ: Ошибка получения Kp: {e}")
            return "?"
async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return

    await update.message.reply_text("Смотрю погоду и космос...")

    try:
        # ВОТ ЗДЕСЬ ДОЛЖНЫ БЫТЬ ВСЕ 5 ПЕРЕМЕННЫХ
        temp, pressure_mm, wind, humidity, precip = await get_weather_data()
        kp = await get_kp_index()

        # Оценка магнитной бури по Kp
        if isinstance(kp, (int, float)):
            if kp >= 7:
                storm = "🔴 Сильная буря"
            elif kp >= 5:
                storm = "🟠 Слабая/умеренная буря"
            else:
                storm = "🟢 Спокойно"
        else:
            storm = "данных нет"

        # Формируем красивое сообщение с эмодзи
        text = (
            f"🌡 Температура: {temp}°C\n"
            f"💧 Влажность: {humidity}%\n"
            f"💨 Ветер: {wind} м/с\n"
            f"☔ Осадки: {precip} мм\n"
            f"📊 Давление: {pressure_mm} мм рт. ст.\n"
            f"🧲 Kp-индекс: {kp} ({storm})"
        )
        await update.message.reply_text(text)
    except Exception as e:
        # Выводим ошибку в Telegram
        await update.message.reply_text(f"Ошибка: {e}")
        # И печатаем полную ошибку в консоль PyCharm для отладки
        print(f"Подробная ошибка: {e}")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("weather", weather_command))
    print("Бот запущен. Жду /weather...")
    app.run_polling()

if __name__ == "__main__":
    main()