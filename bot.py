import telebot
from telebot import types
import json
import os
from datetime import datetime

TOKEN = "8615174100:AAEQFknopQCuWXr8Ktdp5JSgeWpq4hVZLWE"
bot = telebot.TeleBot(TOKEN)

ADMIN_IDS = set()
USER_MESSAGES = {}
CURRENT_CHAT = {}

# Меняем на рабочий стол
DATA_FILE = os.path.join(os.path.expanduser("~"), "Desktop", "bot_data.json")

def load_data():
    global ADMIN_IDS, USER_MESSAGES
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                ADMIN_IDS = set(data.get('admin_ids', []))
                USER_MESSAGES = data.get('user_messages', {})
    except:
        pass

def save_data():
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'admin_ids': list(ADMIN_IDS),
                'user_messages': USER_MESSAGES
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка сохранения: {e}")

load_data()

def get_admin_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("Пользователи"))
    return markup

def get_user_display(user_id):
    if user_id in USER_MESSAGES:
        user_info = USER_MESSAGES[user_id]
        username = user_info.get('username', '')
        first_name = user_info.get('first_name', '')
        
        if username and username != 'Без имени':
            return f"@{username}"
        elif first_name and first_name.strip():
            return first_name
        else:
            return f"ID: {user_id}"
    return f"ID: {user_id}"

def get_users_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    if not USER_MESSAGES:
        markup.add(types.InlineKeyboardButton("Нет пользователей", callback_data="none"))
        return markup
    
    for user_id in USER_MESSAGES:
        display_name = get_user_display(user_id)
        msg_count = len(USER_MESSAGES[user_id].get('messages', []))
        
        markup.add(
            types.InlineKeyboardButton(
                f"{display_name} ({msg_count} сообщ.)",
                callback_data=f"user_{user_id}"
            )
        )
    
    return markup

def get_chat_menu(user_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("Удалить чат", callback_data=f"delete_{user_id}"),
        types.InlineKeyboardButton("Вернуться в меню", callback_data="back_to_menu")
    )
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    user_id = str(message.from_user.id)
    
    if user_id in ADMIN_IDS:
        bot.send_message(
            message.chat.id,
            "Админ-панель",
            reply_markup=get_admin_menu()
        )
    else:
        if user_id not in USER_MESSAGES:
            USER_MESSAGES[user_id] = {
                'username': message.from_user.username or 'Без имени',
                'first_name': message.from_user.first_name or '',
                'messages': []
            }
            save_data()

@bot.message_handler(func=lambda message: message.text == "Пользователи")
def show_users(message):
    if str(message.from_user.id) not in ADMIN_IDS:
        return
    
    bot.send_message(
        message.chat.id,
        "Список пользователей:",
        reply_markup=get_users_keyboard()
    )

@bot.message_handler(content_types=['text'])
def handle_messages(message):
    user_id = str(message.from_user.id)
    text = message.text
    
    if text == "Пользователи":
        return
    
    if text == "admin123" and user_id not in ADMIN_IDS:
        ADMIN_IDS.add(user_id)
        save_data()
        bot.send_message(
            message.chat.id,
            "Вы стали администратором!",
            reply_markup=get_admin_menu()
        )
        return
    
    if user_id in ADMIN_IDS:
        if user_id in CURRENT_CHAT:
            target_user_id = CURRENT_CHAT[user_id]
            try:
                bot.send_message(
                    int(target_user_id),
                    text
                )
                if target_user_id in USER_MESSAGES:
                    USER_MESSAGES[target_user_id]['messages'].append({
                        'text': text,
                        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'from_user': False
                    })
                    save_data()
                
                bot.send_message(
                    message.chat.id,
                    f"Отправлено: {get_user_display(target_user_id)}",
                    reply_markup=get_chat_menu(target_user_id)
                )
            except Exception as e:
                bot.send_message(message.chat.id, f"Ошибка: {str(e)}")
            return
        else:
            bot.send_message(message.chat.id, "Сначала выберите пользователя в 'Пользователи'")
            return
    
    if user_id not in USER_MESSAGES:
        USER_MESSAGES[user_id] = {
            'username': message.from_user.username or 'Без имени',
            'first_name': message.from_user.first_name or '',
            'messages': []
        }
    
    USER_MESSAGES[user_id]['messages'].append({
        'text': text,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'from_user': True
    })
    save_data()
    
    username = message.from_user.username
    if username and username != 'Без имени':
        user_display = f"@{username}"
    else:
        user_display = message.from_user.first_name or f"ID: {user_id}"
    
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(
                int(admin_id),
                f"Новое сообщение от {user_display}:\n\n{text}"
            )
        except:
            pass

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    admin_id = str(call.from_user.id)
    
    if call.data == "back_to_menu":
        if admin_id in CURRENT_CHAT:
            del CURRENT_CHAT[admin_id]
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(
            call.message.chat.id,
            "Админ-панель",
            reply_markup=get_admin_menu()
        )
        return
    
    if call.data.startswith("delete_"):
        target_user_id = call.data.split("_", 1)[1]
        if target_user_id in USER_MESSAGES:
            del USER_MESSAGES[target_user_id]
            save_data()
        if admin_id in CURRENT_CHAT:
            del CURRENT_CHAT[admin_id]
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(
            call.message.chat.id,
            "Чат удален",
            reply_markup=get_admin_menu()
        )
        return
    
    if call.data.startswith("user_"):
        target_user_id = call.data.split("_", 1)[1]
        
        if target_user_id in USER_MESSAGES:
            user_info = USER_MESSAGES[target_user_id]
            CURRENT_CHAT[admin_id] = target_user_id
            display_name = get_user_display(target_user_id)
            
            messages = user_info.get('messages', [])
            if messages:
                history = f"История {display_name}:\n\n"
                for msg in messages[-10:]:
                    direction = "Пользователь" if msg['from_user'] else "Админ"
                    history += f"[{msg['timestamp']}] {direction}: {msg['text']}\n"
            else:
                history = "Нет сообщений"
            
            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=f"{history}\nВведите ответ:",
                    reply_markup=get_chat_menu(target_user_id)
                )
            except:
                pass
    
    elif call.data == "none":
        bot.answer_callback_query(call.id, "Нет пользователей")

from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot running"

def run_flask():
    app.run(host='0.0.0.0', port=10000)

if __name__ == "__main__":
    print("Bot started!")
    bot.remove_webhook()
    Thread(target=run_flask).start()
    bot.infinity_polling()
