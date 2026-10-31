import os
import json
import threading
import datetime
import urllib.parse
import requests
import time
import random
import base64
import uuid
from flask import Flask
import telebot
from telebot.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, Message, 
    LabeledPrice, ForceReply, ReplyKeyboardMarkup, KeyboardButton,
    CallbackQuery
)

# --- НАСТРОЙКИ ---
BOT_TOKEN = "9060154141:AAG8cxlh63N1dWZW2KnOKXRfAEoB9zNX8ws"
ADMIN_ID = 8068216414
ADMIN_USERNAME = "sladkooe_vino"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# --- БАЗА ДАННЫХ ---
DB_FILE = "users.json"
SETTINGS_FILE = "settings.json"
user_data = {}
promo_codes = {}
settings = {
    "welcome_text": "Привет! Нажми '💬 ИИ-Чат', чтобы начать общение.",
    "price_chat": 20,
    "free_chat_tries": 3,
    "maintenance": False
}
admin_logs = []

def load_db():
    global user_data, promo_codes, settings
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                data = json.load(f)
                user_data = data.get("users", {})
                promo_codes = data.get("promos", {})
        except: user_data = {}; promo_codes = {}
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f: settings.update(json.load(f))
        except: pass

def save_db():
    try:
        with open(DB_FILE, "w") as f: json.dump({"users": user_data, "promos": promo_codes}, f)
        with open(SETTINGS_FILE, "w") as f: json.dump(settings, f)
    except Exception as e: print(f"Ошибка БД: {e}")

load_db()

def get_user_data(user_id, username=None):
    user_id_str = str(user_id)
    if user_id_str not in user_data:
        user_data[user_id_str] = {
            "chat_requests": settings.get("free_chat_tries", 3),
            "username": username,
            "total_generated": 0
        }
        save_db()
    elif username and user_data[user_id_str].get("username") != username:
        user_data[user_id_str]["username"] = username
        save_db()
    return user_data[user_id_str]

def is_admin(user_id, username=None):
    if user_id == ADMIN_ID: return True
    if username and username.lower() == ADMIN_USERNAME.lower(): return True
    return False

def get_ai_chat_response(user_text):
    try:
        url = "https://text.pollinations.ai/" + urllib.parse.quote(user_text)
        response = requests.get(url, timeout=30)
        if response.status_code == 200: return response.text.strip()
    except: pass
    return "❌ ИИ временно недоступен. Попробуй позже."

@app.route('/')
def health(): return "Bot is running"

def run_bot():
    print("Бот запущен...")
    bot.infinity_polling()

def get_main_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("👤 Профиль"), KeyboardButton("💳 Купить"))
    markup.add(KeyboardButton("💬 ИИ-Чат"), KeyboardButton("🆘 Помощь"))
    markup.add(KeyboardButton("🎁 Промокод"))
    return markup

# --- ПОЛЬЗОВАТЕЛЬСКИЕ ФУНКЦИИ ---
@bot.message_handler(commands=['start'])
def start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    get_user_data(user_id, username)
    if settings.get("maintenance") and not is_admin(user_id, username):
        return bot.reply_to(message, "🔧 Бот на техобслуживании. Заходите позже.")
    if is_admin(user_id, username):
        bot.reply_to(message, "👑 Привет, Админ! Жми /admin_menu.", reply_markup=get_main_keyboard())
        return
    bot.reply_to(message, settings.get("welcome_text", "Привет!"), reply_markup=get_main_keyboard())

@bot.message_handler(func=lambda message: message.text == "👤 Профиль")
def profile(message: Message):
    user_id = message.from_user.id
    data = get_user_data(user_id)
    bot.reply_to(message, f"👤 Твой профиль:\nID: {user_id}\nЗапросов к ИИ: {data.get('chat_requests', 0)}")

@bot.message_handler(func=lambda message: message.text == "💳 Купить")
def buy_menu(message: Message):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(f"💬 100 запросов к ИИ ({settings['price_chat']} ⭐)", callback_data="buy_chat"))
    bot.reply_to(message, "Выбери тариф:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "🆘 Помощь")
def help_menu(message: Message):
    bot.reply_to(message, "Нажми '💬 ИИ-Чат' и просто напиши свой вопрос.")

@bot.message_handler(func=lambda message: message.text == "🎁 Промокод")
def promo_button(message: Message):
    msg = bot.reply_to(message, "Введи промокод:", reply_markup=ForceReply())
    bot.register_next_step_handler(msg, process_user_promo)

def process_user_promo(message: Message):
    try:
        code = message.text.strip().upper()
        if code in promo_codes:
            amount = promo_codes.pop(code)
            save_db()
            data = get_user_data(message.from_user.id)
            data["chat_requests"] += amount
            save_db()
            bot.reply_to(message, f"✅ +{amount} запросов к ИИ.")
        else:
            bot.reply_to(message, "❌ Неверный код.")
    except: pass

@bot.message_handler(func=lambda message: message.text == "💬 ИИ-Чат")
def start_chat(message: Message):
    user_id = message.from_user.id
    data = get_user_data(user_id)
    if data.get("chat_requests", 0) <= 0:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(f"🎫 100 запросов ({settings['price_chat']} ⭐)", callback_data="buy_chat"))
        return bot.reply_to(message, "У тебя закончились запросы к ИИ. Купи пакет:", reply_markup=markup)
    bot.reply_to(message, f"💬 Режим чата активирован. Осталось запросов: {data['chat_requests']}. Просто напиши свой вопрос.")

# --- ОБРАБОТЧИК ТЕКСТА (ИИ-ЧАТ) ---
@bot.message_handler(func=lambda message: not message.text.startswith('/') and message.content_type == 'text')
def handle_text(message: Message):
    user_id = message.from_user.id
    data = get_user_data(user_id)
    if settings.get("maintenance"): return
    user_text = message.text.strip()
    if len(user_text) < 2: return
    
    if data.get("chat_requests", 0) > 0:
        bot.send_chat_action(message.chat.id, 'typing')
        answer = get_ai_chat_response(user_text)
        data["chat_requests"] -= 1
        save_db()
        bot.reply_to(message, f"{answer}\n\n(Осталось запросов: {data['chat_requests']})")
    else:
        bot.reply_to(message, "У тебя нет запросов к ИИ. Купи: /buy")

# --- ОПЛАТА ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_'))
def handle_buy_button(call):
    bot.answer_callback_query(call.id)
    if call.data == "buy_chat":
        bot.send_invoice(chat_id=call.message.chat.id, title="100 запросов к ИИ", description="Доступ к текстовому чату", invoice_payload="chat_100", provider_token="", currency="XTR", prices=[LabeledPrice(label="100 запросов", amount=settings['price_chat'])])

@bot.pre_checkout_query_handler(func=lambda query: True)
def checkout(pre_checkout_query): bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def got_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    user_id = message.from_user.id
    data = get_user_data(user_id)
    if payload == "chat_100":
        data["chat_requests"] = data.get("chat_requests", 0) + 100; save_db()
        bot.send_message(user_id, "✅ Начислено 100 запросов к ИИ!")

# --- АДМИН-ПАНЕЛЬ ---
@bot.message_handler(commands=['admin_menu'])
def admin_menu(message: Message):
    if not is_admin(message.from_user.id, message.from_user.username): return
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("👥 Пользователи", callback_data="adm_users_0"))
    markup.add(InlineKeyboardButton("📊 Статистика", callback_data="adm_stats"))
    markup.add(InlineKeyboardButton("🎟 Промокоды", callback_data="adm_promos"))
    markup.add(InlineKeyboardButton("📢 Рассылка", callback_data="adm_broadcast"))
    bot.reply_to(message, "🛠 Админ-панель:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('adm_'))
def handle_admin_buttons(call: CallbackQuery):
    if not is_admin(call.from_user.id, call.from_user.username): return
    bot.answer_callback_query(call.id)
    
    if call.data == "adm_stats":
        total = len(user_data)
        total_req = sum(d.get("chat_requests", 0) for d in user_data.values())
        bot.send_message(call.message.chat.id, f"📊 Всего: {total}\nЗапросов к ИИ на балансах: {total_req}")
    elif call.data == "adm_broadcast":
        msg = bot.send_message(call.message.chat.id, "Текст для рассылки:", reply_markup=ForceReply())
        bot.register_next_step_handler(msg, process_broadcast)
    elif call.data == "adm_promos":
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("➕ Создать", callback_data="promo_create"))
        markup.add(InlineKeyboardButton("📜 Список", callback_data="promo_list"))
        bot.send_message(call.message.chat.id, "🎟 Промокоды:", reply_markup=markup)
    elif call.data.startswith("adm_users_"):
        page = int(call.data.split("_")[2])
        show_users_page(call.message.chat.id, call.message.message_id, page)

def process_broadcast(message):
    count = 0
    for uid in user_data.keys():
        try:
            bot.send_message(uid, f"📢 Сообщение:\n\n{message.text}")
            count += 1; time.sleep(0.05)
        except: pass
    bot.reply_to(message, f"✅ Отправлено {count} юзерам.")

@bot.callback_query_handler(func=lambda call: call.data == "promo_create")
def promo_create_prompt(call: CallbackQuery):
    msg = bot.send_message(call.message.chat.id, "Введи: КОД СУММА (запросов)", reply_markup=ForceReply())
    bot.register_next_step_handler(msg, process_promo_creation)

def process_promo_creation(message):
    try:
        parts = message.text.split()
        promo_codes[parts[0].upper()] = int(parts[1])
        save_db()
        bot.reply_to(message, "✅ Промокод создан.")
    except: bot.reply_to(message, "Ошибка. Введи: КОД СУММА")

@bot.callback_query_handler(func=lambda call: call.data == "promo_list")
def promo_list(call: CallbackQuery):
    text = "🎟 Коды:\n" + "\n".join([f"`{k}` — {v}" for k, v in promo_codes.items()]) if promo_codes else "Нет кодов."
    bot.send_message(call.message.chat.id, text, parse_mode='Markdown')

def show_users_page(chat_id, message_id, page=0):
    users_list = list(user_data.items())
    users_list.sort(key=lambda x: int(x[0]), reverse=True) 
    items_per_page = 8
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    current_page_users = users_list[start_idx:end_idx]
    markup = InlineKeyboardMarkup()
    row = []
    for uid, udata in current_page_users:
        uname = udata.get("username", "без_ника")
        btn_text = f"@{uname}" if uname != "без_ника" else f"ID: {uid}"
        row.append(InlineKeyboardButton(btn_text, callback_data=f"user_manage_{uid}"))
        if len(row) == 2:
            markup.row(*row); row = []
    if row: markup.row(*row)
    nav = []
    if page > 0: nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"adm_users_{page-1}"))
    if end_idx < len(users_list): nav.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"adm_users_{page+1}"))
    if nav: markup.row(*nav)
    markup.add(InlineKeyboardButton("🔙 В меню", callback_data="adm_main"))
    try: bot.edit_message_text(f"👥 Пользователи:", chat_id, message_id, reply_markup=markup)
    except: bot.send_message(chat_id, "👥 Пользователи:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "adm_main")
def back_to_adm_main(call: CallbackQuery):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("👥 Пользователи", callback_data="adm_users_0"))
    markup.add(InlineKeyboardButton("📊 Статистика", callback_data="adm_stats"))
    markup.add(InlineKeyboardButton("🎟 Промокоды", callback_data="adm_promos"))
    markup.add(InlineKeyboardButton("📢 Рассылка", callback_data="adm_broadcast"))
    bot.edit_message_text("🛠 Админ-панель:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('user_manage_'))
def manage_user(call: CallbackQuery):
    uid = call.data.split("_")[2]
    udata = user_data.get(uid)
    if not udata: return
    text = f"👤 @{udata.get('username', 'Нет')}\nID: {uid}\nЗапросы ИИ: {udata.get('chat_requests', 0)}"
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("➕ 10", callback_data=f"act_chat10_{uid}"), InlineKeyboardButton("➕ 50", callback_data=f"act_chat50_{uid}"))
    markup.add(InlineKeyboardButton("🔙 К списку", callback_data="adm_users_0"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('act_'))
def action_user(call: CallbackQuery):
    parts = call.data.split("_")
    action, uid = parts[1], parts[2]
    if uid not in user_data: return
    if action == "chat10": user_data[uid]["chat_requests"] = user_data[uid].get("chat_requests", 0) + 10
    elif action == "chat50": user_data[uid]["chat_requests"] = user_data[uid].get("chat_requests", 0) + 50
    save_db()
    manage_user(call)

if __name__ == '__main__':
    threading.Thread(target=run_bot).start()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
