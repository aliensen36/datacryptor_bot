import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from apps.handlers.start_handler import start_router
from config import BOT_TOKEN
from database.engine import create_db, drop_db


async def main():
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    # Создание базы данных при запуске
    try:
        await create_db()
        logger.info("База данных успешно создана/проверена")
    except Exception as e:
        logger.error(f"Ошибка при создании базы данных: {e}")
        return  # Завершаем выполнение если БД не создана

    # Инициализация бота и диспетчера
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # Регистрация роутеров
    dp.include_router(start_router)

    try:
        logger.info("Бот запущен: https://t.me/datacryptor_bot")
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        # Корректная обработка остановки по Ctrl+C
        logger.info("Бот остановлен")
        print("\nБот остановлен")
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
    finally:
        await bot.session.close()


async def main_with_drop():
    """Функция для полного пересоздания БД (очистка всех данных)"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    # Удаление и пересоздание базы данных
    try:
        await drop_db()
        logger.info("База данных удалена")
        await create_db()
        logger.info("База данных пересоздана")
    except Exception as e:
        logger.error(f"Ошибка при пересоздании базы данных: {e}")
        return

    # Запуск бота
    await main()


if __name__ == "__main__":
    # Для обычного запуска с созданием/проверкой БД
    try:
        # Для обычного запуска с созданием/проверкой БД
        asyncio.run(main())
    except KeyboardInterrupt:
        # Обработка KeyboardInterrupt на верхнем уровне
        print("\nРабота бота завершена")

    # Для запуска с полной очисткой БД (раскомментируйте при необходимости)
    # asyncio.run(main_with_drop())
