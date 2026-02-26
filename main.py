import os
from fastapi import FastAPI, Request
import requests

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = str(os.getenv("ADMIN_USER_ID")).strip()

app = FastAPI()

TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"

@app.get("/")
def home():
    return {"status": "Bot activo"}

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        user_id = str(data["message"]["from"]["id"])
        text = data["message"].get("text", "")

        if user_id != ADMIN_ID:
            return {"status": "No autorizado"}

        if text.startswith("/start"):
            send_message(chat_id, "🤖 Analista Deportivo 1x2 activo.")

        elif text.startswith("/add"):
            apuesta = text.replace("/add", "").strip()
            send_message(chat_id, f"📊 NUEVA SEÑAL\n\n{apuesta}")

    return {"ok": True}


def send_message(chat_id, text):
    requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json={"chat_id": chat_id, "text": text}
    )
