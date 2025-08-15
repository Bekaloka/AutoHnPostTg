import os
import requests
import schedule
import time
from datetime import datetime, timedelta
from telegram import Bot
import trafilatura

# --- Твои данные ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

bot = Bot(token=TELEGRAM_TOKEN)
posted_ids = set()  # Чтобы не постить дубли

# --- Функция перевода через Gemini ---
def translate_text(text):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"
    prompt = f"Переведи следующий текст на русский язык, убрав лишние оценки, баллы и комментарии, сохрани только основной смысл:\n\n{text}"
    resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]})
    if resp.status_code == 200:
        try:
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        except:
            return text
    else:
        return text

# --- Получаем топ новости ---
def get_top_news(limit=3):
    url = "https://hacker-news.firebaseio.com/v0/topstories.json"
    ids = requests.get(url).json()
    news_list = []
    for story_id in ids:
        if len(news_list) >= limit * 2:  # запас, если будут дубли
            break
        if story_id in posted_ids:
            continue
        story_url = f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
        story_data = requests.get(story_url).json()
        if not story_data or "url" not in story_data:
            continue
        # Скачиваем и чистим текст
        html = requests.get(story_data["url"], timeout=10).text
        text = trafilatura.extract(html)
        if not text:
            continue
        news_list.append({
            "id": story_id,
            "title": story_data.get("title", "Без заголовка"),
            "url": story_data["url"],
            "text": text
        })
    return news_list

# --- Постим новости ---
def post_top_news():
    global posted_ids
    news_items = get_top_news(limit=3)
    count = 0
    for item in news_items:
        if item["id"] in posted_ids:
            continue
        translated = translate_text(item["text"])
        message = f"🔥 **{item['title']}**\n\n{translated}\n\n🔗 Читать: {item['url']}"
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode="Markdown")
        posted_ids.add(item["id"])
        count += 1
        if count >= 3:
            break

# --- Ставим расписание (МСК) ---
def schedule_jobs():
    moscow_offset = 3  # UTC+3
    for t in ["09:00", "12:00", "18:00"]:
        schedule.every().day.at(t).do(post_top_news)

# --- Запуск ---
if __name__ == "__main__":
    post_top_news()  # Постим сразу при старте
    schedule_jobs()
    while True:
        schedule.run_pending()
        time.sleep(30)
