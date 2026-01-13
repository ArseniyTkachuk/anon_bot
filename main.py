import telebot
from telebot import types
import uuid
from pymongo import MongoClient, ASCENDING
from datetime import datetime

# =======================
# Налаштування
# =======================
TOKEN = "7771111625:AAGYfvnvlc3blLW445bG9_PBmnYzb7aeiLU"
bot = telebot.TeleBot(TOKEN)

VIP_USER_ID = 6974025895  # твій Telegram ID

# Підключення до MongoDB Atlas
MONGO_URI = "mongodb+srv://admin:wwwwww@cluster0.wxjo6hs.mongodb.net/anon_bot?retryWrites=true&w=majority"
# MONGO_URI = "mongodb://localhost:27017/"
client = MongoClient(MONGO_URI)
print(client.list_database_names())
db = client["anon_bot"]
messages_col = db["messages"]

# TTL індекс (видалення повідомлень через 7 днів)
del_time = 60*60*24*7
messages_col.create_index([("created_at", ASCENDING)], expireAfterSeconds=del_time)

# =======================
# Клавіатура
# =======================
def main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row("Моє персональне посилання", "Допомога")
    return keyboard

# =======================
# Стани
# =======================
user_reply_state = {}   # key: user_id, value: message_id, на яке відповідають
user_target_state = {}  # key: user_id, value: receiver_id для нового повідомлення через посилання

# =======================
# /start
# =======================
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    args = message.text.split()

    if len(args) > 1 and args[1].startswith("uid_"):
        receiver_id = int(args[1].split("_")[1])
        user_target_state[user_id] = receiver_id
        bot.send_message(user_id, "Введи анонімне повідомлення:", reply_markup=main_keyboard())
    else:
        bot.send_message(user_id,
                         "Привіт! Я анонімний бот. Скористайся кнопками нижче.",
                         reply_markup=main_keyboard())

# =======================
# Обробка текстових повідомлень
# =======================
@bot.message_handler(func=lambda message: True)
def handle_text(message):
    user_id = message.chat.id
    text = message.text

    # Меню
    if text == "Моє персональне посилання":
        link = f"https://t.me/{bot.get_me().username}?start=uid_{user_id}"
        bot.send_message(user_id, f"Твоє персональне посилання:\n{link}")
        return
    elif text == "Допомога":
        bot.send_message(user_id,
                         "1️⃣ Натисни 'Моє персональне посилання', щоб отримати своє посилання\n"
                         "2️⃣ Поділись посиланням для анонімних повідомлень\n",
                         reply_markup=main_keyboard())
        return

    # =======================
    # Відповідь на повідомлення
    # =======================
    if user_id in user_reply_state:
        msg_id = user_reply_state.pop(user_id)
        original = messages_col.find_one({"_id": msg_id})
        if not original:
            bot.send_message(user_id, "Повідомлення більше не доступне.", reply_markup=main_keyboard())
            return

        reply_text = text
        receiver_id = original["sender_id"]
        sender_info = f"\n\nВід @{message.chat.username}" if original["receiver_id"] == VIP_USER_ID else ""
        bot.send_message(receiver_id, f"Відповідь:\n\n{reply_text}{sender_info}", reply_markup=main_keyboard())

        # Зберігаємо відповідь
        new_msg = {
            "_id": str(uuid.uuid4()),
            "sender_id": receiver_id,
            "receiver_id": user_id,
            "text": reply_text,
            "parent_id": msg_id,
            "created_at": datetime.utcnow()
        }
        messages_col.insert_one(new_msg)
        bot.send_message(user_id, "Відповідь надіслано!", reply_markup=main_keyboard())
        return

    # =======================
    # Нове анонімне повідомлення через посилання
    # =======================
    if user_id not in user_target_state:
        bot.send_message(user_id,
                         "Щоб надіслати повідомлення, скористайся персональним посиланням іншого користувача.",
                         reply_markup=main_keyboard())
        return

    receiver_id = user_target_state.pop(user_id)

    # Зберігаємо повідомлення
    msg_id = str(uuid.uuid4())
    messages_col.insert_one({
        "_id": msg_id,
        "sender_id": user_id,
        "receiver_id": receiver_id,
        "text": text,
        "parent_id": None,
        "created_at": datetime.utcnow()
    })

    # Кнопка відповісти
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Відповісти", callback_data=f"reply_{msg_id}"))

    sender_info = f"\n\nВід @{message.chat.username}" if receiver_id == VIP_USER_ID else ""
    bot.send_message(receiver_id, f"Нове повідомлення:\n\n{text}{sender_info}", reply_markup=markup)
    bot.send_message(user_id, "Повідомлення надіслано!", reply_markup=main_keyboard())

# =======================
# Callback кнопка "Відповісти"
# =======================
@bot.callback_query_handler(func=lambda call: call.data.startswith("reply_"))
def handle_reply(call):
    msg_id = call.data.split("_")[1]
    user_reply_state[call.from_user.id] = msg_id
    bot.send_message(call.from_user.id, "Введи відповідь на повідомлення:")

# =======================
# Запуск бота
# =======================
bot.infinity_polling()
