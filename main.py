#!/usr/bin/env python3
import asyncio
import logging
import os
from datetime import datetime
from typing import Dict, Optional

import aiohttp
import feedparser
import trafilatura
import google.generativeai as genai
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Config:
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN')
    TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID', '@your_channel')
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'YOUR_GEMINI_KEY')
    HN_SOURCE = 'https://hnrss.org/frontpage?points=100'
    POST_TIMES = ['09:00', '12:00', '18:00']
    TIMEZONE = 'Europe/Moscow'

class HackerNewsBot:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        genai.configure(api_key=Config.GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemini-2.5-flash')

    async def get_top_story(self) -> Optional[Dict]:
        """Берёт топ-1 новость с Hacker News"""
        try:
            async with self.session.get(Config.HN_SOURCE) as resp:
                feed = feedparser.parse(await resp.text())

            if not feed.entries:
                return None

            entry = feed.entries[0]
            return {
                "title": entry.title,
                "link": entry.link
            }
        except Exception as e:
            logger.error(f"Ошибка получения топ новости: {e}")
            return None

    async def fetch_article_text(self, url: str) -> str:
        """Скачивает полный текст статьи"""
        try:
            async with self.session.get(url) as resp:
                html = await resp.text()
            text = trafilatura.extract(html)
            return text or "Не удалось извлечь текст."
        except Exception as e:
            logger.error(f"Ошибка скачивания статьи: {e}")
            return "Не удалось извлечь текст."

    async def translate_text(self, text: str) -> str:
        """Перевод текста через Gemini"""
        try:
            prompt = f"Переведи текст на русский, сохрани смысл и структуру:\n\n{text}"
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Ошибка перевода: {e}")
            return text

    async def send_to_telegram(self, title: str, translated_text: str, link: str):
        """Отправка поста в Telegram"""
        post = f"🔥 <b>{title}</b>\n\n✍️ {translated_text}\n\n🔗 <a href='{link}'>Читать оригинал</a>"
        try:
            async with self.session.post(
                f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": Config.TELEGRAM_CHANNEL_ID,
                    "text": post,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False
                }
            ) as resp:
                if resp.status != 200:
                    logger.error(f"Ошибка отправки в Telegram: {resp.status}")
        except Exception as e:
            logger.error(f"Ошибка Telegram API: {e}")

    async def process_and_post(self):
        """Основная логика"""
        logger.info("Загрузка топ новости...")
        story = await self.get_top_story()
        if not story:
            logger.warning("Нет новостей для публикации")
            return

        logger.info(f"Новость: {story['title']}")
        article_text = await self.fetch_article_text(story["link"])
        translated_title = await self.translate_text(story["title"])
        translated_article = await self.translate_text(article_text)
        await self.send_to_telegram(translated_title, translated_article, story["link"])

async def main():
    async with aiohttp.ClientSession() as session:
        bot = HackerNewsBot(session)
        scheduler = AsyncIOScheduler(timezone=Config.TIMEZONE)

        # Пост сразу при запуске
        await bot.process_and_post()

        # Запуск по расписанию
        for t in Config.POST_TIMES:
            h, m = map(int, t.split(':'))
            scheduler.add_job(bot.process_and_post, CronTrigger(hour=h, minute=m))
        scheduler.start()

        while True:
            await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())
