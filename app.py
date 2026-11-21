import os
import threading
from flask import Flask
from bot import main as run_bot

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running"

@app.route('/health')
def health():
    return "OK"

def start_bot():
    # Запускаем вашего бота в фоновом потоке
    run_bot()

if __name__ == "__main__":
    # Запускаем бота в отдельном потоке
    bot_thread = threading.Thread(target=start_bot)
    bot_thread.start()
    
    # Запускаем веб-сервер, чтобы Render видел порт
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)