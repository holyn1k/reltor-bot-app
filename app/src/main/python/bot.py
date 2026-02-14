import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler, 
    CallbackQueryHandler, ConversationHandler, MessageHandler, filters
)

# --- НАСТРОЙКИ ---
TOKEN = '8478424555:AAGlP8nfQTWO4itK2Ujn7bDdxZJ1ILMMmj0' 

# ID Админов
ADMIN_IDS = [5715641487, 6226739178] 

# Переменная для ID группы (обновится сама при команде /start в группе)
GROUP_ID = -1005276337773 

CITIES = ["Москва", "Санкт-Петербург", "Татарстан", "Калининград", "Краснодарский край", "Волжск", "Другое"]
ROOMS = ["Студия", "1 комнатная", "2 комнатная", "3 комнатная", "4 комнатная"]

(STATE_CITY, STATE_ROOMS, STATE_MEDIA, STATE_DESC) = range(4)

logging.basicConfig(level=logging.INFO)

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('real_estate.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS flats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        city TEXT,
        rooms TEXT,
        media_id TEXT,
        media_type TEXT,
        description TEXT
    )''')
    conn.commit()
    conn.close()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def get_admin_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("➕ Добавить квартиру"), KeyboardButton("🗑 Удалить квартиру")]],
        resize_keyboard=True
    )

async def show_flat_by_id(update: Update, context: ContextTypes.DEFAULT_TYPE, flat_id):
    """Показывает квартиру. Работает и для ссылок, и для кнопок."""
    conn = sqlite3.connect('real_estate.db')
    c = conn.cursor()
    c.execute("SELECT * FROM flats WHERE id=?", (flat_id,))
    flat = c.fetchone()
    conn.close()
    
    # Если вызываем из команды /start (message) или кнопки (callback)
    if update.callback_query:
        msg_func = update.callback_query.message
        # Удаляем старое меню
        try: await msg_func.delete()
        except: pass
        chat_id = msg_func.chat.id
    else:
        chat_id = update.effective_chat.id

    if not flat:
        await context.bot.send_message(chat_id=chat_id, text="Эта квартира была удалена или не существует 😔", 
                                       reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("В главное меню", callback_data='main_menu')]]))
        return

    # flat: (id, city, rooms, media_id, media_type, desc)
    caption = f"📍 {flat[1]} | {flat[2]}\n\n{flat[5]}"
    kb = [
        [InlineKeyboardButton("✅ Оставить заявку", callback_data=f'lead_{flat[0]}')],
        [InlineKeyboardButton("🏠 В главное меню", callback_data='main_menu')]
    ]
    
    if flat[4] == 'photo':
        await context.bot.send_photo(chat_id=chat_id, photo=flat[3], caption=caption, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await context.bot.send_video(chat_id=chat_id, video=flat[3], caption=caption, reply_markup=InlineKeyboardMarkup(kb))

# --- ОСНОВНОЙ СТАРТ (/start) ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global GROUP_ID
    
    # 1. ЛОГИКА ДЛЯ ГРУППЫ (Восстановил!)
    if update.effective_chat.type in ['group', 'supergroup']:
        GROUP_ID = update.effective_chat.id
        await update.message.reply_text(f"✅ Группа подключена! ID: {GROUP_ID}\nТеперь заявки падают сюда.")
        return

    # 2. ЛОГИКА "ПОДЕЛИТЬСЯ" (Deep Linking)
    # Если ссылка вида t.me/bot?start=flat_55, то args будет ['flat_55']
    args = context.args
    if args and args[0].startswith('flat_'):
        flat_id = args[0].split('_')[1]
        await show_flat_by_id(update, context, flat_id)
        return

    # 3. ОБЫЧНЫЙ СТАРТ (Личка)
    user_id = update.effective_user.id
    
    # Если админ - даем нижнюю клавиатуру
    if user_id in ADMIN_IDS:
        await update.message.reply_text("👋 Привет, Админ! Панель снизу.", reply_markup=get_admin_keyboard())
    
    # Показываем красивое меню поиска
    await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает выбор городов"""
    keyboard = []
    row = []
    for city in CITIES:
        row.append(InlineKeyboardButton(city, callback_data=f'city_{city}'))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
    
    text = "Привет! Я Татьяна. Где будем искать дом мечты? 🌍"
    
    if update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# --- АДМИНКА (ДОБАВЛЕНИЕ) ---

async def admin_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    
    keyboard = [[InlineKeyboardButton(c, callback_data=c)] for c in CITIES]
    await update.message.reply_text("🏙 Шаг 1/4. Выберите город:", reply_markup=InlineKeyboardMarkup(keyboard))
    return STATE_CITY

async def admin_save_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['new_flat_city'] = query.data
    
    keyboard = [[InlineKeyboardButton(r, callback_data=r)] for r in ROOMS]
    await query.message.edit_text(f"Город: {query.data}\n🏠 Шаг 2/4. Выберите тип:", reply_markup=InlineKeyboardMarkup(keyboard))
    return STATE_ROOMS

async def admin_save_rooms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['new_flat_rooms'] = query.data
    await query.message.edit_text("📸 Шаг 3/4. Отправьте ФОТО или ВИДЕО квартиры.")
    return STATE_MEDIA

async def admin_save_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        context.user_data['media_id'] = update.message.photo[-1].file_id
        context.user_data['media_type'] = 'photo'
    elif update.message.video:
        context.user_data['media_id'] = update.message.video.file_id
        context.user_data['media_type'] = 'video'
    else:
        await update.message.reply_text("Нужно фото или видео!")
        return STATE_MEDIA

    await update.message.reply_text("📝 Шаг 4/4. Напишите ОПИСАНИЕ и ЦЕНУ.")
    return STATE_DESC

async def admin_save_final(update: Update, context: ContextTypes.DEFAULT_TYPE):
    description = update.message.text
    data = context.user_data
    
    conn = sqlite3.connect('real_estate.db')
    c = conn.cursor()
    c.execute("INSERT INTO flats (city, rooms, media_id, media_type, description) VALUES (?, ?, ?, ?, ?)",
              (data['new_flat_city'], data['new_flat_rooms'], data['media_id'], data['media_type'], description))
    # Получаем ID только что созданной квартиры
    new_id = c.lastrowid
    conn.commit()
    conn.close()
    
    # Генерируем ссылку
    bot_username = context.bot.username
    share_link = f"https://t.me/{bot_username}?start=flat_{new_id}"
    
    await update.message.reply_text(
        f"✅ Квартира сохранена!\n\n"
        f"🔗 <b>Ссылка, чтобы поделиться:</b>\n{share_link}",
        parse_mode='HTML'
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отмена.")
    return ConversationHandler.END

# --- АДМИНКА (УДАЛЕНИЕ) ---

async def admin_delete_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    
    conn = sqlite3.connect('real_estate.db')
    c = conn.cursor()
    c.execute("SELECT id, city, rooms FROM flats")
    flats = c.fetchall()
    conn.close()
    
    if not flats:
        await update.message.reply_text("База пуста.")
        return

    keyboard = []
    for f in flats:
        keyboard.append([InlineKeyboardButton(f"❌ {f[1]} | {f[2]} (ID:{f[0]})", callback_data=f'del_{f[0]}')])
    
    await update.message.reply_text("Нажмите для удаления:", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    flat_id = query.data.split('_')[1]
    
    conn = sqlite3.connect('real_estate.db')
    c = conn.cursor()
    c.execute("DELETE FROM flats WHERE id=?", (flat_id,))
    conn.commit()
    conn.close()
    
    await query.message.edit_text(f"🗑 Лот #{flat_id} удален.")

# --- ОБРАБОТКА НАЖАТИЙ ПОЛЬЗОВАТЕЛЯ ---

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data == 'main_menu':
        await show_main_menu(update, context)

    # Меню выбора
    elif data.startswith('city_'):
        city = data.split('_')[1]
        keyboard = [[InlineKeyboardButton(r, callback_data=f'filter_{city}_{r}')] for r in ROOMS]
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='main_menu')])
        await query.message.edit_text(f"📍 {city}:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith('filter_'):
        _, city, rooms = data.split('_')
        conn = sqlite3.connect('real_estate.db')
        c = conn.cursor()
        c.execute("SELECT id, description FROM flats WHERE city=? AND rooms=?", (city, rooms))
        results = c.fetchall()
        conn.close()
        
        if not results:
            kb = [[InlineKeyboardButton("🔙 Назад", callback_data=f'city_{city}')]]
            await query.message.edit_text("Предложений пока нет 😔", reply_markup=InlineKeyboardMarkup(kb))
            return
            
        keyboard = []
        for res in results:
            desc_preview = res[1].split('\n')[0][:30]
            keyboard.append([InlineKeyboardButton(f"📄 {desc_preview}...", callback_data=f'show_{res[0]}')])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=f'city_{city}')])
        await query.message.edit_text(f"Найдено: {len(results)}", reply_markup=InlineKeyboardMarkup(keyboard))

    # Показ
    elif data.startswith('show_'):
        flat_id = data.split('_')[1]
        await show_flat_by_id(update, context, flat_id)

    # Заявка
    elif data.startswith('lead_'):
        flat_id = data.split('_')[1]
        conn = sqlite3.connect('real_estate.db')
        c = conn.cursor()
        c.execute("SELECT city, rooms, description FROM flats WHERE id=?", (flat_id,))
        flat_info = c.fetchone()
        conn.close()

        # Юзеру
        await query.message.delete()
        await query.message.chat.send_message("✅ Заявка отправлена! Менеджер свяжется с вами.", 
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("В начало", callback_data='main_menu')]]))
        
        # В ГРУППУ
        if GROUP_ID and flat_info:
            user = query.from_user
            msg = (f"🔥 <b>НОВАЯ ЗАЯВКА!</b>\n"
                   f"👤: {user.full_name} (@{user.username})\n"
                   f"🏠: {flat_info[0]}, {flat_info[1]}\n"
                   f"💰: {flat_info[2]}")
            try:
                await context.bot.send_message(chat_id=GROUP_ID, text=msg, parse_mode='HTML')
            except: pass

# --- ЗАПУСК ---
if __name__ == '__main__':
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    
    # 1. ОБЩИЙ START (И группа, и личка, и ссылки)
    app.add_handler(CommandHandler('start', start_command))
    
    # 2. АДМИНКА (Добавление)
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^➕ Добавить квартиру$'), admin_add_start)],
        states={
            STATE_CITY: [CallbackQueryHandler(admin_save_city)],
            STATE_ROOMS: [CallbackQueryHandler(admin_save_rooms)],
            STATE_MEDIA: [MessageHandler(filters.PHOTO | filters.VIDEO, admin_save_media)],
            STATE_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_save_final)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    app.add_handler(conv_handler)
    
    # 3. АДМИНКА (Удаление)
    app.add_handler(MessageHandler(filters.Regex('^🗑 Удалить квартиру$'), admin_delete_trigger))
    app.add_handler(CallbackQueryHandler(admin_delete_confirm, pattern='^del_'))
    
    # 4. ОБЫЧНЫЕ КНОПКИ
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    print("Бот запущен!")
    print("1. Добавь бота в группу и напиши там /start")
    print("2. Добавь квартиру и получишь ссылку, чтобы поделиться.")
    app.run_polling()


def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    print("Bot started from Android service...")
    app.run_polling()
