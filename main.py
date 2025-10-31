import os
import logging
from enum import Enum

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

user_data_store = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало опроса"""
    user = update.effective_user
    logger.info(f"Пользователь {user.id} начал опрос")
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n"
        "Я помогу подобрать тебе идеальную прогулку.\n\n"
        "Сначала расскажи, что тебе интересно? Например: стрит-арт, история, кофейни, панорамы и т.д.\n"
        "Можешь перечислить через запятую."
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
        "Теперь отправь своё текущее местоположение — нажми кнопку ниже.",
        reply_markup=reply_markup
    )
    return States.LOCATION

async def get_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняем геопозицию и вызываем нейросеть"""
    location = update.message.location
    if not location:
        await update.message.reply_text("Пожалуйста, отправь геопозицию через кнопку.")
        return States.LOCATION

    context.user_data['location'] = {
        'latitude': location.latitude,
        'longitude': location.longitude
    }

    user_id = update.effective_user.id
    user_data_store[user_id] = {
        'interests': context.user_data['interests'],
        'available_time': context.user_data['available_time'],
        'location': context.user_data['location']
    }

    await update.message.reply_text(
        "Спасибо! 🎉\n"
        f"• Интересы: {context.user_data['interests']}\n"
        f"• Время: {context.user_data['available_time']} ч\n"
        f"• Местоположение: {location.latitude:.5f}, {location.longitude:.5f}\n\n"
        "Готовлю для тебя персональный маршрут..."
    )

    route_suggestion = generate_route_suggestion(context.user_data)
    await update.message.reply_text("Вот твой маршрут:\n\n" + route_suggestion)

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена опроса"""
    user = update.effective_user
    logger.info(f"Пользователь {user.id if user else 'unknown'} отменил опрос")
    await update.message.reply_text("Опрос отменён. Напиши /start, чтобы начать заново.")
    return ConversationHandler.END

def main():
    TOKEN = os.getenv("TELEGRAM_BOT_KEY")
    if not TOKEN:
        logger.error("Токен бота не найден в .env файле!")
        raise ValueError("Токен бота не найден!")

    application = Application.builder().token(TOKEN).build()

    # ConversationHandler для последовательного опроса
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            States.INTERESTS: [MessageHandler(~filters.COMMAND, get_interests)],
            States.AVAILABLE_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_available_time)],
            States.LOCATION: [MessageHandler(filters.LOCATION, get_location)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    logger.info("Бот запущен.")
    application.run_polling()

if __name__ == "__main__":
    main()
