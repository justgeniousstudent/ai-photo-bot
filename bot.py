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
CF_ACCOUNT_ID = "34f552476e3fbf85af57f61be594ffc6"
CF_API_TOKEN = "cfut_qxccfcwH1bNSlvN05G1D7XUpnT1DeBfm5NkpfF0xb330f1e0"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# --- БАЗА ДАННЫХ ---
DB_FILE = "users.json"
SETTINGS_FILE = "settings.json"
user_data = {}
promo_codes = {}
settings = {
    "welcome_text": "Привет! Отправь фото, нажми '🎨 Генерация фото' или '💬 ИИ-Чат'.",
    "price_20": 100,
    "price_sub": 150,
    "price_chat": 20,
    "price_trap": 70,
    "free_tries": 1,
    "free_chat_tries": 3,
    "maintenance": False
}
last_prompt = {}
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

def log_admin(action, admin_id):
    admin_logs.append(f"{datetime.datetime.now().strftime('%H:%M')} - {action}")
    if len(admin_logs) > 30: admin_logs.pop(0)

def get_user_data(user_id, username=None):
    user_id_str = str(user_id)
    if user_id_str not in user_data:
        user_data[user_id_str] = {
            "credits": settings.get("free_tries", 1),
            "chat_requests": settings.get("free_chat_tries", 3),
            "subscription_end": None,
            "username": username,
            "total_generated": 0
        }
        save_db()
    elif username and user_data[user_id_str].get("username") != username:
        user_data[user_id_str]["username"] = username
        save_db()
    return user_data[user_id_str]

def is_subscription_active(user_id):
    data = get_user_data(user_id)
    sub_end = data.get("subscription_end")
    if sub_end and datetime.datetime.fromisoformat(sub_end) > datetime.datetime.now(): return True
    return False

def is_admin(user_id, username=None):
    if user_id == ADMIN_ID: return True
    if username and username.lower() == ADMIN_USERNAME.lower(): return True
    return False

def get_smart_prompt(user_request):
    try:
        url = "https://text.pollinations.ai/" + urllib.parse.quote(f"Create a detailed image generation prompt for: {user_request}. Only output the prompt.")
        response = requests.get(url, timeout=15)
        if response.status_code == 200: return response.text.strip()
    except: pass
    return user_request

def get_ai_chat_response(user_text):
    try:
        url = "https://text.pollinations.ai/" + urllib.parse.quote(user_text)
        response = requests.get(url, timeout=20)
        if response.status_code == 200 and len(response.text.strip()) > 5:
            return response.text.strip()
    except: pass
    try:
        url = "https://api.airforce/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        payload = {"model": "llama-3.1-70b-chat", "messages": [{"role": "user", "content": user_text}], "max_tokens": 500}
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"].strip()
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
    markup.add(KeyboardButton("🎨 Генерация фото"), KeyboardButton("💬 ИИ-Чат"))
    markup.add(KeyboardButton("🎁 Промокод"), KeyboardButton("🧀 Бонус 100 запросов"))
    markup.add(KeyboardButton("🆘 Помощь"))
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
    sub_status = "Активен" if is_subscription_active(user_id) else "Нет"
    bot.reply_to(message, f"👤 Твой профиль:\nID: {user_id}\nГенераций: {data['credits']}\nЗапросов к ИИ: {data.get('chat_requests', 0)}\nБезлимит: {sub_status}\nВсего создано: {data.get('total_generated', 0)}")

@bot.message_handler(func=lambda message: message.text == "💳 Купить")
def buy_menu(message: Message):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(f"🎫 20 генераций ({settings['price_20']} ⭐)", callback_data="buy_pack"))
    markup.add(InlineKeyboardButton(f"♾️ Безлимит на месяц ({settings['price_sub']} ⭐)", callback_data="buy_sub"))
    markup.add(InlineKeyboardButton(f"💬 100 запросов к ИИ ({settings['price_chat']} ⭐)", callback_data="buy_chat"))
    bot.reply_to(message, "Выбери тариф:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "🆘 Помощь")
def help_menu(message: Message):
    bot.reply_to(message, "Отправь фото или нажми '🎨 Генерация фото' / '💬 ИИ-Чат'.")

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
            data["credits"] += amount
            save_db()
            bot.reply_to(message, f"✅ +{amount} кредитов.")
        else:
            bot.reply_to(message, "❌ Неверный код.")
    except: pass

# --- СМЕШНАЯ ФУНКЦИЯ (БОНУС-ЛОВУШКА) ---
@bot.message_handler(func=lambda message: message.text == "🧀 Бонус-Ловушка")
def trap_bonus(message: Message):
    caption = (
        "🧀 Бесплатный сыр только в мышеловке! 🐭\n\n"
        "Хочешь **100 бесплатных запросов** к ИИ и эмодзи свиньи? 🐷\n"
        "Увы, халявы не будет. Но есть выгодное предложение!\n\n"
        "🔥 **Купи 100 запросов к ИИ всего за 70 ⭐**\n"
        "Это на **30% дешевле**, чем покупать по 20 звезд за 20 запросов (вышло бы 100 звезд)!\n\n"
        "Жми кнопку ниже, пока мышеловка не захлопнулась! 👇"
    )
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🧀 Купить 100 запросов за 70 ⭐", callback_data="buy_trap"))
    
    try:
        with open("trap.jpg", "rb") as photo:
            bot.send_photo(
                chat_id=message.chat.id, 
                photo=photo,
                caption=caption,
                reply_markup=markup,
                parse_mode='Markdown'
            )
    except Exception as e:
        print(f"Ошибка отправки фото: {e}")
        bot.send_message(
            chat_id=message.chat.id, 
            text=caption, 
            reply_markup=markup,
            parse_mode='Markdown'
        )

# --- ИИ-ЧАТ ---
@bot.message_handler(func=lambda message: message.text == "💬 ИИ-Чат")
def start_chat(message: Message):
    user_id = message.from_user.id
    data = get_user_data(user_id)
    if data.get("chat_requests", 0) <= 0:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(f"🎫 100 запросов ({settings['price_chat']} ⭐)", callback_data="buy_chat"))
        return bot.reply_to(message, "У тебя закончились запросы к ИИ. Купи пакет:", reply_markup=markup)
    bot.reply_to(message, f"💬 Режим чата активирован. Осталось запросов: {data['chat_requests']}. Просто напиши свой вопрос.")

@bot.message_handler(func=lambda message: message.text == "🎨 Генерация фото")
def start_generation_prompt(message: Message):
    user_id = message.from_user.id
    if settings.get("maintenance"): return bot.reply_to(message, "🔧 Техработы.")
    data = get_user_data(user_id)
    if not is_subscription_active(user_id) and data["credits"] <= 0:
        return bot.reply_to(message, "Генерации закончились. Купи: /buy")
    bot.reply_to(message, "Напиши, что нарисовать:")

# --- ОБРАБОТЧИК ТЕКСТА (ЧАТ И ГЕНЕРАЦИЯ) ---
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
        return
    
    if not is_subscription_active(user_id) and data["credits"] <= 0:
        return bot.reply_to(message, "У тебя нет кредитов. Купи: /buy")
    msg = bot.reply_to(message, "🧠 ИИ придумывает промпт...")
    smart_prompt = get_smart_prompt(user_text)
    process_generation(message.chat.id, user_id, data, smart_prompt, msg.message_id)

# --- ОПЛАТА ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_'))
def handle_buy_button(call):
    bot.answer_callback_query(call.id)
    if call.data == "buy_pack":
        bot.send_invoice(chat_id=call.message.chat.id, title="20 генераций", description="Разовая покупка", invoice_payload="pack_20", provider_token="", currency="XTR", prices=[LabeledPrice(label="20 генераций", amount=settings['price_20'])])
    elif call.data == "buy_sub":
        bot.send_invoice(chat_id=call.message.chat.id, title="Безлимит", description="30 дней", invoice_payload="sub_month", provider_token="", currency="XTR", prices=[LabeledPrice(label="Безлимит", amount=settings['price_sub'])])
    elif call.data == "buy_chat":
        bot.send_invoice(chat_id=call.message.chat.id, title="100 запросов к ИИ", description="Доступ к текстовому чату", invoice_payload="chat_100", provider_token="", currency="XTR", prices=[LabeledPrice(label="100 запросов", amount=settings['price_chat'])])
    elif call.data == "buy_trap":
        bot.send_invoice(chat_id=call.message.chat.id, title="100 запросов к ИИ (Выгодно!)", description="Специальное предложение", invoice_payload="chat_100_trap", provider_token="", currency="XTR", prices=[LabeledPrice(label="100 запросов (Ловушка)", amount=settings['price_trap'])])

@bot.pre_checkout_query_handler(func=lambda query: True)
def checkout(pre_checkout_query): bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def got_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    user_id = message.from_user.id
    data = get_user_data(user_id)
    if payload == "pack_20":
        data["credits"] += 20; save_db()
        bot.send_message(user_id, "✅ Начислено 20 генераций!")
    elif payload == "sub_month":
        data["subscription_end"] = (datetime.datetime.now() + datetime.timedelta(days=30)).isoformat(); save_db()
        bot.send_message(user_id, "✅ Безлимит на 30 дней!")
    elif payload == "chat_100":
        data["chat_requests"] = data.get("chat_requests", 0) + 100; save_db()
        bot.send_message(user_id, "✅ Начислено 100 запросов к ИИ!")
    elif payload == "chat_100_trap":
        data["chat_requests"] = data.get("chat_requests", 0) + 100; save_db()
        bot.send_message(user_id, "🧀 Поздравляю! Ты попался в мышеловку и купил 100 запросов за 70 звезд! Начислено!")

# --- ГЕНЕРАЦИЯ И ОСТАЛЬНОЕ ---
@bot.message_handler(content_types=['photo'])
def handle_photo(message: Message):
    user_id = message.from_user.id
    if settings.get("maintenance"): return bot.reply_to(message, "🔧 Техработы.")
    data = get_user_data(user_id)
    if not is_subscription_active(user_id) and data["credits"] <= 0:
        return bot.reply_to(message, "Генерации закончились. Купи: /buy")
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✨ Улучшить", callback_data="style_enhance"))
    markup.add(InlineKeyboardButton("🎨 Аниме", callback_data="style_anime"))
    bot.reply_to(message, "Выбери стиль:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('style_'))
def handle_style(call):
    user_id = call.from_user.id
    data = get_user_data(user_id)
    if not is_subscription_active(user_id) and data.get("credits", 0) <= 0:
        return bot.answer_callback_query(call.id, "Нет генераций! Купи: /buy")
    bot.answer_callback_query(call.id)
    process_generation(call.message.chat.id, user_id, data, call.data, call.message.message_id)

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
        total_gen = sum(d.get("total_generated", 0) for d in user_data.values())
        bot.send_message(call.message.chat.id, f"📊 Всего: {total}\nКартинок: {total_gen}")
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
    msg = bot.send_message(call.message.chat.id, "Введи: КОД СУММА (кредитов)", reply_markup=ForceReply())
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
    text = f"👤 @{udata.get('username', 'Нет')}\nID: {uid}\nКредиты: {udata.get('credits', 0)}\nЗапросы ИИ: {udata.get('chat_requests', 0)}"
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("➕ 10", callback_data=f"act_cred10_{uid}"), InlineKeyboardButton("➕ 50", callback_data=f"act_cred50_{uid}"))
    markup.row(InlineKeyboardButton("💬 +10 ИИ", callback_data=f"act_chat10_{uid}"), InlineKeyboardButton("💬 +50 ИИ", callback_data=f"act_chat50_{uid}"))
    markup.add(InlineKeyboardButton("🔙 К списку", callback_data="adm_users_0"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('act_'))
def action_user(call: CallbackQuery):
    parts = call.data.split("_")
    action, uid = parts[1], parts[2]
    if uid not in user_data: return
    if action == "cred10": user_data[uid]["credits"] += 10
    elif action == "cred50": user_data[uid]["credits"] += 50
    elif action == "chat10": user_data[uid]["chat_requests"] = user_data[uid].get("chat_requests", 0) + 10
    elif action == "chat50": user_data[uid]["chat_requests"] = user_data[uid].get("chat_requests", 0) + 50
    save_db()
    manage_user(call)

# --- ГЕНЕРАЦИЯ (3 ИИ) ---
def process_generation(chat_id, user_id, data, prompt, message_id, is_custom=False):
    bot.edit_message_text("⏳ Рисую... (Пробую Cloudflare)", chat_id, message_id)
    image_bytes = None
    
    try:
        cf_url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/black-forest-labs/flux-1-schnell"
        cf_headers = {"Authorization": f"Bearer {CF_API_TOKEN}", "Content-Type": "application/json"}
        cf_resp = requests.post(cf_url, headers=cf_headers, json={"prompt": prompt}, timeout=40)
        if cf_resp.status_code == 200:
            result = cf_resp.json()
            if "result" in result and "image" in result["result"]:
                image_bytes = base64.b64decode(result["result"]["image"])
    except Exception as e: print(f"CF Error: {e}")

    if image_bytes is None:
        bot.edit_message_text("⏳ Cloudflare занят. Пробую Together...", chat_id, message_id)
        try:
            tg_resp = requests.post("https://api.together.xyz/v1/images/generations", 
                json={"model": "black-forest-labs/FLUX.1-schnell-Free", "prompt": prompt, "width": 512, "height": 512, "steps": 4, "n": 1}, timeout=60)
            if tg_resp.status_code == 200:
                tg_result = tg_resp.json()
                if "data" in tg_result and len(tg_result["data"]) > 0:
                    img_url = tg_result["data"][0].get("url")
                    if img_url:
                        img_resp = requests.get(img_url, timeout=30)
                        if img_resp.status_code == 200: image_bytes = img_resp.content
        except Exception as e: print(f"Together Error: {e}")

    if image_bytes is None:
        bot.edit_message_text("⏳ Together занят. Пробую Pollinations...", chat_id, message_id)
        try:
            encoded_prompt = urllib.parse.quote(prompt)
            img_resp = requests.get(f"https://gen.pollinations.ai/image/{encoded_prompt}?width=512&height=512&nologo=true", timeout=40)
            if img_resp.status_code == 200 and img_resp.headers.get('content-type', '').startswith('image'):
                image_bytes = img_resp.content
        except Exception as e: print(f"Pollinations Error: {e}")

    if image_bytes:
        bot.send_photo(chat_id=chat_id, photo=image_bytes, caption="✅ Готово!")
        data["total_generated"] = data.get("total_generated", 0) + 1
        if not is_subscription_active(user_id):
            data["credits"] -= 1; save_db()
            bot.send_message(user_id, f"Осталось: {data['credits']}", reply_markup=get_main_keyboard())
        else:
            save_db()
            bot.send_message(user_id, "Безлимит ♾️", reply_markup=get_main_keyboard())
    else:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔄 Попробовать снова", callback_data=f"retry_{user_id}"))
        bot.edit_message_text("❌ Все серверы заняты. Попробуй позже.", chat_id, message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('retry_'))
def handle_retry(call: CallbackQuery):
    user_id = int(call.data.split("_")[1])
    if call.from_user.id != user_id:
        return bot.answer_callback_query(call.id, "Это не твоя кнопка.")
    data = get_user_data(user_id)
    if not is_subscription_active(user_id) and data["credits"] <= 0:
        return bot.answer_callback_query(call.id, "Генерации закончились. Купи: /buy")
    bot.answer_callback_query(call.id)
    bot.edit_message_text("⏳ Повторная попытка...", call.message.chat.id, call.message.message_id)
    process_generation(call.message.chat.id, user_id, data, "random", call.message.message_id)

if __name__ == '__main__':
    threading.Thread(target=run_bot).start()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
