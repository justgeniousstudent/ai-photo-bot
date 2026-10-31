import os
import json
import threading
import datetime
import urllib.parse
import requests
from flask import Flask
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, LabeledPrice

# --- НАСТРОЙКИ ---
BOT_TOKEN = "9060154141:AAF_Wa3bzK5EVFJxkT3LA_OU2cxsm5uu_YY"
ADMIN_ID = 8068216414          # Ваш ID
ADMIN_USERNAME = "sladkooe_vino" # Ваш юзернейм (без @)

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# --- БАЗА ДАННЫХ ---
DB_FILE = "users.json"
user_data = {}
photo_storage = {}

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
        user_data[user_id_str] = {"credits": 1, "subscription_end": None, "username": username}
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

# Проверка на админа: по ID или по юзернейму
def is_admin(user_id, username=None):
    if user_id == ADMIN_ID:
        return True
    if username and username.lower() == ADMIN_USERNAME.lower():
        return True
    return False

@app.route('/')
def health():
    return "Bot is running"

def run_bot():
    print("Бот запущен...")
    bot.infinity_polling()

# --- КОМАНДЫ ---
@bot.message_handler(commands=['start'])
def start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    
    # Принудительно создаем запись при старте
    data = get_user_data(user_id, username)
    save_db()
    
    if is_admin(user_id, username):
        bot.reply_to(message, "👑 Привет, Админ! Тебе доступны команды:\n/stats - статистика\n/give <ID или @username> <кол-во> - выдать кредиты")
        return # Админу не показываем сообщение о бесплатной попытке
    
    if data["credits"] == 1 and not is_subscription_active(user_id):
        bot.reply_to(message, "Привет! Отправь мне фото, и я сделаю из него конфетку. У тебя есть 1 бесплатная попытка!")
    else:
        bot.reply_to(message, "Привет! Отправь мне фото для обработки.")

@bot.message_handler(commands=['buy'])
def buy(message: Message):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🎫 20 генераций (100 ⭐)", callback_data="buy_pack"))
    markup.add(InlineKeyboardButton("♾️ Безлимит на месяц (150 ⭐)", callback_data="buy_sub"))
    bot.reply_to(message, "Выбери подходящий тариф:", reply_markup=markup)

# --- АДМИНСКИЕ КОМАНДЫ ---
@bot.message_handler(commands=['stats'])
def stats(message: Message):
    if not is_admin(message.from_user.id, message.from_user.username):
        return
    total_users = len(user_data)
    total_credits = sum(d.get("credits", 0) for d in user_data.values())
    bot.reply_to(message, f"📊 Статистика:\nПользователей: {total_users}\nВсего генераций на балансах: {total_credits}")

@bot.message_handler(commands=['give'])
def give_credits(message: Message):
    if not is_admin(message.from_user.id, message.from_user.username):
        return
    try:
        parts = message.text.split()
        if len(parts) != 3:
            bot.reply_to(message, "Использование: /give <ID или @username> <кол-во>")
            return
        
        target = parts[1]
        amount = int(parts[2])
        
        target_id = None
        
        if target.isdigit():
            target_id = target
        elif target.startswith('@'):
            username = target[1:].lower()
            # Ищем пользователя по юзернейму в базе (без учета регистра)
            for uid, udata in user_data.items():
                if udata.get("username") and udata.get("username").lower() == username:
                    target_id = uid
                    break
            if not target_id:
                bot.reply_to(message, f"Пользователь {target} не найден в базе (он еще не писал боту).")
                return
        else:
            bot.reply_to(message, "Неверный формат. Введите ID или @username.")
            return

        if target_id not in user_data:
            user_data[target_id] = {"credits": 0, "subscription_end": None, "username": None}
            
        user_data[target_id]["credits"] += amount
        save_db()
        
        bot.reply_to(message, f"✅ Пользователю {target} выдано {amount} генераций.")
        try:
            bot.send_message(target_id, f"🎁 Тебе начислено {amount} генераций от администратора!")
        except:
            pass
    except Exception as e:
        bot.reply_to(message, f"Ошибка: {e}")

# --- ОПЛАТА ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_'))
def handle_buy_button(call):
    bot.answer_callback_query(call.id)
    if call.data == "buy_pack":
        bot.send_invoice(chat_id=call.message.chat.id, title="Пакет 20 генераций", description="Разовая покупка 20 обработок фото.", invoice_payload="pack_20", provider_token="", currency="XTR", prices=[LabeledPrice(label="20 генераций", amount=100)])
    elif call.data == "buy_sub":
        bot.send_invoice(chat_id=call.message.chat.id, title="Безлимит на 1 месяц", description="Неограниченное количество обработок фото в течение 30 дней.", invoice_payload="sub_month", provider_token="", currency="XTR", prices=[LabeledPrice(label="Безлимит на месяц", amount=150)])

@bot.pre_checkout_query_handler(func=lambda query: True)
def checkout(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def got_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    user_id = message.from_user.id
    data = get_user_data(user_id)
    if payload == "pack_20":
        data["credits"] += 20
        save_db()
        bot.send_message(user_id, "✅ Оплата прошла! Тебе начислено 20 генераций. Отправляй фото!")
    elif payload == "sub_month":
        data["subscription_end"] = (datetime.datetime.now() + datetime.timedelta(days=30)).isoformat()
        save_db()
        bot.send_message(user_id, "✅ Оплата прошла! У тебя активирован безлимит на 30 дней. Отправляй фото!")

# --- ОБРАБОТКА ФОТО ---
@bot.message_handler(content_types=['photo'])
def handle_photo(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    data = get_user_data(user_id, username)
    
    if not is_subscription_active(user_id) and data["credits"] <= 0:
        bot.reply_to(message, "У тебя закончились генерации или подписка. Купи пакет: /buy")
        return

    photo_storage[user_id] = message.photo[-1].file_id 

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✨ Улучшить качество", callback_data="style_enhance"))
    markup.add(InlineKeyboardButton("🎨 Стиль Аниме", callback_data="style_anime"))
    bot.reply_to(message, "Выбери стиль обработки:", reply_markup=markup)

# --- ОБРАБОТКА КНОПОК ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('style_'))
def handle_style(call):
    user_id = call.from_user.id
    data = get_user_data(user_id)
    
    if not is_subscription_active(user_id) and data.get("credits", 0) <= 0:
        bot.answer_callback_query(call.id, "Нет генераций! Купи пакет: /buy")
        return

    bot.answer_callback_query(call.id)
    
    if not photo_storage.get(user_id):
        bot.send_message(call.message.chat.id, "Ошибка: фото не найдено. Отправь фото заново.")
        return

    bot.edit_message_text("⏳ Нейросеть колдует...", call.message.chat.id, call.message.message_id)

    try:
        prompt = "anime style portrait" if call.data == "style_anime" else "high quality, detailed, masterpiece"
        encoded_prompt = urllib.parse.quote(prompt)
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=512&nologo=true"
        
        response = requests.get(image_url, timeout=30)
        
        if response.status_code == 200:
            bot.send_photo(
                chat_id=call.message.chat.id,
                photo=response.content,
                caption=f"✅ Сгенерировано! (Стиль: {call.data})"
            )
            
            if not is_subscription_active(user_id):
                data["credits"] -= 1
                save_db()
                bot.send_message(user_id, f"Осталось генераций: {data['credits']}")
            else:
                bot.send_message(user_id, "У тебя активен безлимит ♾️")
        else:
            bot.send_message(call.message.chat.id, "Ошибка: нейросеть не смогла сгенерировать фото.")
            
    except Exception as e:
        print(f"Ошибка генерации: {e}")
        bot.send_message(call.message.chat.id, "Произошла ошибка при генерации. Попробуй позже.")

# --- ЗАПУСК ---
if __name__ == '__main__':
    threading.Thread(target=run_bot).start()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
