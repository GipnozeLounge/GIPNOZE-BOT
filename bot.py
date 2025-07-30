from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters, CallbackQueryHandler
)
from datetime import datetime
import os
from dotenv import load_dotenv

CHOOSING, BOOK_DATE, BOOK_TIME, GUESTS, CONTACT_NAME, CONTACT_PHONE, SELECT_CABIN = range(7)

ADMIN_CHAT_ID = "@gipnoze_lounge_chat"
ADMIN_PHONE = "+380956232134"
ADMIN_USER_ID = 6073809255

bookings = []

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

# START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_keyboard = [["📅 Забронювати столик", "❌ Скасувати бронь"], ["👀 Переглянути бронювання (адміну)"]]
    await update.message.reply_text(
        "Привіт! Я бот для бронювання в кальянній.\nЩо бажаєш зробити?\n\nДля питань: " + ADMIN_PHONE,
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return CHOOSING

# ВИБІР ДІЇ
async def choose_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = update.message.text
    if action == "📅 Забронювати столик":
        context.user_data['action'] = action
        await update.message.reply_text("На яку дату плануєш візит? (формат: 30.07.2025)")
        return BOOK_DATE
    elif action == "❌ Скасувати бронь":
        await update.message.reply_text("Введи своє ім'я, щоб скасувати бронь:")
        return CONTACT_NAME
    elif action == "👀 Переглянути бронювання (адміну)":
        if update.message.from_user.id == ADMIN_USER_ID:
            if not bookings:
                await update.message.reply_text("Наразі немає активних бронювань.")
            else:
                for i, b in enumerate(bookings, 1):
                    await update.message.reply_text(f"#{i} - {b['name']}, {b['date']} {b['time']}, Статус: {b['status']}")
        else:
            await update.message.reply_text("Ця функція тільки для адміністратора.")
        return ConversationHandler.END

# ДАТА
async def book_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    try:
        datetime.strptime(text, "%d.%m.%Y")
        context.user_data['date'] = text
    except ValueError:
        await update.message.reply_text("Невірний формат. Введи дату у форматі 30.07.2025")
        return BOOK_DATE

    keyboard = [[InlineKeyboardButton(time, callback_data=f"time_{time}")] for time in time_slots]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("О котрій годині?", reply_markup=reply_markup)
    return BOOK_TIME

# ЧАС
async def book_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    time_value = query.data.split("_")[1]
    context.user_data['time'] = time_value

    date = context.user_data['date']
    busy = [b['cabin'] for b in bookings if b['date'] == date and b['time'] == time_value and b['status'] in ['Очікує підтвердження', 'Підтверджено']]
    available_cabins = [c for c in CABINS if c not in busy]

    if not available_cabins:
        await query.edit_message_text("На цей час усі кабінки зайняті. Оберіть інший час або дату.")
        return ConversationHandler.END

    await query.edit_message_text("Скільки осіб?")
    return GUESTS

# ГОСТІ
async def guests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['guests'] = update.message.text
    date = context.user_data['date']
    time = context.user_data['time']
    busy = [b['cabin'] for b in bookings if b['date'] == date and b['time'] == time and b['status'] in ['Очікує підтвердження', 'Підтверджено']]
    available_cabins = [c for c in CABINS if c not in busy]

    keyboard = [[InlineKeyboardButton(cabin, callback_data=f"cabin_{cabin}")] for cabin in available_cabins]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Оберіть місце або зону:", reply_markup=reply_markup)
    return SELECT_CABIN

# КАБІНКА
async def select_cabin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cabin_value = query.data.replace("cabin_", "")
    context.user_data['cabin'] = cabin_value
    await query.edit_message_text("Як вас звати?")
    return CONTACT_NAME

# ІМ'Я
async def contact_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("Ваш номер телефону?")
    return CONTACT_PHONE

# ПІДТВЕРДЖЕННЯ
async def contact_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['contact'] = update.message.text
    booking = {
        'name': context.user_data['name'],
        'action': context.user_data.get('action', '—'),
        'date': context.user_data['date'],
        'time': context.user_data['time'],
        'guests': context.user_data['guests'],
        'cabin': context.user_data['cabin'],
        'contact': context.user_data['contact'],
        'status': 'Очікує підтвердження',
        'chat_id': update.message.chat_id
    }
    bookings.append(booking)
    idx = len(bookings) - 1

    await update.message.reply_text("✅ Дякуємо! Ми отримали твоє бронювання.")
    await update.message.reply_text("📬 Ми повідомимо тебе, коли бронювання буде підтверджене адміністратором.")

    keyboard = [
        [
            InlineKeyboardButton("✅ Підтвердити", callback_data=f"confirm_{idx}"),
            InlineKeyboardButton("❌ Відхилити", callback_data=f"reject_{idx}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=ADMIN_USER_ID, text=format_booking_msg(booking), reply_markup=reply_markup)
    return ConversationHandler.END

# ОБРОБКА ПІДТВЕРДЖЕННЯ
async def booking_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    action, idx_str = data.split("_")
    idx = int(idx_str)

    booking = bookings[idx]

    if action == "confirm":
        booking['status'] = "Підтверджено"
        await context.bot.send_message(chat_id=booking['chat_id'], text="🎉 Ваше бронювання підтверджено!")
        await query.edit_message_text(f"✅ Підтверджено:\n\n{format_booking_msg(booking)}")
    elif action == "reject":
        booking['status'] = "Відхилено"
        await context.bot.send_message(chat_id=booking['chat_id'], text="❌ Ваше бронювання було відхилено.")
        await query.edit_message_text(f"❌ Відхилено:\n\n{format_booking_msg(booking)}")

# СКАСУВАННЯ
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Бронювання скасовано.")
    return ConversationHandler.END

# ФОРМАТ ПОВІДОМЛЕННЯ
def format_booking_msg(booking):
    return (
        f"📅 Нове бронювання:\n"
        f"Ім'я: {booking['name']}\n"
        f"Тип: {booking.get('action', '—')}\n"
        f"Дата: {booking['date']}\n"
        f"Час: {booking['time']}\n"
        f"Гостей: {booking['guests']}\n"
        f"Місце: {booking['cabin']}\n"
        f"Телефон: {booking['contact']}\n"
        f"Статус: {booking['status']}"
    )

# ЗАПУСК
if __name__ == '__main__':
    load_dotenv()
    TOKEN = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CHOOSING: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_action)],
            BOOK_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, book_date)],
            BOOK_TIME: [CallbackQueryHandler(book_time, pattern=r"^time_")],
            GUESTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, guests)],
            SELECT_CABIN: [CallbackQueryHandler(select_cabin, pattern=r"^cabin_")],
            CONTACT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact_name)],
            CONTACT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact_phone)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_chat=True,
        per_message=False
    )

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(booking_callback, pattern=r"^(confirm|reject)_\d+"))

    import asyncio
    asyncio.run(app.run_polling())
