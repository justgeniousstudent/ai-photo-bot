import os
import json
import threading
import datetime
import urllib.parse
import requests
import time
import random
import base64
from flask import Flask
import telebot
from telebot.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, Message, 
    LabeledPrice, ForceReply, ReplyKeyboardMarkup, KeyboardButton,
    CallbackQuery
)

# --- НАСТРОЙКИ ---
BOT_TOKEN = "9060154141:AAESRS4f1L2anR8Zj504SjvIP-pkTa2gFRY"
ADMIN_ID = 8068216414
ADMIN_USERNAME = "sladkooe_vino"

# --- CLOUDFLARE WORKERS AI ---
CF_ACCOUNT_ID = "34f552476e3fbf85af57f61be594ffc6"
CF_API_TOKEN = "cfut_qxccfcwH1bNSlvN05G1D7XUpnT1DeBfm5NkpfF0xb330f1e0"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# --- БАЗА ДАННЫХ ---
DB_FILE = "users.json"
user_data = {}
promo_codes = {}
photo_storage = {}
waiting_for_prompt = {}
waiting_for_generation_text = {}

def load_db():
    global user_data, promo_codes
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                data = json.load(f)
                user_data = data.get("users", {})
                promo_codes = data.get("promos", {})
        except:
            user_data = {}
            promo_codes = {}
    else:
        user_data = {}
        promo_codes = {}

def save_db():
    try:
        with open(DB_FILE, "w") as f:
            json.dump({"users": user_data, "promos": promo_codes}, f)
    except Exception as e:
        print(f"Ошибка сохранения БД: {e}")

load_db()

def get_user_data(user_id, username=None):
    user_id_str = str(user_id)
    if user_id_str not in user_data:
        user_data[user_id_str] = {"credits": 1, "subscription_end": None, "username": username, "banned": False, "total_generated": 0}
        save_db()
    elif username and user_data[user_id_str].get("username") != username:
        user_data[user_id_str]["username"] = username
        save_db()
    return user_data[user_id_str]

def is_subscription_active(user_id):
    data = get_user_data(user_id)
    sub_end = data.get("subscription_end")
    if sub_end and datetime.datetime.fromisoformat(sub_end) > datetime.datetime.now():
        return True
    return False

def is_admin(user_id, username=None):
    if user_id == ADMIN_ID:
        return True
    if username and username.lower() == ADMIN_USERNAME.lower():
        return True
    return False

def is_banned(user_id):
    return get_user_data(user_id).get("banned", False)

# --- УМНЫЙ ПРОМПТ ---
def get_smart_prompt(user_request):
    try:
        url = "https://text.pollinations.ai/" + urllib.parse.quote(f"Create a detailed image generation prompt for: {user_request}. Only output the prompt.")
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            return response.text.strip()
    except:
        pass
    return user_request

@app.route('/')
def health():
    return "Bot is running"

def run_bot():
    print("Бот запущен...")
    bot.infinity_polling()

# --- КЛАВИАТУРА ---
def get_main_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("👤 Профиль"), KeyboardButton("💳 Купить"))
    markup.add(KeyboardButton("🎨 Генерация фото"), KeyboardButton("🆘 Помощь"))
    markup.add(KeyboardButton("🎁 Промокод"))
    return markup

# --- КОМАНДЫ ---
@bot.message_handler(commands=['start'])
def start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    
    if is_banned(user_id):
        return bot.reply_to(message, "🚫 Вы забанены в этом боте.")
        
    get_user_data(user_id, username)
    
    if is_admin(user_id, username):
        bot.reply_to(message, "👑 Привет, Админ! Жми /admin_menu.", reply_markup=get_main_keyboard())
        return
    
    data = get_user_data(user_id)
    if data["credits"] == 1 and not is_subscription_active(user_id):
        bot.reply_to(message, "Привет! Отправь мне фото для обработки или нажми '🎨 Генерация фото'. У тебя есть 1 бесплатная попытка!", reply_markup=get_main_keyboard())
    else:
        bot.reply_to(message, "Привет! Отправь мне фото для обработки или нажми '🎨 Генерация фото'.", reply_markup=get_main_keyboard())

# --- АДМИНСКОЕ МЕНЮ ---
@bot.message_handler(commands=['admin_menu'])
def admin_menu(message: Message):
    if not is_admin(message.from_user.id, message.from_user.username): return
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("👥 Пользователи", callback_data="adm_users_0"))
    markup.add(InlineKeyboardButton("🏆 Топ", callback_data="adm_top"))
    markup.add(InlineKeyboardButton("🎲 Розыгрыш", callback_data="adm_giveaway"))
    markup.add(InlineKeyboardButton("🎟 Промокоды", callback_data="adm_promos"))
    markup.add(InlineKeyboardButton("📢 Рассылка", callback_data="adm_broadcast"))
    markup.add(InlineKeyboardButton("📊 Статистика", callback_data="adm_stats"))
    markup.add(InlineKeyboardButton("🔍 Поиск юзера", callback_data="adm_find"))
    markup.add(InlineKeyboardButton("⚙️ Настройки", callback_data="adm_settings"))
    bot.reply_to(message, "🛠 Админ-панель:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('adm_'))
def handle_admin_buttons(call: CallbackQuery):
    if not is_admin(call.from_user.id, call.from_user.username): return
    bot.answer_callback_query(call.id)
    
    if call.data == "adm_stats":
        total_users = len(user_data)
        banned = sum(1 for d in user_data.values() if d.get("banned"))
        total_gen = sum(d.get("total_generated", 0) for d in user_data.values())
        total_credits = sum(d.get("credits", 0) for d in user_data.values())
        bot.send_message(call.message.chat.id, f"📊 Статистика:\nВсего: {total_users}\nЗабанено: {banned}\nВсего картинок: {total_gen}\nКредитов на балансах: {total_credits}")
    
    elif call.data == "adm_top":
        sorted_users = sorted(user_data.items(), key=lambda item: item[1].get("total_generated", 0), reverse=True)[:5]
        text = "🏆 Топ-5:\n"
        for i, (uid, udata) in enumerate(sorted_users, 1):
            text += f"{i}. @{udata.get('username', uid)} — {udata.get('total_generated', 0)} шт.\n"
        bot.send_message(call.message.chat.id, text)
        
    elif call.data == "adm_giveaway":
        if not user_data: return bot.send_message(call.message.chat.id, "Нет пользователей.")
        winner_id = random.choice(list(user_data.keys()))
        winner = user_data[winner_id]
        winner["credits"] += 5
        save_db()
        bot.send_message(call.message.chat.id, f"🎲 Победитель: @{winner.get('username', winner_id)}. +5 кредитов.")
        try: bot.send_message(winner_id, "🎉 Ты выиграл 5 генераций!")
        except: pass
        
    elif call.data == "adm_broadcast":
        msg = bot.send_message(call.message.chat.id, "Введи текст для рассылки:", reply_markup=ForceReply())
        bot.register_next_step_handler(msg, process_broadcast)
        
    elif call.data == "adm_promos":
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("➕ Создать", callback_data="promo_create"))
        markup.add(InlineKeyboardButton("📜 Список", callback_data="promo_list"))
        bot.send_message(call.message.chat.id, "🎟 Промокоды:", reply_markup=markup)
        
    elif call.data == "adm_find":
        msg = bot.send_message(call.message.chat.id, "Введи ID или @username для поиска:", reply_markup=ForceReply())
        bot.register_next_step_handler(msg, process_find_user)
        
    elif call.data == "adm_settings":
        bot.send_message(call.message.chat.id, "⚙️ Настройки:\n(Здесь можно добавить смену приветствия, но пока заглушка)")
        
    elif call.data.startswith("adm_users_"):
        page = int(call.data.split("_")[2])
        show_users_page(call.message.chat.id, call.message.message_id, page)

# --- ПОИСК ЮЗЕРА ---
def process_find_user(message: Message):
    if not is_admin(message.from_user.id, message.from_user.username): return
    target = message.text.strip()
    target_id = find_user_id(target)
    if not target_id:
        return bot.reply_to(message, "Не найден.")
    class FakeCall:
        def __init__(self, uid):
            self.data = f"user_manage_{uid}"
            self.from_user = message.from_user
            self.message = message
    manage_user(FakeCall(target_id))

# --- ПРОМОКОДЫ ---
@bot.callback_query_handler(func=lambda call: call.data == "promo_create")
def promo_create_prompt(call: CallbackQuery):
    if not is_admin(call.from_user.id, call.from_user.username): return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "Введи: КОД СУММА (например: START 10)", reply_markup=ForceReply())
    bot.register_next_step_handler(msg, process_promo_creation)

def process_promo_creation(message: Message):
    if not is_admin(message.from_user.id, message.from_user.username): return
    try:
        parts = message.text.split()
        code, amount = parts[0].upper(), int(parts[1])
        promo_codes[code] = amount
        save_db()
        bot.reply_to(message, f"✅ Промокод {code} на {amount} кредитов.")
    except:
        bot.reply_to(message, "Ошибка. Введи: КОД СУММА")

@bot.callback_query_handler(func=lambda call: call.data == "promo_list")
def promo_list(call: CallbackQuery):
    if not is_admin(call.from_user.id, call.from_user.username): return
    bot.answer_callback_query(call.id)
    if not promo_codes:
        return bot.send_message(call.message.chat.id, "Промокодов нет.")
    text = "🎟 Активные коды:\n" + "\n".join([f"`{k}` — {v}" for k, v in promo_codes.items()])
    bot.send_message(call.message.chat.id, text, parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == "🎁 Промокод")
def promo_button(message: Message):
    if is_banned(message.from_user.id): return
    msg = bot.reply_to(message, "Введи промокод:", reply_markup=ForceReply())
    bot.register_next_step_handler(msg, process_user_promo)

def process_user_promo(message: Message):
    if is_banned(message.from_user.id): return
    try:
        code = message.text.strip().upper()
        if code in promo_codes:
            amount = promo_codes.pop(code)
            save_db()
            data = get_user_data(message.from_user.id)
            data["credits"] += amount
            save_db()
            bot.reply_to(message, f"✅ Активирован! +{amount} кредитов.")
        else:
            bot.reply_to(message, "❌ Неверный код.")
    except:
        bot.reply_to(message, "Ошибка.")

# --- СПИСОК ПОЛЬЗОВАТЕЛЕЙ ---
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
            markup.row(*row)
            row = []
    if row: markup.row(*row)
    
    nav = []
    if page > 0: nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"adm_users_{page-1}"))
    if end_idx < len(users_list): nav.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"adm_users_{page+1}"))
    if nav: markup.row(*nav)
    markup.add(InlineKeyboardButton("🔙 В меню", callback_data="adm_main"))
    
    try: bot.edit_message_text(f"👥 Пользователи (Стр. {page+1}):", chat_id, message_id, reply_markup=markup)
    except: bot.send_message(chat_id, f"👥 Пользователи (Стр. {page+1}):", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "adm_main")
def back_to_adm_main(call: CallbackQuery):
    if not is_admin(call.from_user.id, call.from_user.username): return
    bot.answer_callback_query(call.id)
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("👥 Пользователи", callback_data="adm_users_0"))
    markup.add(InlineKeyboardButton("🏆 Топ", callback_data="adm_top"))
    markup.add(InlineKeyboardButton("🎲 Розыгрыш", callback_data="adm_giveaway"))
    markup.add(InlineKeyboardButton("🎟 Промокоды", callback_data="adm_promos"))
    markup.add(InlineKeyboardButton("📢 Рассылка", callback_data="adm_broadcast"))
    markup.add(InlineKeyboardButton("📊 Статистика", callback_data="adm_stats"))
    markup.add(InlineKeyboardButton("🔍 Поиск юзера", callback_data="adm_find"))
    markup.add(InlineKeyboardButton("⚙️ Настройки", callback_data="adm_settings"))
    bot.edit_message_text("🛠 Админ-панель:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('user_manage_'))
def manage_user(call: CallbackQuery):
    if not is_admin(call.from_user.id, call.from_user.username): return
    bot.answer_callback_query(call.id)
    uid = call.data.split("_")[2]
    udata = user_data.get(uid)
    if not udata: return bot.edit_message_text("Не найден.", call.message.chat.id, call.message.message_id)
        
    text = f"👤 @{udata.get('username', 'Нет')}\nID: {uid}\nКредиты: {udata.get('credits', 0)}\nБан: {'Да' if udata.get('banned') else 'Нет'}"
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("➕ 10", callback_data=f"act_cred10_{uid}"), InlineKeyboardButton("➕ 50", callback_data=f"act_cred50_{uid}"))
    markup.row(InlineKeyboardButton("♾️ Безлимит", callback_data=f"act_sub_{uid}"), InlineKeyboardButton("❌ Снять", callback_data=f"act_unsub_{uid}"))
    markup.row(InlineKeyboardButton("🚫 Бан/Разбан", callback_data=f"act_ban_{uid}"), InlineKeyboardButton("🗑 Удалить", callback_data=f"act_del_{uid}"))
    markup.add(InlineKeyboardButton("🔙 К списку", callback_data="adm_users_0"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('act_'))
def action_user(call: CallbackQuery):
    if not is_admin(call.from_user.id, call.from_user.username): return
    bot.answer_callback_query(call.id)
    parts = call.data.split("_")
    action, uid = parts[1], parts[2]
    if uid not in user_data: return
    
    if action == "cred10": user_data[uid]["credits"] += 10
    elif action == "cred50": user_data[uid]["credits"] += 50
    elif action == "sub": user_data[uid]["subscription_end"] = (datetime.datetime.now() + datetime.timedelta(days=30)).isoformat()
    elif action == "unsub": user_data[uid]["subscription_end"] = None
    elif action == "ban": user_data[uid]["banned"] = not user_data[uid].get("banned", False)
    elif action == "del": del user_data[uid]; save_db(); return bot.edit_message_text("Удален.", call.message.chat.id, call.message.message_id)
    save_db()
    manage_user(call)

# --- РАССЫЛКА ---
def process_broadcast(message: Message):
    if not is_admin(message.from_user.id, message.from_user.username): return
    text = message.text
    count = 0
    for uid in user_data.keys():
        try:
            bot.send_message(uid, f"📢 Сообщение от админа:\n\n{text}")
            count += 1
            time.sleep(0.05)
        except: pass
    bot.reply_to(message, f"✅ Отправлено {count} юзерам.")

def find_user_id(target):
    if target.isdigit(): return target
    elif target.startswith('@'):
        username = target[1:].lower()
        for uid, udata in user_data.items():
            if udata.get("username") and udata.get("username").lower() == username:
                return uid
    return None

# --- ПОЛЬЗОВАТЕЛЬСКИЕ КНОПКИ ---
@bot.message_handler(func=lambda message: message.text == "👤 Профиль")
def profile(message: Message):
    if is_banned(message.from_user.id): return
    user_id = message.from_user.id
    data = get_user_data(user_id)
    sub_status = "Активен" if is_subscription_active(user_id) else "Нет"
    bot.reply_to(message, f"👤 Твой профиль:\nID: {user_id}\nГенераций: {data['credits']}\nБезлимит: {sub_status}\nВсего создано: {data.get('total_generated', 0)}")

@bot.message_handler(func=lambda message: message.text == "💳 Купить")
def buy_menu(message: Message):
    if is_banned(message.from_user.id): return
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🎫 20 генераций (100 ⭐)", callback_data="buy_pack"))
    markup.add(InlineKeyboardButton("♾️ Безлимит на месяц (150 ⭐)", callback_data="buy_sub"))
    bot.reply_to(message, "Выбери тариф:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "🆘 Помощь")
def help_menu(message: Message):
    if is_banned(message.from_user.id): return
    bot.reply_to(message, "Отправь фото и выбери стиль. Или нажми '🎨 Генерация фото'.\n\nПромокод: кнопка '🎁 Промокод'.")

@bot.message_handler(commands=['buy'])
def buy(message: Message):
    if is_banned(message.from_user.id): return
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🎫 20 генераций (100 ⭐)", callback_data="buy_pack"))
    markup.add(InlineKeyboardButton("♾️ Безлимит на месяц (150 ⭐)", callback_data="buy_sub"))
    bot.reply_to(message, "Выбери тариф:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "🎨 Генерация фото")
def start_generation(message: Message):
    user_id = message.from_user.id
    if is_banned(user_id): return
    data = get_user_data(user_id)
    if not is_subscription_active(user_id) and data["credits"] <= 0:
        return bot.reply_to(message, "Генерации закончились. Купи: /buy")
    waiting_for_generation_text[user_id] = True
    bot.reply_to(message, "Напиши, что нарисовать (например: 'кот в космосе'):", reply_markup=ForceReply())

@bot.message_handler(func=lambda message: message.from_user.id in waiting_for_generation_text)
def handle_generation_text(message: Message):
    user_id = message.from_user.id
    data = get_user_data(user_id)
    user_text = message.text
    waiting_for_generation_text.pop(user_id, None)
    if not is_subscription_active(user_id) and data["credits"] <= 0:
        return bot.reply_to(message, "Генерации закончились. Купи: /buy")
    msg = bot.reply_to(message, "🧠 ИИ придумывает промпт...")
    smart_prompt = get_smart_prompt(user_text)
    process_generation(message.chat.id, user_id, data, smart_prompt, msg.message_id)

# --- ОПЛАТА ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_'))
def handle_buy_button(call):
    bot.answer_callback_query(call.id)
    if call.data == "buy_pack":
        bot.send_invoice(chat_id=call.message.chat.id, title="20 генераций", description="Разовая покупка", invoice_payload="pack_20", provider_token="", currency="XTR", prices=[LabeledPrice(label="20 генераций", amount=100)])
    elif call.data == "buy_sub":
        bot.send_invoice(chat_id=call.message.chat.id, title="Безлимит", description="30 дней", invoice_payload="sub_month", provider_token="", currency="XTR", prices=[LabeledPrice(label="Безлимит", amount=150)])

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

# --- ФОТО И ГЕНЕРАЦИЯ (CLOUDFLARE WORKERS AI) ---
@bot.message_handler(content_types=['photo'])
def handle_photo(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    if is_banned(user_id): return
    data = get_user_data(user_id, username)
    if not is_subscription_active(user_id) and data["credits"] <= 0:
        return bot.reply_to(message, "Генерации закончились. Купи: /buy", reply_markup=get_main_keyboard())
    photo_storage[user_id] = message.photo[-1].file_id 
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✨ Улучшить", callback_data="style_enhance"))
    markup.add(InlineKeyboardButton("🎨 Аниме", callback_data="style_anime"))
    bot.reply_to(message, "Выбери стиль:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('style_'))
def handle_style(call):
    user_id = call.from_user.id
    if is_banned(user_id): return
    data = get_user_data(user_id)
    if not is_subscription_active(user_id) and data.get("credits", 0) <= 0:
        return bot.answer_callback_query(call.id, "Нет генераций! Купи: /buy")
    bot.answer_callback_query(call.id)
    if not photo_storage.get(user_id):
        return bot.send_message(call.message.chat.id, "Ошибка: фото не найдено.")
    process_generation(call.message.chat.id, user_id, data, call.data, call.message.message_id)

def process_generation(chat_id, user_id, data, prompt, message_id, is_custom=False):
    api_url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}", "Content-Type": "application/json"}
    payload = {"prompt": prompt}
    
    bot.edit_message_text("⏳ Нейросеть (Cloudflare) рисует...", chat_id, message_id)
    
    # Делаем 3 попытки
    for attempt in range(3):
        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                if "result" in result and "image" in result["result"]:
                    image_bytes = base64.b64decode(result["result"]["image"])
                    bot.send_photo(chat_id=chat_id, photo=image_bytes, caption="✅ Готово!")
                    
                    data["total_generated"] = data.get("total_generated", 0) + 1
                    if not is_subscription_active(user_id):
                        data["credits"] -= 1
                        save_db()
                        bot.send_message(user_id, f"Осталось: {data['credits']}", reply_markup=get_main_keyboard())
                    else:
                        save_db()
                        bot.send_message(user_id, "Безлимит ♾️", reply_markup=get_main_keyboard())
                    return # Успех
                else:
                    print(f"CF Error: нет картинки в ответе. {result}")
            
            # Если ошибка (не 200), пробуем еще раз
            if attempt < 2:
                bot.edit_message_text(f"⏳ Сервер перегружен. Пробую еще раз... (попытка {attempt+2})", chat_id, message_id)
                time.sleep(5)
            else:
                bot.edit_message_text("❌ Сервер перегружен после 3 попыток. Попробуй позже.", chat_id, message_id)
                
        except Exception as e:
            print(f"Ошибка генерации (попытка {attempt+1}): {e}")
            if attempt < 2:
                time.sleep(5)
            else:
                bot.edit_message_text("❌ Ошибка при генерации. Попробуй позже.", chat_id, message_id)

# --- ЗАПУСК ---
if __name__ == '__main__':
    threading.Thread(target=run_bot).start()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
