import os
import json
import threading
import datetime
import urllib.parse
import requests
import time
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

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# --- БАЗА ДАННЫХ ---
DB_FILE = "users.json"
user_data = {}
photo_storage = {}
waiting_for_prompt = {}
waiting_for_generation_text = {}

def load_db():
    global user_data
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                user_data = json.load(f)
            if not isinstance(user_data, dict):
                user_data = {}
        except:
            user_data = {}
    else:
        user_data = {}

def save_db():
    try:
        with open(DB_FILE, "w") as f:
            json.dump(user_data, f)
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
    markup.add(InlineKeyboardButton("👥 Список пользователей", callback_data="adm_users_0"))
    markup.add(InlineKeyboardButton("🏆 Топ генераторов", callback_data="adm_top"))
    markup.add(InlineKeyboardButton("📢 Сделать рассылку", callback_data="adm_broadcast"))
    markup.add(InlineKeyboardButton("📊 Общая статистика", callback_data="adm_stats"))
    bot.reply_to(message, "🛠 Админ-панель:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('adm_'))
def handle_admin_buttons(call: CallbackQuery):
    if not is_admin(call.from_user.id, call.from_user.username): return
    bot.answer_callback_query(call.id)
    
    if call.data == "adm_stats":
        total_users = len(user_data)
        banned = sum(1 for d in user_data.values() if d.get("banned"))
        total_gen = sum(d.get("total_generated", 0) for d in user_data.values())
        bot.send_message(call.message.chat.id, f"📊 Статистика:\nВсего: {total_users}\nЗабанено: {banned}\nВсего картинок: {total_gen}")
    
    elif call.data == "adm_top":
        sorted_users = sorted(user_data.items(), key=lambda item: item[1].get("total_generated", 0), reverse=True)[:5]
        text = "🏆 Топ-5:\n"
        for i, (uid, udata) in enumerate(sorted_users, 1):
            text += f"{i}. @{udata.get('username', uid)} — {udata.get('total_generated', 0)} шт.\n"
        bot.send_message(call.message.chat.id, text)
        
    elif call.data == "adm_broadcast":
        msg = bot.send_message(call.message.chat.id, "Введи текст для рассылки:", reply_markup=ForceReply())
        bot.register_next_step_handler(msg, process_broadcast)
    
    # Логика списка пользователей (постранично)
    elif call.data.startswith("adm_users_"):
        page = int(call.data.split("_")[2])
        show_users_page(call.message.chat.id, call.message.message_id, page)

def show_users_page(chat_id, message_id, page=0):
    users_list = list(user_data.items())
    # Сортируем по ID (или можно по дате регистрации)
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
        if len(row) == 2: # По 2 кнопки в ряд
            markup.row(*row)
            row = []
    if row: markup.row(*row)
    
    # Кнопки навигации
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"adm_users_{page-1}"))
    if end_idx < len(users_list):
        nav.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"adm_users_{page+1}"))
    if nav: markup.row(*nav)
    
    markup.add(InlineKeyboardButton("🔙 В админ-меню", callback_data="adm_main"))
    
    try:
        bot.edit_message_text(f"👥 Пользователи (Стр. {page+1}):", chat_id, message_id, reply_markup=markup)
    except:
        bot.send_message(chat_id, f"👥 Пользователи (Стр. {page+1}):", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "adm_main")
def back_to_adm_main(call: CallbackQuery):
    if not is_admin(call.from_user.id, call.from_user.username): return
    bot.answer_callback_query(call.id)
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("👥 Список пользователей", callback_data="adm_users_0"))
    markup.add(InlineKeyboardButton("🏆 Топ генераторов", callback_data="adm_top"))
    markup.add(InlineKeyboardButton("📢 Сделать рассылку", callback_data="adm_broadcast"))
    markup.add(InlineKeyboardButton("📊 Общая статистика", callback_data="adm_stats"))
    bot.edit_message_text("🛠 Админ-панель:", call.message.chat.id, call.message.message_id, reply_markup=markup)

# --- УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЕМ ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('user_manage_'))
def manage_user(call: CallbackQuery):
    if not is_admin(call.from_user.id, call.from_user.username): return
    bot.answer_callback_query(call.id)
    
    uid = call.data.split("_")[2]
    udata = user_data.get(uid)
    if not udata:
        return bot.edit_message_text("Пользователь не найден.", call.message.chat.id, call.message.message_id)
        
    uname = udata.get("username", "Нет ника")
    banned = "🚫 Забанен" if udata.get("banned") else "✅ Активен"
    sub = "♾️ Да" if is_subscription_active(uid) else "❌ Нет"
    
    text = (f"👤 Карточка: @{uname}\n"
            f"ID: {uid}\n"
            f"Статус: {banned}\n"
            f"Кредиты: {udata.get('credits', 0)}\n"
            f"Безлимит: {sub}\n"
            f"Сгенерировано: {udata.get('total_generated', 0)}")
    
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("➕ 10 кредитов", callback_data=f"act_cred10_{uid}"), 
               InlineKeyboardButton("➕ 50 кредитов", callback_data=f"act_cred50_{uid}"))
    markup.row(InlineKeyboardButton("♾️ Дать безлимит", callback_data=f"act_sub_{uid}"),
               InlineKeyboardButton("❌ Снять безлимит", callback_data=f"act_unsub_{uid}"))
    
    ban_text = "✅ Разбанить" if udata.get("banned") else "🚫 Забанить"
    markup.row(InlineKeyboardButton(ban_text, callback_data=f"act_ban_{uid}"))
    markup.row(InlineKeyboardButton("🗑 Удалить юзера", callback_data=f"act_del_{uid}"))
    markup.row(InlineKeyboardButton("🔙 К списку", callback_data="adm_users_0"))
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('act_'))
def action_user(call: CallbackQuery):
    if not is_admin(call.from_user.id, call.from_user.username): return
    bot.answer_callback_query(call.id)
    
    parts = call.data.split("_")
    action, uid = parts[1], parts[2]
    
    if uid not in user_data:
        return bot.edit_message_text("Пользователь не найден.", call.message.chat.id, call.message.message_id)

    if action == "cred10":
        user_data[uid]["credits"] += 10
        bot.answer_callback_query(call.id, "✅ Выдано 10 кредитов!")
    elif action == "cred50":
        user_data[uid]["credits"] += 50
        bot.answer_callback_query(call.id, "✅ Выдано 50 кредитов!")
    elif action == "sub":
        user_data[uid]["subscription_end"] = (datetime.datetime.now() + datetime.timedelta(days=30)).isoformat()
        bot.answer_callback_query(call.id, "♾️ Безлимит выдан на 30 дней!")
    elif action == "unsub":
        user_data[uid]["subscription_end"] = None
        bot.answer_callback_query(call.id, "❌ Безлимит снят.")
    elif action == "ban":
        user_data[uid]["banned"] = not user_data[uid].get("banned", False)
        bot.answer_callback_query(call.id, "Статус бана изменен.")
    elif action == "del":
        del user_data[uid]
        save_db()
        return bot.edit_message_text("🗑 Пользователь удален.", call.message.chat.id, call.message.message_id)
        
    save_db()
    # Обновляем карточку
    manage_user(call)

# --- РАССЫЛКА ---
def process_broadcast(message: Message):
    if not is_admin(message.from_user.id, message.from_user.username): return
    text = message.text
    if text == "/cancel": return
    count = 0
    for uid in user_data.keys():
        try:
            bot.send_message(uid, f"📢 Сообщение от админа:\n\n{text}")
            count += 1
            time.sleep(0.05)
        except: pass
    bot.reply_to(message, f"✅ Рассылка отправлена {count} пользователям.")

# --- ОСТАЛЬНОЕ (КНОПКИ, ГЕНЕРАЦИЯ И Т.Д.) ---
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
    bot.reply_to(message, "Выбери подходящий тариф:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "🆘 Помощь")
def help_menu(message: Message):
    if is_banned(message.from_user.id): return
    bot.reply_to(message, "Отправь фото и выбери стиль. Или нажми '🎨 Генерация фото', чтобы нарисовать по описанию.")

@bot.message_handler(commands=['buy'])
def buy(message: Message):
    if is_banned(message.from_user.id): return
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🎫 20 генераций (100 ⭐)", callback_data="buy_pack"))
    markup.add(InlineKeyboardButton("♾️ Безлимит на месяц (150 ⭐)", callback_data="buy_sub"))
    bot.reply_to(message, "Выбери подходящий тариф:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "🎨 Генерация фото")
def start_generation(message: Message):
    user_id = message.from_user.id
    if is_banned(user_id): return
    data = get_user_data(user_id)
    
    if not is_subscription_active(user_id) and data["credits"] <= 0:
        return bot.reply_to(message, "Генерации закончились. Купи: /buy")
        
    waiting_for_generation_text[user_id] = True
    bot.reply_to(message, "Напиши, что ты хочешь нарисовать (например: 'кот в космосе'):", reply_markup=ForceReply())

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

# --- ФОТО И ГЕНЕРАЦИЯ (СТАРЫЙ БЛОК) ---
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
    markup.add(InlineKeyboardButton("✨ Улучшить качество", callback_data="style_enhance"))
    markup.add(InlineKeyboardButton("🎨 Стиль Аниме", callback_data="style_anime"))
    bot.reply_to(message, "Выбери стиль:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('style_'))
def handle_style(call):
    user_id = call.from_user.id
    if is_banned(user_id): return
    data = get_user_data(user_id)
    if not is_subscription_active(user_id) and data.get("credits", 0) <= 0:
        return bot.answer_callback_query(call.id, "Нет генераций! Купи пакет: /buy")
    bot.answer_callback_query(call.id)
    if not photo_storage.get(user_id):
        return bot.send_message(call.message.chat.id, "Ошибка: фото не найдено. Отправь заново.")
    process_generation(call.message.chat.id, user_id, data, call.data, call.message.message_id)

def process_generation(chat_id, user_id, data, prompt, message_id, is_custom=False):
    encoded_prompt = urllib.parse.quote(prompt)
    image_url = f"https://gen.pollinations.ai/image/{encoded_prompt}?width=512&height=512&nologo=true"
    bot.edit_message_text("⏳ Нейросеть рисует...", chat_id, message_id)
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(image_url, headers=headers, timeout=60)
        if response.status_code == 200 and response.headers.get('content-type', '').startswith('image'):
            bot.send_photo(chat_id=chat_id, photo=response.content, caption="✅ Готово!")
            data["total_generated"] = data.get("total_generated", 0) + 1
            if not is_subscription_active(user_id):
                data["credits"] -= 1
                save_db()
                bot.send_message(user_id, f"Осталось: {data['credits']}", reply_markup=get_main_keyboard())
            else:
                save_db()
                bot.send_message(user_id, "Безлимит ♾️", reply_markup=get_main_keyboard())
        else:
            bot.edit_message_text("❌ Сервер перегружен. Попробуй позже.", chat_id, message_id)
    except Exception as e:
        bot.edit_message_text("❌ Ошибка при генерации. Попробуй позже.", chat_id, message_id)

# --- ЗАПУСК ---
if __name__ == '__main__':
    threading.Thread(target=run_bot).start()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
