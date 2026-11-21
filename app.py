import os
from datetime import datetime
import httpx
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import asyncio

# --- НАСТРОЙКИ ---
# Токен берется из настроек Render (Environment Variables). 
# Если там пусто, берется тот, что в кавычках (для локальных тестов).
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN", "9245124017:AAHMeBKjYtKxypd5ULfwbNa-uXJLgx1ilcM")
MY_USER_IDS = [1074643832, 952028708]  # Твой ID и ID жены
CITY_LAT = 55.7558
CITY_LON = 37.6173

# --- ФУНКЦИИ (погода и Kp) ---
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
        now = datetime.now().strftime("%d.%m.%Y %H:%M")
        text = (
            f"📅 {now}\n"
            f"🌡 Температура: {temp}°C\n"
            f"💧 Влажность: {humidity}%\n"
            f"💨 Ветер: {wind} м/с\n"
            f"☔ Осадки: {precip} мм\n"
            f"📊 Давление: {pressure_mm} мм рт. ст.\n"
            f"🧲 Kp-индекс: {kp} ({storm})"
        )
        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

# --- НАСТРОЙКА TELEGRAM ---
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
telegram_app.add_handler(CommandHandler("weather", weather_command))

# --- ЯВНАЯ ИНИЦИАЛИЗАЦИЯ (Чтобы не было ошибки RuntimeError) ---
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
loop.run_until_complete(telegram_app.initialize())

# --- НАСТРОЙКА FASTAPI ---
app = FastAPI()

@app.get("/health")
async def health():
    return "OK"

@app.post(f"/{BOT_TOKEN}")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return Response(status_code=200)
