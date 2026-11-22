import os
import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import asyncio 

# --- 1. НАСТРОЙКИ И БЕЗОПАСНОСТЬ ---
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("ОШИБКА: Переменная TELEGRAM_TOKEN не задана в настройках Render!")

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")

# Безопасный парсинг ID пользователей
ids_str = os.environ.get("MY_USER_IDS", "")
MY_USER_IDS = [int(i.strip()) for i in ids_str.split(",") if i.strip().isdigit()]

CITY_LAT = 55.7558
CITY_LON = 37.6173
MSK_TZ = ZoneInfo("Europe/Moscow")

# --- 2. ФУНКЦИИ ПОГОДЫ И Kp-ИНДЕКСА ---
import asyncio  # добавьте, если ещё не импортирован

async def get_weather_data():
    # wttr.in не требует ключей, просто передаем координаты
    url = f"https://wttr.in/{CITY_LAT},{CITY_LON}?format=j1"
    
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        
        # Данные у wttr.in лежат в другом месте, извлекаем нужное
        current = data.get("current_condition", [{}])[0]
        
        # Температура (в °C)
        temp = current.get("temp_C")
        
        # Давление (в wttr.in оно в гПа, переводим в мм рт. ст.)
        pressure = current.get("pressure")
        pressure_mm = round(float(pressure) * 0.75006, 1) if pressure else "?"
        
        # Ветер в м/с (в ответе API он в км/ч, делим на 3.6)
        wind_kmph = current.get("windspeedKmph")
        wind = round(float(wind_kmph) / 3.6, 1) if wind_kmph else "?"
        
        # Влажность
        humidity = current.get("humidity", "?")
        
        # Осадки за последний час (в мм)
        precip = current.get("precipMM", 0.0)
        
        return temp, pressure_mm, wind, humidity, precip
    raise Exception("Погодный сервис временно перегружен. Попробуйте через минуту.")
    
async def get_kp_index():
    # Формируем даты динамически, чтобы не зависеть от года
    from datetime import datetime, timedelta, timezone
    now_utc = datetime.now(timezone.utc)
    start_str = (now_utc - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    url = f"https://kp.gfz.de/app/json/?start={start_str}&end={end_str}&index=Kp"
    
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and "Kp" in data:
                valid_kp = [x for x in data["Kp"] if x is not None]
                if valid_kp:
                    return round(float(valid_kp[-1]), 1)
        except Exception as e:
            print(f"⚠️ Ошибка получения Kp-индекса: {e}")
    return "?"

async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id not in MY_USER_IDS:
        return

    await update.message.reply_text("Смотрю погоду и космос...")
    try:
        # Вызываем функции БЕЗ аргументов, так как они сами создают клиента
        weather_res, kp = await asyncio.gather(
            get_weather_data(),
            get_kp_index()
        )
        
        temp, pressure_mm, wind, humidity, precip = weather_res

        if isinstance(kp, (int, float)):
            if kp >= 7:
                storm = "🔴 Сильная буря"
            elif kp >= 5:
                storm = "🟠 Слабая/умеренная буря"
            else:
                storm = "🟢 Спокойно"
        else:
            storm = "данных нет"

        now_msk = datetime.now(MSK_TZ).strftime("%d.%m.%Y %H:%M")

        text = (
            f"📅 {now_msk} (МСК)\n"
            f"🌡 Температура: {temp}°C\n"
            f"💧 Влажность: {humidity}%\n"
            f"💨 Ветер: {wind} м/с\n"
            f"☔ Осадки: {precip} мм\n"
            f"📊 Давление: {pressure_mm} мм рт. ст.\n"
            f"🧲 Kp-индекс: {kp} ({storm})"
        )
        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"Ошибка при получении данных: {e}")
        
# --- 3. НАСТРОЙКА TELEGRAM ---
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
telegram_app.add_handler(CommandHandler("weather", weather_command))

webhook_path = f"/{BOT_TOKEN}"

# --- 4. НАСТРОЙКА FASTAPI И ЗАПУСК ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    await telegram_app.initialize()
    await telegram_app.start()

    webhook_url = f"{BASE_URL}{webhook_path}"
    try:
        await telegram_app.bot.set_webhook(webhook_url)
        print(f"✅ Webhook успешно установлен: {webhook_url}")
    except Exception as e:
        print(f"⚠️ Ошибка установки вебхука: {e}")

    yield

    await telegram_app.stop()
    await telegram_app.shutdown()

app = FastAPI(lifespan=lifespan)

#@app.get("/health")
#async def health():
#    return {"status": "ok"}

@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return {"status": "ok"}

@app.post(webhook_path)
async def webhook(request: Request):
    # Страховка на случай холодного старта на Render
    if not telegram_app._initialized:
        await telegram_app.initialize()
        await telegram_app.start()

    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return Response(status_code=200)
