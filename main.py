import aiohttp
import asyncio
import json
import os
import feedparser
import trafilatura
import google.generativeai as genai
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot

# === Настройки ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
POSTED_FILE = "posted.json"

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-pro")
bot = Bot(token=TELEGRAM_TOKEN)

# === Функции ===

def load_posted():
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r") as f:
            return json.load(f)
    return []

def save_posted(posted):
    with open(POSTED_FILE, "w") as f:
        json.dump(posted, f)

async def fetch_hn_top():
    url = "https://hnrss.org/frontpage"
    feed = feedparser.parse(url)
    return feed.entries

async def get_full_text(url):
    downloaded = trafilatura.fetch_url(url)
    if downloaded:
        return trafilatura.extract(downloaded)
    return None

async def translate_text(text):
    prompt = f"""Переведи следующий текст на русский язык, сохранив смысл и структуру, но:
- Удали любые строки с пометками вида "(Оценка:...)" или "Re:".
- Удали дублирующиеся предложения или абзацы.
- Игнорируй технические и служебные вставки, которые не относятся к содержанию статьи.
- Оставь только связный, чистый и читабельный текст.

Текст для перевода:

{text}"""
    resp = model.generate_content(prompt)
    return resp.text.strip()

async def post_news():
    posted = load_posted()
    entries = await fetch_hn_top()

    for entry in entries:
        if entry.link in posted:
            continue  # пропускаем уже постнутые
        full_text = await get_full_text(entry.link)
        if not full_text:
            continue
        translated = await translate_text(full_text)
        message = f"🔥 *{entry.title}*\n\n{translated}\n\n🔗 {entry.link}"
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode="Markdown")
        posted.append(entry.link)
        save_posted(posted)
        break  # публикуем только одну новость за запуск

# === Планировщик ===
async def main():
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(post_news, "cron", hour=9, minute=0)
    scheduler.add_job(post_news, "cron", hour=12, minute=0)
    scheduler.add_job(post_news, "cron", hour=18, minute=0)
    scheduler.start()
    print("Бот запущен. Ждём времени постинга...")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
