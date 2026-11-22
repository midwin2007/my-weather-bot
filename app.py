import os
from datetime import datetime
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- 1. НАСТРОЙКИ И БЕЗОПАСНОСТЬ ---
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("ОШИБКА: Переменная TELEGRAM_TOKEN не задана в настройках Render!")

BASE_URL = os.environ.get("BASE_URL")
if not BASE_URL:
    # Для локальной разработки
    BASE_URL = "http://localhost:8000"

# ID берем из переменной окружения (строка "123,456" превращается в список чисел [123, 456])
# Если переменная не задана, по умолчанию будет пустой список (бот никому не ответит)
ids_str = os.environ.get("MY_USER_IDS", "")
MY_USER_IDS = [int(i) for i in ids_str.split(",")] if ids_str else []

CITY_LAT = 55.7558
CITY_LON = 37.6173

# --- 2. ФУНКЦИИ ПОГОДЫ И Kp-ИНДЕКСА ---
async def get_weather_data():
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": CITY_LAT, "longitude": CITY_LON,
        "current": "temperature_2m,surface_pressure,weather_code,wind_speed_10m,relative_humidity_2m,precipitation",
        "wind_speed_unit": "ms", "timezone": "auto"
    }
    # Используем современный способ задания таймаута
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
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
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and "Kp" in data and data["Kp"]:
                return round(float(data["Kp"][-1]), 1)
        except Exception:
            return "?"
    return "?"

async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверка, что пишет именно владелец
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

# --- 3. НАСТРОЙКА TELEGRAM ---
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
telegram_app.add_handler(CommandHandler("weather", weather_command))

# Формируем путь для вебхука
webhook_path = f"/{BOT_TOKEN}"

# --- 4. НАСТРОЙКА FASTAPI И ЗАПУСК ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Инициализируем бота
    await telegram_app.initialize()

    # Устанавливаем вебхук
    webhook_url = BASE_URL + webhook_path
    try:
        await telegram_app.bot.set_webhook(webhook_url)
        print(f"✅ Webhook успешно установлен: {webhook_url}")
    except Exception as e:
        print(f"⚠️ Ошибка установки вебхука: {e}")
        # Не прерываем запуск, если вебхук уже был настроен ранее

    yield

    # Корректно выключаем бота
    await telegram_app.shutdown()

app = FastAPI(lifespan=lifespan)

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post(webhook_path)
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return Response(status_code=200)
