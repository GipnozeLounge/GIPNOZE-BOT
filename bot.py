from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters, CallbackQueryHandler
)
from datetime import datetime
import os
from dotenv import load_dotenv

# Стани діалогу
CHOOSING, BOOK_DATE, BOOK_TIME, GUESTS, CONTACT_NAME, CONTACT_PHONE, SELECT_CABIN, CANCEL_NAME = range(8)

ADMIN_CHAT_ID = "@gipnoze_lounge_chat"
ADMIN_PHONE = "+380956232134"
ADMIN_USER_ID = 6073809255  # заміни на свій Telegram user ID

bookings = []  # збереження бронювань у пам'яті

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

# --- Функції ---

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
        return CANCEL_NAME

    elif action == "👀 Переглянути бронювання (адміну)":
    if user_id == ADMIN_USER_ID:
        active_bookings = [b for b in bookings if b['status'] in ['Очікує підтвердження', 'Підтверджено']]
        if not active_bookings:
            await update.message.reply_text("Наразі немає активних бронювань.")
        else:
            for i, b in enumerate(active_bookings, 1):
                await update.message.reply_text(
                    f"🔢 #{i}\n"
                    f"🗓 {b['date']} ⏰ {b['time']}\n"
                    f"🏠 {b['cabin']}\n"
                    f"👤 {b['name']} ({b['contact']})\n"
                    f"👥 Гостей: {b['guests']}\n"
                    f"📌 Статус: {b['status']}"
                )
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

    busy = [b['cabin'] for b in bookings if b['date'] == date and b['time'] == time and b['status'] in ['Очікує підтвердження', 'Підтверджено']]
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

    busy = [b['cabin'] for b in bookings if b['date'] == date and b['time'] == time and b['status'] in ['Очікує підтвердження', 'Підтверджено']]
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

    booking = {
        'user_id': user_id,
        'name': data['name'],
        'date': data['date'],
        'time': data['time'],
        'guests': data['guests'],
        'cabin': data['cabin'],
        'contact': data['contact'],
        'status': 'Очікує підтвердження',
        'chat_id': update.message.chat_id
    }
    bookings.append(booking)
    idx = len(bookings) - 1

    await update.message.reply_text("✅ Дякуємо! Ми отримали твоє бронювання.")
    await update.message.reply_text("📬 Чекаємо на підтвердження адміністратором.")

    keyboard = [
        [
            InlineKeyboardButton("✅ Підтвердити", callback_data=f"confirm_{idx}"),
            InlineKeyboardButton("❌ Відхилити", callback_data=f"reject_{idx}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Надіслати адміну для підтвердження
    await context.bot.send_message(chat_id=ADMIN_USER_ID, text=format_booking_msg(booking), reply_markup=reply_markup)

    return ConversationHandler.END

async def booking_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    action, idx_str = data.split("_")
    idx = int(idx_str)

    booking = bookings[idx]

    if action == "confirm":
        booking['status'] = "Підтверджено"

        # Повідомлення в групу
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=(
                f"✅ Бронювання підтверджено:\n\n"
                f"Ім'я: {booking['name']}\n"
                f"Телефон: {booking['contact']}\n"
                f"Дата: {booking['date']}\n"
                f"Час: {booking['time']}\n"
                f"Кабінка: {booking['cabin']}\n"
                f"Гостей: {booking['guests']}"
            )
        )

        # Повідомлення користувачу
        await context.bot.send_message(chat_id=booking['chat_id'], text="✅ Ваше бронювання підтверджено!")

        # Оновлення повідомлення адміну
        await query.edit_message_text(f"✅ Підтверджено:\n\n{format_booking_msg(booking)}")

    elif action == "reject":
        booking['status'] = "Відхилено"

        # Повідомлення користувачу
        await context.bot.send_message(chat_id=booking['chat_id'], text="❌ Ваше бронювання було відхилено.")

        # Оновлення повідомлення адміну
        await query.edit_message_text(f"❌ Відхилено:\n\n{format_booking_msg(booking)}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Бронювання скасовано.")
    return ConversationHandler.END

async def cancel_booking_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.text.strip()
    canceled = False
    for b in bookings:
        if b['user_id'] == user_id and b['status'] in ['Очікує підтвердження', 'Підтверджено']:
            b['status'] = 'Скасовано'
            canceled = True
            await update.message.reply_text(f"✅ Бронювання для {b['name']} на {b['date']} о {b['time']} скасовано.")
            # Повідомлення адміну
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=f"❌ Користувач {b['name']} скасував бронювання на {b['date']} о {b['time']}."
            )
            break

    if not canceled:
        await update.message.reply_text("Бронювання не знайдено або вже скасоване.")

    return ConversationHandler.END

def format_booking_msg(booking):
    return (
        f"📅 Нове бронювання:\n"
        f"Ім'я: {booking['name']}\n"
        f"Дата: {booking['date']}\n"
        f"Час: {booking['time']}\n"
        f"Гостей: {booking['guests']}\n"
        f"Місце: {booking['cabin']}\n"
        f"Телефон: {booking['contact']}\n"
        f"Статус: {booking['status']}"
    )

if __name__ == '__main__':
    load_dotenv()
    TOKEN = os.getenv("BOT_TOKEN")

    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CHOOSING: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_action)],
            BOOK_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, book_date)],
            BOOK_TIME: [CallbackQueryHandler(book_time)],
            GUESTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, guests)],
            SELECT_CABIN: [CallbackQueryHandler(select_cabin)],
            CONTACT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact_name)],
            CONTACT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact_phone)],
            CANCEL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, cancel_booking_name)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(booking_callback, pattern=r"^(confirm|reject)_\d+"))

    import asyncio
    asyncio.run(app.run_polling())
