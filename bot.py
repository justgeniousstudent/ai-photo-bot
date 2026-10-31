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
        bot.reply_to(
            message, 
            "👑 Привет, Админ! Жми /admin_menu, чтобы открыть панель управления.",
            reply_markup=get_main_keyboard()
        )
        return
    
    data = get_user_data(user_id)
    if data["credits"] == 1 and not is_subscription_active(user_id):
        bot.reply_to(message, "Привет! Отправь мне фото для обработки или нажми '🎨 Генерация фото', чтобы нарисовать картинку с нуля. У тебя есть 1 бесплатная попытка!", reply_markup=get_main_keyboard())
    else:
        bot.reply_to(message, "Привет! Отправь мне фото для обработки или нажми '🎨 Генерация фото'.", reply_markup=get_main_keyboard())

# --- АДМИНСКОЕ МЕНЮ ---
@bot.message_handler(commands=['admin_menu'])
def admin_menu(message: Message):
    if not is_admin(message.from_user.id, message.from_user.username): return
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📊 Статистика", callback_data="adm_stats"))
    markup.add(InlineKeyboardButton("📢 Рассылка", callback_data="adm_broadcast_help"))
    markup.add(InlineKeyboardButton("🎁 Выдать кредиты", callback_data="adm_give_help"))
    markup.add(InlineKeyboardButton("🚫 Забанить", callback_data="adm_ban_help"))
    markup.add(InlineKeyboardButton("🏆 Топ юзеров", callback_data="adm_top"))
    bot.reply_to(message, "🛠 Админ-панель:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('adm_'))
def handle_admin_buttons(call: CallbackQuery):
    if not is_admin(call.from_user.id, call.from_user.username): return
    bot.answer_callback_query(call.id)
    
    if call.data == "adm_stats":
        total_users = len(user_data)
        banned_users = sum(1 for d in user_data.values() if d.get("banned"))
        total_credits = sum(d.get("credits", 0) for d in user_data.values())
        bot.send_message(call.message.chat.id, f"📊 Статистика:\nВсего: {total_users}\nЗабанено: {banned_users}\nГенераций на балансах: {total_credits}")
    
    elif call.data == "adm_broadcast_help":
        bot.send_message(call.message.chat.id, "Для рассылки напиши:\n/broadcast Твой текст")
        
    elif call.data == "adm_give_help":
        bot.send_message(call.message.chat.id, "Чтобы выдать кредиты, напиши:\n/give @username 10")
        
    elif call.data == "adm_ban_help":
        bot.send_message(call.message.chat.id, "Чтобы забанить, напиши:\n/ban @username")
        
    elif call.data == "adm_top":
        sorted_users = sorted(user_data.items(), key=lambda item: item[1].get("total_generated", 0), reverse=True)[:5]
        text = "🏆 Топ-5 генераторов:\n"
        for i, (uid, udata) in enumerate(sorted_users, 1):
            uname = udata.get("username", uid)
            text += f"{i}. @{uname} — {udata.get('total_generated', 0)} картинок\n"
        bot.send_message(call.message.chat.id, text)

# --- ОБРАБОТКА КНОПОК КЛАВИАТУРЫ ---
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
    bot.reply_to(message, "Отправь фото и выбери стиль для обработки. Или нажми '🎨 Генерация фото', чтобы нарисовать картинку по описанию. Оплатить генерации можно через 'Купить'.")

# --- ГЕНЕРАЦИЯ ФОТО ---
@bot.message_handler(func=lambda message: message.text == "🎨 Генерация фото")
def start_generation(message: Message):
    user_id = message.from_user.id
    if is_banned(user_id): return
    data = get_user_data(user_id)
    
    if not is_subscription_active(user_id) and data["credits"] <= 0:
        return bot.reply_to(message, "Генерации закончились. Купи: /buy")
        
    waiting_for_generation_text[user_id] = True
    bot.reply_to(message, "Напиши, что ты хочешь нарисовать (например: 'кот в космосе в стиле киберпанк'):", reply_markup=ForceReply())

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

@bot.message_handler(commands=['buy'])
def buy(message: Message):
    if is_banned(message.from_user.id): return
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🎫 20 генераций (100 ⭐)", callback_data="buy_pack"))
    markup.add(InlineKeyboardButton("♾️ Безлимит на месяц (150 ⭐)", callback_data="buy_sub"))
    bot.reply_to(message, "Выбери подходящий тариф:", reply_markup=markup)

# --- СТАРЫЕ АДМИНСКИЕ КОМАНДЫ ---
@bot.message_handler(commands=['stats'])
def stats(message: Message):
    if not is_admin(message.from_user.id, message.from_user.username): return
    total_users = len(user_data)
    banned_users = sum(1 for d in user_data.values() if d.get("banned"))
    total_credits = sum(d.get("credits", 0) for d in user_data.values())
    bot.reply_to(message, f"📊 Статистика:\nВсего: {total_users}\nЗабанено: {banned_users}\nГенераций на балансах: {total_credits}")

@bot.message_handler(commands=['give'])
def give_credits(message: Message):
    if not is_admin(message.from_user.id, message.from_user.username): return
    try:
        parts = message.text.split()
        if len(parts) != 3: return bot.reply_to(message, "Использование: /give <ID или @username> <кол-во>")
        target, amount = parts[1], int(parts[2])
        target_id = find_user_id(target)
        if not target_id: return bot.reply_to(message, "Пользователь не найден.")
        
        user_data[target_id]["credits"] += amount
        save_db()
        bot.reply_to(message, f"✅ {target} выдано {amount} генераций.")
        try: bot.send_message(target_id, f"🎁 Тебе начислено {amount} генераций!")
        except: pass
    except Exception as e: bot.reply_to(message, f"Ошибка: {e}")

@bot.message_handler(commands=['reset_user'])
def reset_user(message: Message):
    if not is_admin(message.from_user.id, message.from_user.username): return
    parts = message.text.split()
    if len(parts) != 2: return bot.reply_to(message, "Использование: /reset_user <ID или @username>")
    target_id = find_user_id(parts[1])
    if not target_id: return bot.reply_to(message, "Пользователь не найден.")
    
    if target_id in user_data:
        del user_data[target_id]
        save_db()
        bot.reply_to(message, f"🗑 Пользователь {parts[1]} удален из базы.")

@bot.message_handler(commands=['ban'])
def ban_user(message: Message):
    if not is_admin(message.from_user.id, message.from_user.username): return
    parts = message.text.split()
    if len(parts) != 2: return bot.reply_to(message, "Использование: /ban <ID или @username>")
    target_id = find_user_id(parts[1])
    if not target_id: return bot.reply_to(message, "Пользователь не найден.")
    user_data[target_id]["banned"] = True
    save_db()
    bot.reply_to(message, f"🚫 Пользователь {parts[1]} забанен.")

@bot.message_handler(commands=['unban'])
def unban_user(message: Message):
    if not is_admin(message.from_user.id, message.from_user.username): return
    parts = message.text.split()
    if len(parts) != 2: return bot.reply_to(message, "Использование: /unban <ID или @username>")
    target_id = find_user_id(parts[1])
    if not target_id: return bot.reply_to(message, "Пользователь не найден.")
    user_data[target_id]["banned"] = False
    save_db()
    bot.reply_to(message, f"✅ Пользователь {parts[1]} разбанен.")

@bot.message_handler(commands=['broadcast'])
def broadcast(message: Message):
    if not is_admin(message.from_user.id, message.from_user.username): return
    text = message.text.replace("/broadcast ", "")
    if not text: return bot.reply_to(message, "Введите текст для рассылки.")
    count = 0
    for uid in user_data.keys():
        try:
            bot.send_message(uid, f"📢 Сообщение от админа:\n\n{text}")
            count += 1
            time.sleep(0.05)
        except: pass
    bot.reply_to(message, f"✅ Рассылка отправлена {count} пользователям.")

def find_user_id(target):
    if target.isdigit(): return target
    elif target.startswith('@'):
        username = target[1:].lower()
        for uid, udata in user_data.items():
            if udata.get("username") and udata.get("username").lower() == username:
                return uid
    return None

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

# --- ОБРАБОТКА ФОТО ---
@bot.message_handler(content_types=['photo'])
def handle_photo(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    
    if is_banned(user_id): return
    
    data = get_user_data(user_id, username)
    
    if not is_subscription_active(user_id) and data["credits"] <= 0:
        return bot.reply_to(message, "Генерации закончились. Купи: /buy", reply_markup=get_main_keyboard())

    photo_storage[user_id] = message.photo[-1].file_id 
    waiting_for_prompt.pop(user_id, None)

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✨ Улучшить качество", callback_data="style_enhance"))
    markup.add(InlineKeyboardButton("🎨 Стиль Аниме", callback_data="style_anime"))
    markup.add(InlineKeyboardButton("✍️ Свой запрос", callback_data="style_custom"))
    bot.reply_to(message, "Выбери стиль или напиши свой запрос:", reply_markup=markup)

# --- ОБРАБОТКА КНОПОК СТИЛЯ ---
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

    if call.data == "style_custom":
        waiting_for_prompt[user_id] = True
        bot.send_message(call.message.chat.id, "Напиши, что ты хочешь сделать с фото:", reply_markup=ForceReply())
        return

    process_generation(call.message.chat.id, user_id, data, call.data, call.message.message_id)

@bot.message_handler(func=lambda message: message.from_user.id in waiting_for_prompt)
def handle_custom_text(message: Message):
    user_id = message.from_user.id
    if is_banned(user_id): return
    data = get_user_data(user_id)
    user_text = message.text
    waiting_for_prompt.pop(user_id, None)
    
    if not is_subscription_active(user_id) and data.get("credits", 0) <= 0:
        return bot.reply_to(message, "Генерации закончились. Купи: /buy")
    if not photo_storage.get(user_id):
        return bot.reply_to(message, "Фото не найдено. Отправь заново.")

    msg = bot.reply_to(message, "🧠 ИИ обрабатывает твой запрос...")
    smart_prompt = get_smart_prompt(user_text)
    process_generation(message.chat.id, user_id, data, smart_prompt, msg.message_id, is_custom=True)

# --- ФУНКЦИЯ ГЕНЕРАЦИИ (НОВЫЙ ШЛЮЗ POLLINATIONS) ---
def process_generation(chat_id, user_id, data, prompt, message_id, is_custom=False):
    encoded_prompt = urllib.parse.quote(prompt)
    image_url = f"https://gen.pollinations.ai/image/{encoded_prompt}?width=512&height=512&nologo=true"
    
    bot.edit_message_text("⏳ Нейросеть рисует... (попытка 1)", chat_id, message_id)
    
    for attempt in range(3):
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(image_url, headers=headers, timeout=60)
            
            if response.status_code == 200 and response.headers.get('content-type', '').startswith('image'):
                bot.send_photo(
                    chat_id=chat_id,
                    photo=response.content,
                    caption=f"✅ Готово! (Запрос: {prompt[:50]}...)"
                )
                
                data["total_generated"] = data.get("total_generated", 0) + 1
                
                if not is_subscription_active(user_id):
                    data["credits"] -= 1
                    save_db()
                    bot.send_message(user_id, f"Осталось генераций: {data['credits']}", reply_markup=get_main_keyboard())
                else:
                    save_db()
                    bot.send_message(user_id, "У тебя активен безлимит ♾️", reply_markup=get_main_keyboard())
                return 
            
            else:
                if attempt < 2:
                    bot.edit_message_text(f"⏳ Сервер перегружен. Пробую еще раз... (попытка {attempt+2})", chat_id, message_id)
                    time.sleep(5)
                else:
                    bot.edit_message_text("❌ Нейросеть перегружена. Попробуй позже.", chat_id, message_id)
                    
        except Exception as e:
            print(f"Ошибка генерации (попытка {attempt+1}): {e}")
            if attempt < 2:
                time.sleep(5)
            else:
                bot.send_message(chat_id, "Произошла ошибка при генерации. Попробуй позже.")

# --- ЗАПУСК ---
if __name__ == '__main__':
    threading.Thread(target=run_bot).start()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
