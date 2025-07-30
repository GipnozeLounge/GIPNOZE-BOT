from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters, CallbackQueryHandler
)
from datetime import datetime
import os
from dotenv import load_dotenv

# Стани діалогу
CHOOSING, BOOK_DATE, BOOK_TIME, GUESTS, CONTACT_NAME, CONTACT_PHONE, SELECT_CABIN = range(7)

# ID групи Telegram, куди надсилати повідомлення
ADMIN_CHAT_ID = "@gipnoze_lounge_chat"
ADMIN_PHONE = "+380956232134"
ADMIN_USER_ID = 6073809255  # <-- заміни на свій Telegram user ID

bookings = []  # Список для збереження бронювань у пам'яті

# Часові слоти з 17:00 по 22:30 з кроком 30 хвилин
time_slots = [f"{h:02d}:{m:02d}" for h in range(17, 23) for m in (0, 30) if not (h == 22 and m > 30)]

CABINS = [
    "Кабінка 1 (5-10 чол.)",
    "Кабінка 2 (до 8 чол.)",
    "Кабінка 3 (до 6 чол.)",
    "VIP Xbox X (до 12 чол.)",
    "VIP PS5 (до 12 чол.)",
    "Диванчики на барі (до 6 чол.)",
    "Барна стійка (6 місць)",
    "Літня тераса - стіл 1",
    "Літня тераса - стіл 2",
    "Літня тераса - стіл 3",
    "Літня тераса - стіл 4",
    "Додаткове місце на 3 чол."
]

user_booking_data = {}  # тимчасове зберігання для кожного юзера

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_keyboard = [["📅 Забронювати столик", "❌ Скасувати бронь"], ["👀 Переглянути бронювання (адміну)"]]
    await update.message.reply_text(
        "Привіт! Я бот для бронювання в кальянній.\nЩо бажаєш зробити?\n\nДля питань: " + ADMIN_PHONE,
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
    )
    return CHOOSING

async def choose_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = update.message.text
    user_id = update.message.from_user.id

    if action == "📅 Забронювати столик":
        user_booking_data[user_id] = {}
        await update.message.reply_text("На яку дату плануєш візит? (формат: 30.07.2025)")
        return BOOK_DATE
    elif action == "❌ Скасувати бронь":
        await update.message.reply_text("Введи своє ім'я, щоб скасувати бронювання:")
        return CONTACT_NAME
    elif action == "👀 Переглянути бронювання (адміну)":
        if update.message.from_user.id == ADMIN_USER_ID:
            if not bookings:
                await update.message.reply_text("Наразі немає активних бронювань.")
            else:
                for i, b in enumerate(bookings, 1):
                    await update.message.reply_text(f"#{i}: {b}")
        else:
            await update.message.reply_text("Ця функція тільки для адміністратора.")
        return ConversationHandler.END

async def book_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    try:
        datetime.strptime(text, "%d.%m.%Y")
        user_booking_data[user_id]['date'] = text
    except ValueError:
        await update.message.reply_text("Невірний формат. Введи дату у форматі 30.07.2025")
        return BOOK_DATE

    keyboard = [[InlineKeyboardButton(time, callback_data=time)] for time in time_slots]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("О котрій годині?", reply_markup=reply_markup)
    return BOOK_TIME

async def book_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_booking_data[user_id]['time'] = query.data

    date = user_booking_data[user_id]['date']
    time = user_booking_data[user_id]['time']
    busy = [b['cabin'] for b in bookings if b['date'] == date and b['time'] == time]

    available_cabins = [cabin for cabin in CABINS if cabin not in busy]
    if not available_cabins:
        await query.edit_message_text("На цей час усі кабінки зайняті. Оберіть інший час або дату.")
        return ConversationHandler.END

    await query.edit_message_text("Скільки осіб?")
    return GUESTS

async def guests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_booking_data[user_id]['guests'] = update.message.text

    date = user_booking_data[user_id]['date']
    time = user_booking_data[user_id]['time']
    busy = [b['cabin'] for b in bookings if b['date'] == date and b['time'] == time]
    available_cabins = [cabin for cabin in CABINS if cabin not in busy]
    keyboard = [[InlineKeyboardButton(cabin, callback_data=cabin)] for cabin in available_cabins]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Оберіть місце або зону:", reply_markup=reply_markup)
    return SELECT_CABIN

async def select_cabin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_booking_data[user_id]['cabin'] = query.data
    await query.edit_message_text("Як вас звати?")
    return CONTACT_NAME

async def contact_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_booking_data[user_id]['name'] = update.message.text
    await update.message.reply_text("Ваш номер телефону?")
    return CONTACT_PHONE

async def contact_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_booking_data[user_id]['contact'] = update.message.text
    data = user_booking_data[user_id]

    summary = (
        f"📅 Нова бронь:\n"
        f"Ім'я: {data['name']}\n"
        f"Дата: {data['date']}\n"
        f"Час: {data['time']}\n"
        f"Гостей: {data['guests']}\n"
        f"Місце: {data['cabin']}\n"
        f"Телефон: {data['contact']}"
    )

    bookings.append({
        'user_id': user_id,
        'name': data['name'],
        'date': data['date'],
        'time': data['time'],
        'guests': data['guests'],
        'cabin': data['cabin'],
        'contact': data['contact'],
        'text': summary
    })

    await update.message.reply_text("✅ Дякуємо! Ми отримали твоє бронювання.")
    await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=summary)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Бронювання скасовано.")
    return ConversationHandler.END

if __name__ == '__main__':
    load_dotenv()
    TOKEN = os.getenv("BOT_TOKEN")

    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CHOOSING: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_action)],
            BOOK_DATE: [MessageHandler(filters.TEXT, book_date)],
            BOOK_TIME: [CallbackQueryHandler(book_time)],
            GUESTS: [MessageHandler(filters.TEXT, guests)],
            SELECT_CABIN: [CallbackQueryHandler(select_cabin)],
            CONTACT_NAME: [MessageHandler(filters.TEXT, contact_name)],
            CONTACT_PHONE: [MessageHandler(filters.TEXT, contact_phone)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True
    )

    app.add_handler(conv_handler)
    import asyncio
    asyncio.run(app.run_polling())
