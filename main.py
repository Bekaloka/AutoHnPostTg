import os
import requests
import trafilatura
from datetime import datetime, timedelta
import pytz
import schedule
import time
from telegram import Bot
import google.generativeai as genai

# --- Настройки токенов и чата ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or "1234567890:ABCdefGhIJKlmnOPQrstUVwxYZ"
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or "@имя_твоего_канала"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or "ВАШ_GEMINI_API_KEY"

if ":" not in TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN пустой или неверный. Укажи токен от BotFather!")

bot = Bot(token=TELEGRAM_TOKEN)

# --- Настройки Gemini API ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-pro")

# --- Память о последних постах (чтобы не было дублей) ---
posted_ids = []

# --- Получение топ-новостей с Hacker News ---
def get_top_hn_articles(limit=10):
    top_ids = requests.get("https://hacker-news.firebaseio.com/v0/topstories.json").json()
    articles = []
    for item_id in top_ids[:limit]:
        item = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json").json()
        if item and "url" in item:
            articles.append({"id": item_id, "title": item["title"], "url": item["url"]})
    return articles

# --- Скачивание и очистка текста ---
def extract_full_text(url):
    downloaded = trafilatura.fetch_url(url)
    if downloaded:
        return trafilatura.extract(downloaded)
    return None

# --- Перевод текста через Gemini ---
def translate_text(text):
    prompt = f"""
Ты — профессиональный переводчик технических новостей.
Переведи на русский язык текст ниже, сохранив стиль и смысл.
Удали мусорные комментарии, рейтинги, оценки вида (Оценка:5) и подобное.

Текст для перевода:
{text}
"""
    response = model.generate_content(prompt)
    return response.text.strip()

# --- Публикация в Telegram ---
def post_to_telegram(title, translated_text, url):
    message = f"🔥 **{title}**\n\n{translated_text}\n\n🔗 [Читать оригинал]({url})"
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode="Markdown")

# --- Основная логика ---
def job():
    global posted_ids
    print("🚀 Запуск задачи:", datetime.now(pytz.timezone("Europe/Moscow")).strftime("%Y-%m-%d %H:%M:%S"))

    articles = get_top_hn_articles(limit=10)

    count = 0
    for article in articles:
        if article["id"] in posted_ids:
            continue  # Пропускаем, если уже постили
        text = extract_full_text(article["url"])
        if text:
            translated = translate_text(text)
            post_to_telegram(article["title"], translated, article["url"])
            posted_ids.append(article["id"])
            count += 1
        if count >= 3:
            break

    # Храним только последние 30 ID
    posted_ids = posted_ids[-30:]

# --- Планировщик ---
schedule.every().day.at("09:00").do(job)
schedule.every().day.at("12:00").do(job)
schedule.every().day.at("18:00").do(job)

print("✅ Бот запущен! Ждём времени постинга...")
# Первый запуск сразу при старте бота
post_top_news()
while True:
    schedule.run_pending()
    time.sleep(30)
