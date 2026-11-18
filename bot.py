"""Feedback Relay Bot: users message the bot, admins reply from inside the bot chat.

Configured via environment variables / a .env file (see .env.example and README).
"""
import hmac
import json
import logging
import os
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path

import telebot
from telebot import types

try:  # python-dotenv is optional: you can also set environment variables yourself
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()   # empty = password login disabled
ENV_ADMINS = {x.strip() for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()}
DATA_FILE = Path(os.getenv("DATA_FILE", "bot_data.json"))
WELCOME_TEXT = os.getenv("WELCOME_TEXT",
                         "Hello! Send your message and an administrator will reply.")
ENABLE_WEB = os.getenv("ENABLE_WEB", "0") == "1"           # tiny web server for hosts like Render
PORT = int(os.getenv("PORT", "10000"))

MAX_HISTORY = 200        # messages kept per user
HISTORY_SHOWN = 10       # messages shown to the admin
MAX_USER_BUTTONS = 90    # Telegram limit: 100 buttons per keyboard

if not TOKEN:
    sys.exit("BOT_TOKEN is not set. Copy .env.example to .env and paste the token from @BotFather.")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")

bot = telebot.TeleBot(TOKEN)

CONTENT_TYPES = ["text", "photo", "video", "document", "voice", "audio",
                 "sticker", "video_note", "animation"]
BTN_USERS = "Users"

# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------
lock = threading.RLock()
ADMIN_IDS = set(ENV_ADMINS)
USER_MESSAGES = {}   # user_id -> {username, first_name, messages: [...]}
CURRENT_CHAT = {}    # admin_id -> user_id


def load_data():
    global ADMIN_IDS, USER_MESSAGES
    if not DATA_FILE.exists():
        return
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        with lock:
            ADMIN_IDS = set(data.get("admin_ids", [])) | ENV_ADMINS
            USER_MESSAGES = data.get("user_messages", {})
    except (OSError, ValueError) as e:
        log.error("Could not read %s: %s", DATA_FILE, e)


def save_data():
    """Atomic write: write to a temp file first, then replace."""
    with lock:
        payload = {"admin_ids": sorted(ADMIN_IDS - ENV_ADMINS), "user_messages": USER_MESSAGES}
        try:
            DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=DATA_FILE.parent or ".", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp, DATA_FILE)
        except OSError as e:
            log.error("Save error: %s", e)


load_data()


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def is_admin(uid):
    return str(uid) in ADMIN_IDS


def ensure_user(tg_user):
    """Create the user record and refresh the name."""
    uid = str(tg_user.id)
    with lock:
        info = USER_MESSAGES.setdefault(uid, {"username": "", "first_name": "", "messages": []})
        info["username"] = tg_user.username or ""
        info["first_name"] = tg_user.first_name or ""
    return uid


def display_name(uid):
    info = USER_MESSAGES.get(uid, {})
    if info.get("username"):
        return f"@{info['username']}"
    if info.get("first_name", "").strip():
        return info["first_name"]
    return f"ID: {uid}"


def describe(message):
    """Text representation of a message for the history."""
    if message.content_type == "text":
        return message.text
    caption = f" {message.caption}" if message.caption else ""
    return f"[{message.content_type}]{caption}"


def add_history(uid, text, from_user):
    with lock:
        msgs = USER_MESSAGES.setdefault(uid, {"username": "", "first_name": "", "messages": []})["messages"]
        msgs.append({"text": text, "timestamp": now(), "from_user": from_user})
        del msgs[:-MAX_HISTORY]
    save_data()


def last_activity(uid):
    msgs = USER_MESSAGES[uid].get("messages", [])
    return msgs[-1]["timestamp"] if msgs else ""


def clip(text, n):
    return text if len(text) <= n else text[:n] + "…"


# --------------------------------------------------------------------------
# Keyboards
# --------------------------------------------------------------------------
def admin_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton(BTN_USERS))
    return markup


def users_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    with lock:
        if not USER_MESSAGES:
            markup.add(types.InlineKeyboardButton("No users yet", callback_data="none"))
            return markup
        uids = sorted(USER_MESSAGES, key=last_activity, reverse=True)[:MAX_USER_BUTTONS]
        for uid in uids:
            count = len(USER_MESSAGES[uid].get("messages", []))
            markup.add(types.InlineKeyboardButton(
                f"{display_name(uid)} ({count} msg)", callback_data=f"user_{uid}"))
    return markup


def chat_menu(uid):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("Delete chat", callback_data=f"delete_{uid}"),
        types.InlineKeyboardButton("Back to menu", callback_data="back_to_menu"),
    )
    return markup


def confirm_menu(uid):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("Yes, delete", callback_data=f"confirm_{uid}"),
        types.InlineKeyboardButton("Cancel", callback_data=f"user_{uid}"),
    )
    return markup


def history_text(uid):
    msgs = USER_MESSAGES.get(uid, {}).get("messages", [])
    if not msgs:
        return f"Chat with {display_name(uid)}\n\nNo messages yet."
    lines = [f"History of {display_name(uid)}:\n"]
    for m in msgs[-HISTORY_SHOWN:]:
        who = "User" if m["from_user"] else "Admin"
        lines.append(f"[{m['timestamp']}] {who}: {clip(m['text'], 300)}")
    return clip("\n".join(lines), 3500)


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------
@bot.message_handler(commands=["start"], chat_types=["private"])
def cmd_start(message):
    uid = str(message.from_user.id)
    if is_admin(uid):
        bot.send_message(message.chat.id, "Admin panel", reply_markup=admin_menu())
        return
    ensure_user(message.from_user)
    save_data()
    bot.send_message(message.chat.id, WELCOME_TEXT)


@bot.message_handler(commands=["exit"], chat_types=["private"])
def cmd_exit(message):
    uid = str(message.from_user.id)
    if is_admin(uid):
        CURRENT_CHAT.pop(uid, None)
        bot.send_message(message.chat.id, "You left the chat.", reply_markup=admin_menu())


@bot.message_handler(commands=["users"], chat_types=["private"])
@bot.message_handler(func=lambda m: m.text == BTN_USERS, content_types=["text"], chat_types=["private"])
def show_users(message):
    if not is_admin(message.from_user.id):
        return
    bot.send_message(message.chat.id, "Users:", reply_markup=users_keyboard())


# --------------------------------------------------------------------------
# Messages
# --------------------------------------------------------------------------
def try_admin_login(message):
    """Password login. Returns True if the message was the password."""
    if not ADMIN_PASSWORD or message.content_type != "text":
        return False
    if not hmac.compare_digest(message.text.encode(), ADMIN_PASSWORD.encode()):
        return False
    uid = str(message.from_user.id)
    with lock:
        ADMIN_IDS.add(uid)
        USER_MESSAGES.pop(uid, None)   # an admin is no longer a regular user
    save_data()
    try:  # remove the password from the chat
        bot.delete_message(message.chat.id, message.message_id)
    except Exception as e:
        log.warning("Could not delete the password message: %s", e)
    bot.send_message(message.chat.id, "You are now an administrator!", reply_markup=admin_menu())
    return True


def handle_admin_message(message, uid):
    target = CURRENT_CHAT.get(uid)
    if not target:
        bot.send_message(message.chat.id, f"First pick a user with the \"{BTN_USERS}\" button.")
        return
    try:
        bot.copy_message(int(target), message.chat.id, message.message_id)
    except Exception as e:
        log.warning("Could not send to user %s: %s", target, e)
        bot.send_message(message.chat.id, f"Send error: {e}")
        return
    add_history(target, describe(message), from_user=False)
    bot.send_message(message.chat.id, f"Sent to: {display_name(target)}",
                     reply_markup=chat_menu(target))


def handle_user_message(message):
    uid = ensure_user(message.from_user)
    add_history(uid, describe(message), from_user=True)
    header = f"New message from {display_name(uid)}:"
    for admin_id in list(ADMIN_IDS):
        try:
            bot.send_message(int(admin_id), header)
            bot.copy_message(int(admin_id), message.chat.id, message.message_id)
        except Exception as e:
            log.warning("Could not notify admin %s: %s", admin_id, e)


@bot.message_handler(content_types=CONTENT_TYPES, chat_types=["private"])
def handle_messages(message):
    uid = str(message.from_user.id)
    if not is_admin(uid) and try_admin_login(message):
        return
    if is_admin(uid):
        handle_admin_message(message, uid)
    else:
        handle_user_message(message)


# --------------------------------------------------------------------------
# Inline buttons
# --------------------------------------------------------------------------
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    admin_id = str(call.from_user.id)
    if not is_admin(admin_id):                  # guard against forged callback_data
        bot.answer_callback_query(call.id)
        return
    data, chat_id, msg_id = call.data, call.message.chat.id, call.message.message_id
    bot.answer_callback_query(call.id)

    if data == "none":
        return

    if data == "back_to_menu":
        CURRENT_CHAT.pop(admin_id, None)
        try:
            bot.delete_message(chat_id, msg_id)
        except Exception as e:
            log.debug("delete_message: %s", e)
        bot.send_message(chat_id, "Admin panel", reply_markup=admin_menu())
        return

    action, _, target = data.partition("_")
    if target not in USER_MESSAGES:
        bot.send_message(chat_id, "User not found (the chat may already be deleted).",
                         reply_markup=admin_menu())
        return

    if action == "user":
        CURRENT_CHAT[admin_id] = target
        text, markup = f"{history_text(target)}\n\nType your reply:", chat_menu(target)
    elif action == "delete":
        text = f"Delete the chat with {display_name(target)} and its history?"
        markup = confirm_menu(target)
    elif action == "confirm":
        with lock:
            USER_MESSAGES.pop(target, None)
        save_data()
        for k in [k for k, v in CURRENT_CHAT.items() if v == target]:
            del CURRENT_CHAT[k]
        try:
            bot.delete_message(chat_id, msg_id)
        except Exception as e:
            log.debug("delete_message: %s", e)
        bot.send_message(chat_id, "Chat deleted", reply_markup=admin_menu())
        return
    else:
        return

    try:
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=markup)
    except Exception as e:   # e.g. "message is not modified"
        log.debug("edit_message_text: %s", e)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def run_web():
    from flask import Flask
    app = Flask(__name__)

    @app.route("/")
    def home():
        return "Bot running"

    app.run(host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    log.info("Bot started. Admins: %d, users: %d", len(ADMIN_IDS), len(USER_MESSAGES))
    if not ADMIN_IDS and not ADMIN_PASSWORD:
        log.warning("No admins configured: set ADMIN_PASSWORD or ADMIN_IDS in .env")
    bot.remove_webhook()
    if ENABLE_WEB:
        threading.Thread(target=run_web, daemon=True).start()
    bot.infinity_polling(skip_pending=True)
