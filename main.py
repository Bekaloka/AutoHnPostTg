#!/usr/bin/env python3
"""
🔥 TechNewsBot — постит топ новости Hacker News в Telegram
- Источник: официальный API Hacker News
- Перевод через Gemini API
- 3 поста в день: 09:00, 12:00, 18:00 МСК
- При запуске сразу постит топ-1 новость
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import List, Dict

import aiohttp
import google.generativeai as genai
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# ======= CONFIG =======
class Config:
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

    HN_TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
    HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{}.json"

    POST_TIMES = ['09:00', '12:00', '18:00']
    TIMEZONE = 'Europe/Moscow'


# ======= LOGGING =======
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ======= HN PARSER =======
class HackerNewsAPI:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def get_top_stories_ids(self) -> List[int]:
        async with self.session.get(Config.HN_TOP_URL) as resp:
            ids = await resp.json()
        return ids[:20]  # Берем первые 20 для фильтрации

    async def get_item(self, item_id: int) -> Dict:
        async with self.session.get(Config.HN_ITEM_URL.format(item_id)) as resp:
            return await resp.json()

    async def get_top_stories(self, limit=3) -> List[Dict]:
        ids = await self.get_top_stories_ids()
        items = await asyncio.gather(*(self.get_item(i) for i in ids))
        # Оставляем только статьи
        stories = [it for it in items if it and it.get("type") == "story" and "url" in it]
        return stories[:limit]


# ======= GEMINI TRANSLATOR =======
class GeminiTranslator:
    def __init__(self):
        genai.configure(api_key=Config.GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemini-2.5-flash')

    async def translate(self, text: str) -> str:
        try:
            prompt = f"Переведи на русский, сохрани технические термины:\n\n{text}"
            resp = await asyncio.to_thread(self.model.generate_content, prompt)
            return resp.text.strip()
        except Exception as e:
            logger.error(f"Ошибка перевода: {e}")
            return text


# ======= TELEGRAM POSTER =======
class TelegramPoster:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self.base_url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}"

    async def send_message(self, text: str) -> bool:
        url = f"{self.base_url}/sendMessage"
        data = {
            "chat_id": Config.TELEGRAM_CHANNEL_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        async with self.session.post(url, json=data) as resp:
            if resp.status == 200:
                logger.info("✅ Сообщение отправлено")
                return True
            logger.error(f"Ошибка TG API: {resp.status}")
            return False


# ======= MAIN BOT =======
class TechNewsBot:
    def __init__(self):
        self.session = None
        self.hn = None
        self.translator = None
        self.poster = None
        self.scheduler = AsyncIOScheduler(timezone=Config.TIMEZONE)

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        self.hn = HackerNewsAPI(self.session)
        self.translator = GeminiTranslator()
        self.poster = TelegramPoster(self.session)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.session:
            await self.session.close()

    async def make_post(self, limit=3):
        logger.info("📡 Получаю новости...")
        stories = await self.hn.get_top_stories(limit=limit)

        if not stories:
            logger.warning("Нет новостей")
            return

        translated = []
        for st in stories:
            tr_title = await self.translator.translate(st['title'])
            translated.append((tr_title, st['url']))

        now = datetime.now().strftime("%H:%M")
        text = f"🔥 <b>Топ Hacker News {now} МСК</b>\n\n"
        for i, (title, link) in enumerate(translated, 1):
            text += f"<b>{i}. {title}</b>\n🔗 <a href='{link}'>Читать</a>\n\n"

        await self.poster.send_message(text)

    async def post_startup_news(self):
        logger.info("🚀 Постим стартовую новость...")
        await self.make_post(limit=1)

    def schedule_jobs(self):
        for t in Config.POST_TIMES:
            h, m = map(int, t.split(":"))
            self.scheduler.add_job(self.make_post, CronTrigger(hour=h, minute=m))

    async def run(self):
        await self.post_startup_news()
        self.schedule_jobs()
        self.scheduler.start()
        while True:
            await asyncio.sleep(60)


async def main():
    if not all([Config.TELEGRAM_BOT_TOKEN, Config.TELEGRAM_CHANNEL_ID, Config.GEMINI_API_KEY]):
        logger.error("❌ Не заданы переменные окружения")
        exit(1)
    async with TechNewsBot() as bot:
        await bot.run()


if __name__ == "__main__":
    asyncio.run(main())ranslator.translate_to_russian(top_news['title'])
            
            # Формируем стартовый пост
            startup_post = f"🔥 <b>Топ новость HackerNews:</b>\n\n"
            startup_post += f"<b>{translated_title}</b>\n"
            startup_post += f"💬 {top_news['points']} очков\n"
            startup_post += f"🔗 <a href='{top_news['link']}'>Читать далее</a>"
            
            # Отправляем
            success = await self.poster.send_message(startup_post)
            
            if success:
                logger.info("🎉 Стартовая новость успешно опубликована!")
            else:
                logger.error("❌ Ошибка публикации стартовой новости")
                
        except Exception as e:
            logger.error(f"Ошибка в post_startup_news: {e}")

async def main():
    """Основная функция запуска"""
    # Railway автоматически запускает в production режиме
    async with TechNewsBot() as bot:
        await bot.run_forever()

if __name__ == "__main__":
    # Railway автоматически передаст переменные окружения
    required_vars = ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHANNEL_ID', 'GEMINI_API_KEY']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"❌ Не заданы переменные окружения: {', '.join(missing_vars)}")
        logger.error("Добавьте их в Railway Dashboard -> Variables")
        exit(1)
    
    logger.info("🚀 Запуск Tech News Bot на Railway...")
    asyncio.run(main())
