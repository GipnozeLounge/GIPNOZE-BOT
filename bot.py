# python-telegram-bot v20.x
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters, CallbackQueryHandler
)
from datetime import datetime
import os
from dotenv import load_dotenv
import sqlite3
import logging

# Налаштовуємо логування для діагностики
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Завантажуємо змінні оточення з файлу .env, якщо вони потрібні
load_dotenv()

# Стани діалогу для ConversationHandler
CHOOSING_MAIN_ACTION, BOOK_DATE, BOOK_TIME, GUESTS, SELECT_CABIN, CONTACT_NAME, CONTACT_PHONE, ADMIN_VIEW_DATE = range(8)

# Новий токен бота, наданий користувачем
TOKEN = "8351072049:AAHuWeKXsg2kIz0CGVzctq1xjIfLT9JHRU"

# Нові дані адміністратора
ADMIN_USER_ID = 6073809255
ADMIN_CHAT_ID = "@gipnoze_lounge_chat"
ADMIN_PHONE = "+380956232134"

# Перевірка наявності токена бота
if not TOKEN:
    logging.critical("BOT_TOKEN не знайдено у файлі .env")
    raise ValueError("BOT_TOKEN не знайдено у файлі .env")

# Назва файлу бази даних SQLite
DB_NAME = 'bookings.db'

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

# --- Функції для роботи з базою даних ---

def init_db():
    """Ініціалізує базу даних, створюючи таблицю 'bookings', якщо вона не існує."""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                guests INTEGER NOT NULL,
                cabin TEXT NOT NULL,
                contact TEXT NOT NULL,
                status TEXT NOT NULL,
                chat_id INTEGER NOT NULL
            )
        ''')
        conn.commit()
        logging.info("База даних ініціалізована.")
    except sqlite3.Error as e:
        logging.error(f"Помилка ініціалізації бази даних: {e}")
    finally:
        if conn:
            conn.close()

def get_bookings_from_db(filters=None):
    """Отримує бронювання з бази даних з можливістю фільтрації."""
    conn = None
    bookings_list = []
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        query = "SELECT id, user_id, name, date, time, guests, cabin, contact, status, chat_id FROM bookings"
        params = []
        where_clauses = []

        if filters:
            if 'user_id' in filters:
                where_clauses.append("user_id = ?")
                params.append(filters['user_id'])
            if 'status' in filters:
                if isinstance(filters['status'], list):
                    status_placeholders = ','.join(['?' for _ in filters['status']])
                    where_clauses.append(f"status IN ({status_placeholders})")
                    params.extend(filters['status'])
                else:
                    where_clauses.append("status = ?")
                    params.append(filters['status'])
            if 'date' in filters:
                where_clauses.append("date = ?")
                params.append(filters['date'])
            if 'time' in filters:
                where_clauses.append("time = ?")
                params.append(filters['time'])
            if 'cabin' in filters:
                where_clauses.append("cabin = ?")
                params.append(filters['cabin'])


        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        for row in rows:
            booking = {
                'id': row[0],
                'user_id': row[1],
                'name': row[2],
                'date': row[3],
                'time': row[4],
                'guests': row[5],
                'cabin': row[6],
                'contact': row[7],
                'status': row[8],
                'chat_id': row[9]
            }
            bookings_list.append(booking)
    except sqlite3.Error as e:
        logging.error(f"Помилка отримання бронювань з бази даних: {e}")
    finally:
        if conn:
            conn.close()
    return bookings_list

def add_booking_to_db(booking_data):
    """Додає нове бронювання до бази даних."""
    conn = None
    booking_id = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO bookings (user_id, name, date, time, guests, cabin, contact, status, chat_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            booking_data['user_id'],
            booking_data['name'],
            booking_data['date'],
            booking_data['time'],
            booking_data['guests'],
            booking_data['cabin'],
            booking_data['contact'],
            booking_data['status'],
            booking_data['chat_id']
        ))
        booking_id = cursor.lastrowid
        conn.commit()
        logging.info(f"Бронювання {booking_id} додано до БД.")
    except sqlite3.Error as e:
        logging.error(f"Помилка додавання бронювання до бази даних: {e}")
    finally:
        if conn:
            conn.close()
    return booking_id

def update_booking_status_in_db(booking_id, new_status):
    """Оновлює статус бронювання в базі даних за ID."""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE bookings SET status = ? WHERE id = ?
        ''', (new_status, booking_id))
        conn.commit()
        logging.info(f"Статус бронювання {booking_id} оновлено на '{new_status}'.")
    except sqlite3.Error as e:
        logging.error(f"Помилка оновлення статусу бронювання {booking_id}: {e}")
    finally:
        if conn:
            conn.close()

def get_booking_by_id(booking_id):
    """Отримує одне бронювання за його ID."""
    conn = None
    row = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, user_id, name, date, time, guests, cabin, contact, status, chat_id FROM bookings WHERE id = ?
        ''', (booking_id,))
        row = cursor.fetchone()
    except sqlite3.Error as e:
        logging.error(f"Помилка отримання бронювання за ID {booking_id}: {e}")
    finally:
        if conn:
            conn.close()

    if row:
        return {
            'id': row[0],
            'user_id': row[1],
            'name': row[2],
            'date': row[3],
            'time': row[4],
            'guests': row[5],
            'cabin': row[6],
            'contact': row[7],
            'status': row[8],
            'chat_id': row[9]
        }
    return None

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
        [
            ["📅 Забронювати столик", "📸 Instagram"],
            ["👀 Переглянути бронювання (адміну)", "📞 Зв'язатися з адміном"]
        ],
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
    elif text == "👀 Переглянути бронювання (адміну)":
        if user_id == ADMIN_USER_ID:
            await update.message.reply_text("На яку дату ви хочете переглянути бронювання? (наприклад, 30.07.2025)")
            return ADMIN_VIEW_DATE
        else:
            await update.message.reply_text("Ця функція тільки для адміністратора.", reply_markup=get_main_keyboard())
            return CHOOSING_MAIN_ACTION
    elif text == "📸 Instagram":
        instagram_url = "https://www.instagram.com/gipnoze_lounge?utm_source=ig_web_button_share_sheet&igsh=ZDNlZDc0MzIxNw=="
        await update.message.reply_text(f"Перейти на нашу сторінку Instagram: {instagram_url}", reply_markup=get_main_keyboard())
        return CHOOSING_MAIN_ACTION
    elif text == "📞 Зв'язатися з адміном":
        await update.message.reply_text(f"Номер телефону адміністратора: {ADMIN_PHONE}", reply_markup=get_main_keyboard())
        return CHOOSING_MAIN_ACTION
    else:
        await update.message.reply_text("Будь ласка, оберіть дію з клавіатури.", reply_markup=get_main_keyboard())
        return CHOOSING_MAIN_ACTION

async def book_date_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник введення дати бронювання."""
    user_id = update.message.from_user.id
    date_text = update.message.text

    try:
        booking_date = datetime.strptime(date_text, "%d.%m.%Y").date()
        today = datetime.now().date()
        if booking_date < today:
            await update.message.reply_text("Ви не можете забронювати столик на минулу дату. Будь ласка, введіть актуальну дату.")
            return BOOK_DATE

        user_booking_data[user_id]['date'] = date_text

        keyboard = []
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
    await query.answer()

    user_id = query.from_user.id
    selected_time = query.data.split("_")[1]
    
    if 'date' not in user_booking_data.get(user_id, {}):
        await query.message.reply_text("Щось пішло не так. Будь ласка, почніть бронювання знову.", reply_markup=get_main_keyboard())
        return CHOOSING_MAIN_ACTION

    user_booking_data[user_id]['time'] = selected_time

    # Редагуємо повідомлення з часом на нове повідомлення
    await query.edit_message_text(f"Ви обрали {selected_time}. Тепер, скільки вас буде?", reply_markup=None)
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
    except (ValueError, TypeError):
        await update.message.reply_text("Невірний формат. Будь ласка, введіть кількість гостей числом.")
        return GUESTS

    date = user_booking_data[user_id]['date']
    time = user_booking_data[user_id]['time']

    busy = [b['cabin'] for b in get_bookings_from_db(filters={'date': date, 'time': time, 'status': ['Очікує підтвердження', 'Підтверджено']})]
    available_cabins = [cabin for cabin in CABINS if cabin not in busy]

    if not available_cabins:
        await update.message.reply_text("На жаль, на цей час усі кабінки зайняті. Будь ласка, спробуйте інший час або дату.")
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
    selected_cabin = query.data.split("_")[1]
    
    if 'guests' not in user_booking_data.get(user_id, {}):
        # Відправка нового повідомлення замість редагування, щоб уникнути помилки
        await query.message.reply_text("Дані бронювання втрачені. Будь ласка, почніть бронювання знову.", reply_markup=get_main_keyboard())
        return CHOOSING_MAIN_ACTION

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
    user_data = user_booking_data.get(user_id)
    if not user_data or 'name' not in user_data:
        await update.message.reply_text("Дані бронювання втрачені. Будь ласка, почніть знову.", reply_markup=get_main_keyboard())
        return ConversationHandler.END

    user_data['contact'] = update.message.text

    booking_to_save = {
        'user_id': user_id,
        'name': user_data['name'],
        'date': user_data['date'],
        'time': user_data['time'],
        'guests': user_data['guests'],
        'cabin': user_data['cabin'],
        'contact': user_data['contact'],
        'status': 'Очікує підтвердження',
        'chat_id': update.message.chat_id
    }
    
    booking_id = add_booking_to_db(booking_to_save)
    if booking_id:
        booking_to_save['id'] = booking_id

        await update.message.reply_text("✅ Дякуємо! Ми отримали твоє бронювання.")
        await update.message.reply_text("📬 Чекаємо на підтвердження адміністратором.")

        keyboard = [
            [
                InlineKeyboardButton("✅ Підтвердити", callback_data=f"admin_confirm_{booking_id}"),
                InlineKeyboardButton("❌ Відхилити", callback_data=f"admin_reject_{booking_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await context.bot.send_message(chat_id=ADMIN_USER_ID, text=format_booking_msg(booking_to_save), reply_markup=reply_markup)
        except Exception as e:
            logging.error(f"Помилка при відправці повідомлення адміну ({ADMIN_USER_ID}): {e}")
            await update.message.reply_text(f"Виникла помилка при відправці повідомлення адміністратору. Будь ласка, зв'яжіться з нами за номером {ADMIN_PHONE}.")
    else:
        await update.message.reply_text("Виникла помилка при збереженні бронювання. Будь ласка, спробуйте ще раз.")

    await update.message.reply_text("Щось ще?", reply_markup=get_main_keyboard())
    return ConversationHandler.END

async def admin_booking_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник callback-запитів від адміністратора (підтвердження/відхилення)."""
    query = update.callback_query
    await query.answer()

    data = query.data
    parts = data.split("_")
    if len(parts) != 3 or parts[0] != "admin":
        await query.edit_message_text("Невірний формат запиту. Спробуйте ще раз або зверніться до розробника.")
        return

    action_type = parts[1]
    try:
        booking_id = int(parts[2])
    except (ValueError, IndexError):
        await query.edit_message_text("Невірний ID бронювання.")
        return

    booking = get_booking_by_id(booking_id)

    if not booking:
        await query.edit_message_text("Бронювання не знайдено або вже видалено.")
        return

    if query.from_user.id != ADMIN_USER_ID:
        await query.edit_message_text("Ви не маєте прав для виконання цієї дії.")
        return

    if booking['status'] not in ['Очікує підтвердження']:
        await query.edit_message_text(f"Ця бронь вже '{booking['status']}'.")
        return

    if action_type == "confirm":
        update_booking_status_in_db(booking_id, "Підтверджено")
        booking['status'] = "Підтверджено"

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
            logging.info(f"Повідомлення про підтвердження успішно надіслано в групу: {ADMIN_CHAT_ID}")
        except Exception as e:
            logging.error(f"ПОМИЛКА: Не вдалося надіслати повідомлення в групу {ADMIN_CHAT_ID}: {e}")

        try:
            await context.bot.send_message(chat_id=booking['chat_id'], text="✅ Ваше бронювання підтверджено!")
        except Exception as e:
            logging.error(f"Помилка при відправці повідомлення користувачу {booking['chat_id']} про підтвердження: {e}")

        await query.edit_message_text(f"✅ Підтверджено:\n\n{format_booking_msg(booking)}")

    elif action_type == "reject":
        update_booking_status_in_db(booking_id, "Відхилено")
        booking['status'] = "Відхилено"

        try:
            await context.bot.send_message(chat_id=booking['chat_id'], text="❌ Ваше бронювання було відхилено.")
        except Exception as e:
            logging.error(f"Помилка при відправці повідомлення користувачу {booking['chat_id']} про відхилення: {e}")

        await query.edit_message_text(f"❌ Відхилено:\n\n{format_booking_msg(booking)}")

async def admin_view_date_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник введення дати для перегляду бронювань адміністратором."""
    date_text = update.message.text

    try:
        datetime.strptime(date_text, "%d.%m.%Y").date()
        context.user_data['admin_view_date'] = date_text

        bookings_for_date = get_bookings_from_db(filters={'date': date_text, 'status': ['Очікує підтвердження', 'Підтверджено']})

        if not bookings_for_date:
            await update.message.reply_text(f"На {date_text} немає активних бронювань.", reply_markup=get_main_keyboard())
        else:
            await update.message.reply_text(f"Ось бронювання на {date_text}:")
            for i, b in enumerate(bookings_for_date, 1):
                keyboard = [
                    [InlineKeyboardButton("❌ Скасувати цю бронь", callback_data=f"admin_force_cancel_{b['id']}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    f"🔢 #{i}\n"
                    f"📅 Дата: {b['date']}\n"
                    f"⏰ Час: {b['time']}\n"
                    f"🏠 Кабінка: {b['cabin']}\n"
                    f"👤 {b['name']} ({b['contact']})\n"
                    f"👥 Гостей: {b['guests']}\n"
                    f"📌 Статус: {b['status']}",
                    reply_markup=reply_markup
                )
            await update.message.reply_text("Щось ще?", reply_markup=get_main_keyboard())
        return CHOOSING_MAIN_ACTION
    except ValueError:
        await update.message.reply_text("Невірний формат дати. Будь ласка, введіть дату у форматі ДД.ММ.РРРР (наприклад, 30.07.2025).")
        return ADMIN_VIEW_DATE

async def admin_force_cancel_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник для примусового скасування бронювання адміністратором."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data
    
    if user_id != ADMIN_USER_ID:
        await query.edit_message_text("Ви не маєте прав для виконання цієї дії.")
        return

    action, _, idx_str = data.split("_", 2)
    try:
        booking_id = int(idx_str)
    except (ValueError, IndexError):
        await query.edit_message_text("Невірний ID бронювання.")
        return

    booking_to_cancel = get_booking_by_id(booking_id)

    if not booking_to_cancel:
        await query.edit_message_text("Бронювання не знайдено або вже видалено.")
        return

    if booking_to_cancel['status'] in ['Очікує підтвердження', 'Підтверджено']:
        update_booking_status_in_db(booking_id, 'Скасовано (адміном)')
        booking_to_cancel['status'] = 'Скасовано (адміном)'

        await query.edit_message_text(f"✅ Бронювання на {booking_to_cancel['date']} о {booking_to_cancel['time']} для {booking_to_cancel['name']} скасовано адміністратором.")

        try:
            await context.bot.send_message(
                chat_id=booking_to_cancel['chat_id'],
                text=f"❌ Ваше бронювання на {booking_to_cancel['date']} о {booking_to_cancel['time']} (Кабінка: {booking_to_cancel['cabin']}) було скасовано адміністратором."
            )
        except Exception as e:
            logging.error(f"Помилка при відправці повідомлення користувачу про скасування: {e}")
    else:
        await query.edit_message_text(f"Це бронювання вже було {booking_to_cancel['status']}.")
    
async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник невідомих команд."""
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Вибачте, я не розумію цієї команди. Будь ласка, скористайтесь меню."
    )

def main():
    """Основна функція для запуску бота."""
    init_db()

    application = ApplicationBuilder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING_MAIN_ACTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu_choice)
            ],
            BOOK_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, book_date_handler)],
            BOOK_TIME: [CallbackQueryHandler(book_time_handler, pattern="^time_")],
            GUESTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, guests_handler)],
            SELECT_CABIN: [CallbackQueryHandler(select_cabin_handler, pattern="^cabin_")],
            CONTACT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact_name_handler)],
            CONTACT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact_phone_handler)],
            ADMIN_VIEW_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_view_date_handler)]
        },
        fallbacks=[CommandHandler("start", start)]
    )

    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(admin_booking_callback, pattern="^admin_(confirm|reject)_"))
    application.add_handler(CallbackQueryHandler(admin_force_cancel_booking, pattern="^admin_force_cancel_"))
    application.add_handler(MessageHandler(filters.COMMAND, unknown))

    logging.info("Бот запущено...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
