import os
import logging
from enum import Enum
import asyncio
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)
from dotenv import load_dotenv
from llm import generate_route_suggestion

load_dotenv("config.env") #TELEGRAM_BOT_KEY

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния бота (ConversationHandler)
class States(Enum):
    INTERESTS = 0
    AVAILABLE_TIME = 1
    LOCATION = 2
    WAIT_USER = 3 

user_data_store = {}
dialogue_end = set()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало опроса"""
    user = update.effective_user
    logger.info(f"Пользователь {user.id} начал опрос")
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n"
        "Я помогу подобрать тебе идеальную прогулку.\n\n"
        "Сначала расскажи, что тебе или вашей компании интересно? Например: стрит-арт, история, кофейни, панорамы и т.д.\n"
        "Перечисляй всё через запятую.Можешь указать что конкретному человеку интересно."
    )
    return States.INTERESTS

async def get_interests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняем интересы пользователя"""
    text = update.message.text
    if not text:
        await update.message.reply_text("Пожалуйста, введи текст (не фото/стикеры).")
        return States.INTERESTS

    context.user_data['interests'] = text.strip()
    logger.info(f"Пользователь {update.effective_user.id} указал интересы: {text.strip()}")

    await update.message.reply_text(
        "Отлично! А сколько у тебя свободного времени на прогулку? Напиши число в часах (например: 2.5 или 3)."
    )
    return States.AVAILABLE_TIME

async def get_available_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняем время пользователя"""
    text = update.message.text
    try:
        hours = float(text.replace(',', '.'))
        if hours <= 0:
            raise ValueError
        context.user_data['available_time'] = hours
        logger.info(f"Пользователь {update.effective_user.id} указал время: {hours} ч")
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи положительное число (например: 1.5 или 2).")
        return States.AVAILABLE_TIME

    # Запрашиваем местоположение
    location_button = KeyboardButton(text="Отправить моё местоположение 📍", request_location=True)
    reply_markup = ReplyKeyboardMarkup([[location_button]], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text(
        "Теперь отправь своё текущее местоположение.\n"
        "Вы можете написать координаты текстом (например: 56.326 44.007) "
        "либо воспользоваться кнопкой ниже.",
        reply_markup=reply_markup
    )
    return States.LOCATION

async def get_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lat = None
    lon = None
    source = " "
    if update.message.location:
        location = update.message.location
        lat, lon = location.latitude, location.longitude
    elif update.message.text:
        text = update.message.text.strip()
        try:
            parts = text.replace(',', ' ').split()
            if len(parts) != 2:
                raise ValueError
            lat = float(parts[0])
            lon = float(parts[1])
        except (ValueError, IndexError):
            await update.message.reply_text(
                "Неверный формат координат. Напиши как: 56.326, 44.007\n"
                "Или нажми кнопку 📍 для автоматической отправки местоположения."
            )
            return States.LOCATION
    else:
        await update.message.reply_text("Пожалуйста, отправь геопозицию или введи координаты.")
        return States.LOCATION

    context.user_data['location'] = {
        'latitude': lat,
        'longitude': lon
    }

    logger.info(f"Получены координаты: {lat:.6f}, {lon:.6f} ({source})")

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    user_data_store[user_id] = {
        'interests': context.user_data['interests'],
        'available_time': context.user_data['available_time'],
        'location': context.user_data['location']
    }

    await update.message.reply_text(
        "Спасибо! 🎉\n"
        f"• Интересы: {context.user_data['interests']}\n"
        f"• Время: {context.user_data['available_time']} ч\n"
        f"• Местоположение: {lat:.5f}, {lon:.5f}\n\n"
        "Подожди,я подготовлю для тебя персональный маршрут..."
    )
    
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    context.application.create_task(
        generate_and_send_route(context, chat_id, context.user_data.copy())
    )

    return States.WAIT_USER 

async def generate_and_send_route(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_data: dict):
    """Фоновая задача: генерация маршрута и отправка результата"""
    try:
        route_suggestion = await generate_route_suggestion(user_data)
        await context.bot.send_message(
            chat_id=chat_id,
              text="Вот твой маршрут:\n\n" + route_suggestion + "\n\nНапиши /start, чтобы создать новый маршрут!"
        )
    except Exception as e:
        logger.error(f"Ошибка генерации маршрута для чата {chat_id}: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="Произошла ошибка при генерации маршрута. Попробуй позже."
        )
    finally:
        dialogue_end.add(chat_id)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена опроса"""
    user = update.effective_user
    logger.info(f"Пользователь {user.id if user else 'unknown'} отменил опрос")
    await update.message.reply_text("Опрос отменён. Напиши /start, чтобы начать заново.")
    return ConversationHandler.END

async def handle_during_wait(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверяет диалог на завершенность.Удаляет сообщение пользователя и показывает 'Ожидайте...' на 5 сек"""
    chat_id = update.effective_chat.id 
    if chat_id in dialogue_end:
        dialogue_end.discard(chat_id)  # сброс флага
        await update.message.reply_text("Маршрут уже отправлен. Напиши /start для новой прогулки.")
        return ConversationHandler.END

    user_msg = update.message
    bot_msg = await user_msg.reply_text("⏳ Пожалуйста, ожидайте — маршрут генерируется...")

    try:
        await user_msg.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение: {e}")

    try:
        await asyncio.sleep(5)
        await bot_msg.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить служебное сообщение: {e}")

    return States.WAIT_USER

async def post_init(application: Application):
    await application.bot.set_my_commands([
        ("start", "Начать опрос"),
        ("cancel", "Отменить текущий опрос"),
    ])

def main():
    TOKEN = os.getenv("TELEGRAM_BOT_KEY")
    if not TOKEN:
        logger.error("Токен бота не найден в .env файле!")
        raise ValueError("Токен бота не найден!")

    application = Application.builder().token(TOKEN).post_init(post_init).build()

    # ConversationHandler для последовательного опроса
    conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        States.INTERESTS: [MessageHandler(~filters.COMMAND, get_interests)],
        States.AVAILABLE_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_available_time)],
        States.LOCATION: [
            MessageHandler(filters.LOCATION, get_location),
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_location),
            ],
        States.WAIT_USER: [
            CommandHandler("cancel", cancel),
            MessageHandler(filters.ALL, handle_during_wait),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
        ],
    )

    application.add_handler(conv_handler)
    logger.info("Бот запущен.")
    application.run_polling()

if __name__ == "__main__":
    main()
