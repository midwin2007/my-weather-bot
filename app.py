import os
from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import httpx
from datetime import datetime

# --- НАСТРОЙКИ (скопируйте сюда ваши значения) ---
BOT_TOKEN = os.environ.get("9245124017:AAHMeBKjYtKxypd5ULfwbNa-uXJLgx1ilcM")
MY_USER_IDS = [1074643832, 952028708] # Замените на ваши реальные ID
CITY_LAT = 55.7558
CITY_LON = 37.6173

# --- ВАШИ ФУНКЦИИ (погода и Kp) ---
async def get_weather_data():
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": CITY_LAT, "longitude": CITY_LON,
        "current": "temperature_2m,surface_pressure,weather_code,wind_speed_10m,relative_humidity_2m,precipitation",
        "wind_speed_unit": "ms", "timezone": "auto"
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params)
        data = resp.json()
        current = data.get("current", {})
        temp = current.get("temperature_2m")
        pressure = current.get("surface_pressure")
        pressure_mm = round(pressure * 0.75006, 1) if pressure else "?"
        wind = current.get("wind_speed_10m", "?")
        humidity = current.get("relative_humidity_2m", "?")
        precip = current.get("precipitation", 0.0)
        return temp, pressure_mm, wind, humidity, precip

async def get_kp_index():
    url = "https://kp.gfz.de/app/json/?start=2026-01-30T00:00:00Z&end=2026-12-31T23:59:59Z&index=Kp"
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, timeout=15.0)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and "Kp" in data and data["Kp"]:
                return round(float(data["Kp"][-1]), 1)
        except Exception:
            return "?"
    return "?"

async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in MY_USER_IDS:
        return
    await update.message.reply_text("Смотрю погоду и космос...")
    try:
        temp, pressure_mm, wind, humidity, precip = await get_weather_data()
        kp = await get_kp_index()
        if isinstance(kp, (int, float)):
            storm = "🔴 Сильная буря" if kp >= 7 else ("🟠 Слабая/умеренная буря" if kp >= 5 else "🟢 Спокойно")
        else:
            storm = "данных нет"
        text = (f"🌡 Температура: {temp}°C\n💧 Влажность: {humidity}%\n💨 Ветер: {wind} м/с\n"
                f"☔ Осадки: {precip} мм\n📊 Давление: {pressure_mm} мм рт. ст.\n🧲 Kp-индекс: {kp} ({storm})")
        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

# --- FLASK ПРИЛОЖЕНИЕ ---
app = Flask(__name__)
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
telegram_app.add_handler(CommandHandler("weather", weather_command))

@app.route('/health')
def health():
    return "OK"

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
async def webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), telegram_app.bot)
        await telegram_app.process_update(update)
        return "ok", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
