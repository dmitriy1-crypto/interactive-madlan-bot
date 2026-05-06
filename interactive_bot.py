import os
import json
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ConversationHandler, MessageHandler, filters, ContextTypes

# ---------- НАСТРОЙКИ ----------
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '').strip()
CHAT_ID = os.environ.get('CHAT_ID', '').strip()

CONFIG_FILE = 'config.json'
PRICE_HISTORY_FILE = 'price_history.json'
ADMIN_ID = 5242236154 

# Состояния для диалогов
WAITING_PRICE, WAITING_ZONE, WAITING_ROOMS_MIN, WAITING_ROOMS_MAX = range(4)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ---------- ФУНКЦИИ ДЛЯ РАБОТЫ С КОНФИГУРАЦИЕЙ ----------
def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

def load_price_history():
    try:
        with open(PRICE_HISTORY_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_price_history(history):
    with open(PRICE_HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=4)

def is_allowed(user_id):
    config = load_config()
    allowed_users = config.get('allowed_users', [ADMIN_ID])
    return user_id in allowed_users

def check_price_drops(items):
    history = load_price_history()
    drops = []
    for item in items:
        listing_id = item.get('id')
        current_price = item.get('price')
        if listing_id in history and current_price and history[listing_id] > current_price:
            old_price = history[listing_id]
            diff = old_price - current_price
            pct = (diff / old_price) * 100
            drops.append({
                'id': listing_id,
                'old': old_price,
                'new': current_price,
                'diff': diff,
                'pct': round(pct, 1)
            })
        if current_price:
            history[listing_id] = current_price
    save_price_history(history)
    return drops

# ---------- ОБРАБОТЧИКИ КОМАНД ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    await update.message.reply_text('👋 Привет! Я бот для поиска квартир.\n/filters - мои настройки\n/pause - приостановить поиск')

async def show_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    config = load_config()
    msg = (f"🏙 Зона: {config.get('area', 'не задана')}\n"
           f"💰 Макс. цена: {config.get('max_price', 'не задана')}\n"
           f"🛏 Комнаты: от {config.get('min_rooms', 'не задано')} до {config.get('max_rooms', 'не задано')}")
    await update.message.reply_text(msg)

async def pause_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    global is_paused
    is_paused = not is_paused
    state = "приостановлен" if is_paused else "активен"
    await update.message.reply_text(f"🔴 Бот {state}.")

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    await update.message.reply_text("📊 Функция отчёта пока в разработке.")

# ---------- ДИАЛОГИ ДЛЯ ИЗМЕНЕНИЯ НАСТРОЕК ----------
async def start_set_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return ConversationHandler.END
    await update.message.reply_text("Введите новую максимальную цену:")
    return WAITING_PRICE

async def process_new_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_price = int(update.message.text)
        config = load_config()
        config['max_price'] = new_price
        save_config(config)
        await update.message.reply_text(f"✅ Максимальная цена изменена на {new_price}.")
    except ValueError:
        await update.message.reply_text("❌ Введите число.")
    return ConversationHandler.END

async def start_set_zone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return ConversationHandler.END
    await update.message.reply_text("Введите новый код города (area):")
    return WAITING_ZONE

async def process_new_zone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_zone = update.message.text.strip()
    config = load_config()
    config['area'] = new_zone
    save_config(config)
    await update.message.reply_text(f"✅ Код города изменён на {new_zone}.")
    return ConversationHandler.END

async def start_set_rooms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return ConversationHandler.END
    await update.message.reply_text("Введите минимальное количество комнат:")
    return WAITING_ROOMS_MIN

async def process_min_rooms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        min_rooms = int(update.message.text)
        context.user_data['min_rooms'] = min_rooms
        await update.message.reply_text("Введите максимальное количество комнат:")
        return WAITING_ROOMS_MAX
    except ValueError:
        await update.message.reply_text("❌ Введите число.")
        return WAITING_ROOMS_MIN

async def process_max_rooms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        max_rooms = int(update.message.text)
        min_rooms = context.user_data.get('min_rooms')
        config = load_config()
        config['min_rooms'] = min_rooms
        config['max_rooms'] = max_rooms
        save_config(config)
        await update.message.reply_text(f"✅ Диапазон комнат изменён: {min_rooms}-{max_rooms}.")
    except ValueError:
        await update.message.reply_text("❌ Введите число.")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Операция отменена.")
    return ConversationHandler.END

# ---------- ЗАПУСК ----------
def main():
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Простые команды
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('filters', show_filters))
    application.add_handler(CommandHandler('pause', pause_bot))
    application.add_handler(CommandHandler('report', report))

    # Диалоги для изменения настроек
    price_conv = ConversationHandler(
        entry_points=[CommandHandler('set_price', start_set_price)],
        states={WAITING_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_new_price)]},
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    application.add_handler(price_conv)

    zone_conv = ConversationHandler(
        entry_points=[CommandHandler('set_zone', start_set_zone)],
        states={WAITING_ZONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_new_zone)]},
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    application.add_handler(zone_conv)

    rooms_conv = ConversationHandler(
        entry_points=[CommandHandler('set_rooms', start_set_rooms)],
        states={
            WAITING_ROOMS_MIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_min_rooms)],
            WAITING_ROOMS_MAX: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_max_rooms)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    application.add_handler(rooms_conv)

    logger.info("Бот запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()
