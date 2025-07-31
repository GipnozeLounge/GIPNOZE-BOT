from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters, CallbackQueryHandler
)
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

# Завантажуємо змінні оточення з файлу .env
load_dotenv()

# Стани діалогу для ConversationHandler
CHOOSING_MAIN_ACTION, BOOK_DATE, BOOK_TIME, GUESTS, SELECT_CABIN, CONTACT_NAME, CONTACT_PHONE, CANCEL_PROMPT, CANCEL_CONFIRM = range(9)

# Отримуємо токен бота, ID адміністратора та ID групи з .env файлу
# Це безпечніше, ніж хардкодити їх у коді
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID")) # Ваш Telegram user ID (числовий)
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID") # Username групи або ID чату для повідомлень адміністраторам (наприклад, "@gipnoze_lounge_chat" або числовий ID)
ADMIN_PHONE = "+380956232134" # Номер телефону для зв'язку

# Зберігання бронювань у пам'яті.
# Увага: При перезапуску бота всі дані будуть втрачені!
# Для продакшн-версії рекомендується використовувати базу даних (наприклад, SQLite, PostgreSQL, Firestore).
bookings = []

# Генерація часових слотів з 17:00 до 22:30 включно, з кроком 30 хвилин
time_slots = []
for h in range(17, 23): # Години від 17 до 22
    for m in (0, 30): # Хвилини 0 або 30
        time_slots.append(f"{h:02d}:{m:02d}")

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

# Тимчасове зберігання даних бронювання для кожного користувача
user_booking_data = {}

# --- Допоміжні функції ---

def format_booking_msg(booking):
    """Форматує інформацію про бронювання для відправки."""
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

def get_main_keyboard():
    """Повертає головну клавіатуру."""
    return ReplyKeyboardMarkup(
        [["📅 Забронювати столик", "❌ Скасувати бронь"], ["👀 Переглянути бронювання (адміну)"]],
        resize_keyboard=True
    )

# --- Функції обробників ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник команди /start."""
    await update.message.reply_text(
        "Привіт! Я бот для бронювання в кальянній.\nЩо бажаєш зробити?\n\nДля питань: " + ADMIN_PHONE,
        reply_markup=get_main_keyboard()
    )
    return CHOOSING_MAIN_ACTION

async def handle_main_menu_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник вибору з головного меню (ReplyKeyboardMarkup)."""
    text = update.message.text
    user_id = update.message.from_user.id

    if text == "📅 Забронювати столик":
        user_booking_data[user_id] = {} # Ініціалізуємо дані для нового бронювання
        await update.message.reply_text("На яку дату ви хочете забронювати столик? (наприклад, 30.07.2025)")
        return BOOK_DATE
    elif text == "❌ Скасувати бронь":
        # Перевіряємо, чи є у користувача активні бронювання
        user_active_bookings = [
            b for b in bookings
            if b['user_id'] == user_id and b['status'] in ['Очікує підтвердження', 'Підтверджено']
        ]
        if not user_active_bookings:
            await update.message.reply_text("У вас немає активних бронювань для скасування.")
            return CHOOSING_MAIN_ACTION

        keyboard = []
        for i, booking in enumerate(user_active_bookings):
            # Зберігаємо індекс бронювання в загальному списку bookings
            original_idx = bookings.index(booking)
            keyboard.append([InlineKeyboardButton(
                f"Скасувати: {booking['date']} {booking['time']} - {booking['cabin']}",
                callback_data=f"cancel_booking_{original_idx}"
            )])
        keyboard.append([InlineKeyboardButton("Повернутися до головного меню", callback_data="back_to_main")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Оберіть бронювання, яке бажаєте скасувати:", reply_markup=reply_markup)
        return CANCEL_PROMPT # Переходимо в стан очікування вибору скасування
    elif text == "👀 Переглянути бронювання (адміну)":
        if user_id == ADMIN_USER_ID:
            active_bookings = [b for b in bookings if b['status'] in ['Очікує підтвердження', 'Підтверджено']]
            if not active_bookings:
                await update.message.reply_text("Наразі немає активних бронювань.")
            else:
                await update.message.reply_text("Ось всі активні бронювання:")
                for i, b in enumerate(active_bookings, 1):
                    # Для адміна, якщо це повідомлення надсилається в групу, можливо, не потрібно кнопок підтвердження/відхилення тут,
                    # оскільки вони вже надсилаються в особистий чат адміна.
                    # Якщо це для перегляду в особистому чаті адміна, можна додати кнопки, але тоді потрібна логіка,
                    # щоб кнопки діяли тільки для адміна.
                    await update.message.reply_text(
                        f"🔢 #{i}\n"
                        f"📅 Дата: {b['date']}\n"
                        f"⏰ Час: {b['time']}\n"
                        f"🏠 Кабінка: {b['cabin']}\n"
                        f"👤 {b['name']} ({b['contact']})\n"
                        f"👥 Гостей: {b['guests']}\n"
                        f"📌 Статус: {b['status']}"
                    )
            return CHOOSING_MAIN_ACTION
        else:
            await update.message.reply_text("Ця функція тільки для адміністратора.")
            return CHOOSING_MAIN_ACTION
    else:
        await update.message.reply_text("Будь ласка, оберіть дію з клавіатури.")
        return CHOOSING_MAIN_ACTION

async def book_date_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник введення дати бронювання."""
    user_id = update.message.from_user.id
    date_text = update.message.text

    try:
        # Перевірка формату дати та її актуальності (не раніше сьогодні)
        booking_date = datetime.strptime(date_text, "%d.%m.%Y").date()
        today = datetime.now().date()
        if booking_date < today:
            await update.message.reply_text("Ви не можете забронювати столик на минулу дату. Будь ласка, введіть актуальну дату.")
            return BOOK_DATE

        user_booking_data[user_id]['date'] = date_text

        # Генеруємо кнопки з часовими слотами
        keyboard = []
        # Розбиваємо слоти на ряди по 4 кнопки
        for i in range(0, len(time_slots), 4):
            row = []
            for slot in time_slots[i:i+4]:
                row.append(InlineKeyboardButton(slot, callback_data=f"time_{slot}"))
            keyboard.append(row)

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Оберіть час:", reply_markup=reply_markup)
        return BOOK_TIME
    except ValueError:
        await update.message.reply_text("Невірний формат дати. Будь ласка, введіть дату у форматі ДД.ММ.РРРР (наприклад, 30.07.2025).")
        return BOOK_DATE

async def book_time_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник вибору часу бронювання."""
    query = update.callback_query
    await query.answer() # Відповідаємо на callback query

    user_id = query.from_user.id
    # Отримуємо час з callback_data (наприклад, "time_18:00")
    selected_time = query.data.split("_")[1]
    user_booking_data[user_id]['time'] = selected_time

    date = user_booking_data[user_id]['date']
    time = user_booking_data[user_id]['time']

    # Фільтруємо зайняті кабінки на обрану дату та час
    busy = [b['cabin'] for b in bookings if b['date'] == date and b['time'] == time and b['status'] in ['Очікує підтвердження', 'Підтверджено']]
    available_cabins = [cabin for cabin in CABINS if cabin not in busy]

    if not available_cabins:
        await query.edit_message_text("На цей час усі кабінки зайняті. Оберіть інший час або дату.")
        # Повертаємо користувача до вибору часу або дати
        # Можна перевести в CHOOSING_MAIN_ACTION або запропонувати повернутися до вибору часу/дати
        await query.message.reply_text("Будь ласка, оберіть інший час або дату з головного меню.", reply_markup=get_main_keyboard())
        return CHOOSING_MAIN_ACTION

    await query.edit_message_text("Скільки осіб?")
    return GUESTS

async def guests_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник введення кількості гостей."""
    user_id = update.message.from_user.id
    guests_text = update.message.text

    try:
        num_guests = int(guests_text)
        if num_guests <= 0:
            await update.message.reply_text("Кількість гостей має бути позитивним числом. Будь ласка, введіть коректну кількість.")
            return GUESTS
        user_booking_data[user_id]['guests'] = num_guests
    except ValueError:
        await update.message.reply_text("Невірний формат. Будь ласка, введіть кількість гостей числом.")
        return GUESTS

    date = user_booking_data[user_id]['date']
    time = user_booking_data[user_id]['time']

    # Повторно фільтруємо зайняті кабінки (на випадок, якщо хтось забронював за цей час)
    busy = [b['cabin'] for b in bookings if b['date'] == date and b['time'] == time and b['status'] in ['Очікує підтвердження', 'Підтверджено']]
    available_cabins = [cabin for cabin in CABINS if cabin not in busy]

    if not available_cabins:
        await update.message.reply_text("На жаль, поки ви вводили дані, всі кабінки на цей час стали зайнятими. Будь ласка, спробуйте інший час або дату.")
        await update.message.reply_text("Повертаю вас до головного меню.", reply_markup=get_main_keyboard())
        return CHOOSING_MAIN_ACTION

    keyboard = [[InlineKeyboardButton(cabin, callback_data=f"cabin_{cabin}")] for cabin in available_cabins]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Оберіть місце або зону:", reply_markup=reply_markup)
    return SELECT_CABIN

async def select_cabin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник вибору кабінки."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    selected_cabin = query.data.split("_")[1] # Отримуємо назву кабінки з callback_data
    user_booking_data[user_id]['cabin'] = selected_cabin
    await query.edit_message_text("Як вас звати?")
    return CONTACT_NAME

async def contact_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник введення імені контакту."""
    user_id = update.message.from_user.id
    user_booking_data[user_id]['name'] = update.message.text
    await update.message.reply_text("Ваш номер телефону? (наприклад, +380991234567)")
    return CONTACT_PHONE

async def contact_phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник введення номера телефону та завершення бронювання."""
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
        'chat_id': update.message.chat_id # Chat ID користувача для надсилання йому повідомлень
    }
    bookings.append(booking)
    idx = len(bookings) - 1 # Зберігаємо індекс нового бронювання

    await update.message.reply_text("✅ Дякуємо! Ми отримали твоє бронювання.")
    await update.message.reply_text("📬 Чекаємо на підтвердження адміністратором.")

    # Клавіатура для адміністратора для підтвердження/відхилення
    keyboard = [
        [
            InlineKeyboardButton("✅ Підтвердити", callback_data=f"admin_confirm_{idx}"),
            InlineKeyboardButton("❌ Відхилити", callback_data=f"admin_reject_{idx}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Надіслати адміну для підтвердження
    try:
        await context.bot.send_message(chat_id=ADMIN_USER_ID, text=format_booking_msg(booking), reply_markup=reply_markup)
    except Exception as e:
        print(f"Помилка при відправці повідомлення адміну: {e}")
        await update.message.reply_text("Виникла помилка при відправці повідомлення адміністратору. Будь ласка, зв'яжіться з нами за номером " + ADMIN_PHONE)

    return ConversationHandler.END # Завершуємо діалог бронювання

async def admin_booking_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник callback-запитів від адміністратора (підтвердження/відхилення)."""
    query = update.callback_query
    await query.answer()

    data = query.data
    action, idx_str = data.split("_", 1) # Розбиваємо "admin_confirm_idx" або "admin_reject_idx"
    action_type = action.split("_")[1] # "confirm" або "reject"
    idx = int(idx_str)

    if not (0 <= idx < len(bookings)):
        await query.edit_message_text("Бронювання не знайдено або вже видалено.")
        return

    booking = bookings[idx]

    # Перевіряємо, чи дія виконується адміністратором
    if query.from_user.id != ADMIN_USER_ID:
        await query.edit_message_text("Ви не маєте прав для виконання цієї дії.")
        return

    if action_type == "confirm":
        booking['status'] = "Підтверджено"

        # Повідомлення в групу адміністраторів (якщо ADMIN_CHAT_ID - це група)
        try:
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
        except Exception as e:
            print(f"Помилка при відправці повідомлення в групу: {e}")

        # Повідомлення користувачу
        try:
            await context.bot.send_message(chat_id=booking['chat_id'], text="✅ Ваше бронювання підтверджено!")
        except Exception as e:
            print(f"Помилка при відправці повідомлення користувачу: {e}")

        # Оновлення повідомлення адміну, щоб кнопки зникли
        await query.edit_message_text(f"✅ Підтверджено:\n\n{format_booking_msg(booking)}")

    elif action_type == "reject":
        booking['status'] = "Відхилено"

        # Повідомлення користувачу
        try:
            await context.bot.send_message(chat_id=booking['chat_id'], text="❌ Ваше бронювання було відхилено.")
        except Exception as e:
            print(f"Помилка при відправці повідомлення користувачу: {e}")

        # Оновлення повідомлення адміну, щоб кнопки зникли
        await query.edit_message_text(f"❌ Відхилено:\n\n{format_booking_msg(booking)}")

    # Після підтвердження/відхилення, можна повернути адміна до головного меню або завершити діалог
    return ConversationHandler.END

async def cancel_booking_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник callback-запитів від користувача для скасування бронювання."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    if data == "back_to_main":
        await query.edit_message_text("Повертаюся до головного меню.", reply_markup=get_main_keyboard())
        return CHOOSING_MAIN_ACTION

    action, idx_str = data.split("_", 1) # Очікуємо "cancel_booking_idx"
    idx = int(idx_str)

    if not (0 <= idx < len(bookings)):
        await query.edit_message_text("Бронювання не знайдено або вже скасовано.")
        return CHOOSING_MAIN_ACTION

    booking_to_cancel = bookings[idx]

    # Перевірка, чи користувач намагається скасувати власне бронювання
    if booking_to_cancel['user_id'] != user_id:
        await query.edit_message_text("Ви можете скасувати лише власні бронювання.")
        return CHOOSING_MAIN_ACTION

    if booking_to_cancel['status'] in ['Очікує підтвердження', 'Підтверджено']:
        booking_to_cancel['status'] = 'Скасовано'
        await query.edit_message_text(f"✅ Бронювання на {booking_to_cancel['date']} о {booking_to_cancel['time']} скасовано.")

        # Повідомлення адміну про скасування
        try:
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=f"❌ Користувач {booking_to_cancel['name']} скасував бронювання на {booking_to_cancel['date']} о {booking_to_cancel['time']} (Кабінка: {booking_to_cancel['cabin']})."
            )
        except Exception as e:
            print(f"Помилка при відправці повідомлення адміну про скасування: {e}")
    else:
        await query.edit_message_text("Це бронювання вже не є активним.")

    await query.message.reply_text("Щось ще?", reply_markup=get_main_keyboard())
    return CHOOSING_MAIN_ACTION

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник команди /cancel для виходу з будь-якого діалогу."""
    await update.message.reply_text("Діалог скасовано. Повертаюся до головного меню.", reply_markup=get_main_keyboard())
    return ConversationHandler.END

async def fallback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник для невідомих команд або повідомлень."""
    await update.message.reply_text("Вибачте, я не розумію вашу команду. Будь ласка, оберіть дію з клавіатури або скористайтеся /start.", reply_markup=get_main_keyboard())
    return CHOOSING_MAIN_ACTION # Повертаємо до головного стану

# --- Основна частина програми ---

if __name__ == '__main__':
    # Перевіряємо наявність токена бота
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN:
        raise ValueError("BOT_TOKEN не знайдено у файлі .env")
    if not ADMIN_USER_ID or not ADMIN_CHAT_ID:
        raise ValueError("ADMIN_USER_ID або ADMIN_CHAT_ID не знайдено у файлі .env")


    app = ApplicationBuilder().token(TOKEN).build()

    # ConversationHandler для обробки діалогів
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CHOOSING_MAIN_ACTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu_choice),
            ],
            BOOK_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, book_date_handler)],
            BOOK_TIME: [CallbackQueryHandler(book_time_handler, pattern=r"^time_")],
            GUESTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, guests_handler)],
            SELECT_CABIN: [CallbackQueryHandler(select_cabin_handler, pattern=r"^cabin_")],
            CONTACT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact_name_handler)],
            CONTACT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact_phone_handler)],
            CANCEL_PROMPT: [CallbackQueryHandler(cancel_booking_callback, pattern=r"^(cancel_booking_|back_to_main)")],
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation), MessageHandler(filters.ALL, fallback_handler)],
        allow_reentry=True, # Дозволяє повторний вхід у діалог
    )

    app.add_handler(conv_handler)
    # Окремий обробник для callback-запитів від адміністратора
    app.add_handler(CallbackQueryHandler(admin_booking_callback, pattern=r"^(admin_confirm_|admin_reject_)"))

    import asyncio
    # Запускаємо бота
    asyncio.run(app.run_polling())

