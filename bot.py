import os
import threading
import time
import datetime
from flask import Flask
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from neonpay import create_neonpay, PaymentStage, PaymentStatus

BOT_TOKEN = "9060154141:AAGDGDAwAs1J-HdUyJKyhxfFUfRidrTOjek"
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

neonpay = create_neonpay(bot)

stage_pack = PaymentStage(
    title="Пакет 20 генераций",
    description="Разовая покупка 20 обработок фото.",
    price=100,
    photo_url="https://example.com/pack.png" 
)
neonpay.create_payment_stage("pack_20", stage_pack)

stage_sub = PaymentStage(
    title="Безлимит на 1 месяц",
    description="Неограниченное количество обработок фото в течение 30 дней.",
    price=150,
    photo_url="https://example.com/sub.png"
)
neonpay.create_payment_stage("sub_month", stage_sub)

user_data = {}

def get_user_data(user_id):
    """Возвращает данные пользователя. Если его нет — создает с 1 бесплатной попыткой."""
    if user_id not in user_data:
        user_data[user_id] = {
            "credits": 1, 
            "subscription_end": None 
        }
    return user_data[user_id]

def is_subscription_active(user_id):
    """Проверяет, активна ли подписка."""
    data = user_data.get(user_id, {})
    sub_end = data.get("subscription_end")
    if sub_end and sub_end > datetime.datetime.now():
        return True
    return False

@app.route('/')
def health():
    return "Bot is running"

def run_bot():
    print("Бот запущен...")
    bot.infinity_polling()

@bot.message_handler(commands=['start'])
def start(message: Message):
    user_id = message.from_user.id
    data = get_user_data(user_id)
    
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


@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_'))
def handle_buy_button(call):
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id
    
    if call.data == "buy_pack":
        neonpay.send_payment(user_id=user_id, stage_id="pack_20")
    elif call.data == "buy_sub":
        neonpay.send_payment(user_id=user_id, stage_id="sub_month")

@neonpay.on_payment
def handle_payment(result):
    if result.status == PaymentStatus.COMPLETED:
        user_id = result.user_id
        data = get_user_data(user_id)
        
        if result.stage_id == "pack_20":
            data["credits"] += 20
            bot.send_message(user_id, "Оплата прошла! Тебе начислено 20 генераций. Отправляй фото!")
        elif result.stage_id == "sub_month":
         
            data["subscription_end"] = datetime.datetime.now() + datetime.timedelta(days=30)
            bot.send_message(user_id, "Оплата прошла! У тебя активирован безлимит на 30 дней. Отправляй фото!")


@bot.message_handler(content_types=['photo'])
def handle_photo(message: Message):
    user_id = message.from_user.id
    get_user_data(user_id) 
    if not is_subscription_active(user_id) and user_data[user_id]["credits"] <= 0:
        bot.reply_to(message, "У тебя закончились генерации или подписка. Купи пакет: /buy")
        return
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✨ Улучшить качество", callback_data="style_enhance"))
    markup.add(InlineKeyboardButton("🎨 Стиль Аниме", callback_data="style_anime"))
    bot.reply_to(message, "Выбери стиль обработки:", reply_markup=markup)
@bot.callback_query_handler(func=lambda call: call.data.startswith('style_'))
def handle_style(call):
    user_id = call.from_user.id
    if not is_subscription_active(user_id) and user_data[user_id]["credits"] <= 0:
        bot.answer_callback_query(call.id, "Нет генераций! Купи пакет: /buy")
        return
    bot.answer_callback_query(call.id)
    bot.edit_message_text("⏳ Нейросеть колдует над твоим фото...", call.message.chat.id, call.message.message_id)
    time.sleep(3) 
    bot.send_photo(
        chat_id=call.message.chat.id,
        photo=call.message.photo[-1].file_id, 
        caption=f"✅ Готово! (Стиль: {call.data})"
    )
    if not is_subscription_active(user_id):
        user_data[user_id]["credits"] -= 1
        bot.send_message(user_id, f"Осталось генераций: {user_data[user_id]['credits']}")
    else:
        bot.send_message(user_id, "У тебя активен безлимит по подписке ♾️")
if __name__ == '__main__':
    threading.Thread(target=run_bot).start()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
