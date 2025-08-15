#!/usr/bin/env python3
"""
Автоматический бот для постинга технических новостей в Telegram
Постит 3 раза в день: 9:00, 12:00, 18:00 по МСК
Готов для Railway deployment
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import List, Dict, Optional

import aiohttp
import feedparser
import google.generativeai as genai
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Настройка логирования для Railway
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]  # Railway читает stdout
)
logger = logging.getLogger(__name__)

class Config:
    """Конфигурация бота"""
    # Токены (заполнить реальными значениями)
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN')
    TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID', '@your_channel')
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'YOUR_GEMINI_KEY')
    
    # Источники новостей
    HN_SOURCES = [
        'https://hnrss.org/frontpage?points=100',  # Посты с 100+ очков
        'https://hnrss.org/best?points=200',       # Лучшие с 200+ очков
        'https://hnrss.org/newest?points=150'      # Новые с 150+ очков
    ]
    
    # Расписание постинга (МСК)
    POST_TIMES = ['09:00', '12:00', '18:00']
    TIMEZONE = 'Europe/Moscow'

class HackerNewsParser:
    """Парсер новостей с Hacker News"""
    
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
    
    async def fetch_news(self, url: str) -> List[Dict]:
        """Получение новостей из RSS"""
        try:
            async with self.session.get(url) as response:
                content = await response.text()
                
            feed = feedparser.parse(content)
            news = []
            
            for entry in feed.entries[:10]:  # Берем топ-10
                # Извлекаем баллы из комментариев (если есть)
                points = 0
                if hasattr(entry, 'comments') and 'points' in entry.comments:
                    try:
                        points = int(entry.comments.split()[0])
                    except:
                        points = 0
                
                news_item = {
                    'title': entry.title,
                    'link': entry.link,
                    'published': entry.published,
                    'points': points,
                    'summary': getattr(entry, 'summary', '')[:500]  # Ограничиваем длину
                }
                news.append(news_item)
            
            return sorted(news, key=lambda x: x['points'], reverse=True)
            
        except Exception as e:
            logger.error(f"Ошибка получения новостей с {url}: {e}")
            return []
    
    async def get_top_stories(self) -> List[Dict]:
        """Получение топовых новостей со всех источников"""
        all_news = []
        
        for source in Config.HN_SOURCES:
            news = await self.fetch_news(source)
            all_news.extend(news)
        
        # Удаляем дубликаты по ссылкам
        seen_links = set()
        unique_news = []
        for item in all_news:
            if item['link'] not in seen_links:
                seen_links.add(item['link'])
                unique_news.append(item)
        
        # Сортируем по баллам и берем топ-3
        return sorted(unique_news, key=lambda x: x['points'], reverse=True)[:3]

class GeminiTranslator:
    """Переводчик текста через Gemini API"""
    
    def __init__(self):
        genai.configure(api_key=Config.GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemini-1.5-flash')
    
    async def translate_to_russian(self, text: str) -> str:
        """Перевод текста на русский"""
        try:
            prompt = f"""
            Переведи следующий технический текст на русский язык.
            Сохрани технические термины, но сделай текст понятным для русскоязычной аудитории.
            Не добавляй лишних комментариев, только перевод:
            
            {text}
            """
            
            response = await asyncio.to_thread(
                self.model.generate_content, prompt
            )
            
            return response.text.strip()
            
        except Exception as e:
            logger.error(f"Ошибка перевода: {e}")
            return text  # Возвращаем оригинал при ошибке

class TelegramPoster:
    """Отправка сообщений в Telegram"""
    
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self.base_url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}"
    
    async def send_message(self, text: str) -> bool:
        """Отправка сообщения в канал"""
        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                'chat_id': Config.TELEGRAM_CHANNEL_ID,
                'text': text,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True
            }
            
            async with self.session.post(url, json=data) as response:
                if response.status == 200:
                    logger.info("Сообщение успешно отправлено в Telegram")
                    return True
                else:
                    logger.error(f"Ошибка отправки в Telegram: {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"Ошибка отправки в Telegram: {e}")
            return False
    
    def format_news_post(self, news_items: List[Dict], translated: List[str]) -> str:
        """Форматирование поста с новостями"""
        current_time = datetime.now().strftime("%H:%M")
        
        post = f"🔥 <b>Топ технических новостей {current_time} МСК</b>\n\n"
        
        for i, (item, translation) in enumerate(zip(news_items, translated), 1):
            post += f"<b>{i}. {translation}</b>\n"
            post += f"💬 {item['points']} очков\n"
            post += f"🔗 <a href='{item['link']}'>Читать далее</a>\n\n"
        
        post += "📡 <i>Автоматическая подборка от TechNewsBot</i>"
        return post

class TechNewsBot:
    """Основной класс бота"""
    
    def __init__(self):
        self.session = None
        self.parser = None
        self.translator = GeminiTranslator()
        self.poster = None
        self.scheduler = AsyncIOScheduler(timezone=Config.TIMEZONE)
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        self.parser = HackerNewsParser(self.session)
        self.poster = TelegramPoster(self.session)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def process_and_post_news(self):
        """Основная функция: получение, перевод и постинг новостей"""
        logger.info("Начинаем обработку новостей...")
        
        try:
            # 1. Получаем топовые новости
            news_items = await self.parser.get_top_stories()
            
            if not news_items:
                logger.warning("Не удалось получить новости")
                return
            
            logger.info(f"Получено {len(news_items)} новостей")
            
            # 2. Переводим заголовки
            translated_titles = []
            for item in news_items:
                translated = await self.translator.translate_to_russian(item['title'])
                translated_titles.append(translated)
            
            # 3. Формируем и отправляем пост
            post_text = self.poster.format_news_post(news_items, translated_titles)
            success = await self.poster.send_message(post_text)
            
            if success:
                logger.info("Новости успешно опубликованы!")
            else:
                logger.error("Ошибка публикации новостей")
                
        except Exception as e:
            logger.error(f"Ошибка в process_and_post_news: {e}")
    
    def setup_scheduler(self):
        """Настройка расписания постинга"""
        for time_str in Config.POST_TIMES:
            hour, minute = map(int, time_str.split(':'))
            
            self.scheduler.add_job(
                self.process_and_post_news,
                trigger=CronTrigger(hour=hour, minute=minute),
                id=f'post_news_{time_str}',
                name=f'Post news at {time_str}'
            )
            
            logger.info(f"Запланирован постинг на {time_str} МСК")
    
    async def run_once(self):
        """Одноразовый запуск для тестирования"""
        await self.process_and_post_news()
    
    async def run_forever(self):
        """Запуск бота в режиме демона"""
        self.setup_scheduler()
        self.scheduler.start()
        
        logger.info("Бот запущен! Ожидание расписания...")
        
        try:
            # Бесконечный цикл работы
            while True:
                await asyncio.sleep(60)  # Проверяем каждую минуту
                
        except KeyboardInterrupt:
            logger.info("Получен сигнал остановки")
        finally:
            self.scheduler.shutdown()

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