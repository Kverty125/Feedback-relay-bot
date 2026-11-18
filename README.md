# Feedback Relay Bot

A Telegram feedback bot: users message the bot, admins read and reply directly from
the bot chat. No web panel, no database, just Python and one JSON file.

## Features
- Relays user messages to admins (text, photos, videos, documents, voice, stickers)
- Reply to a user from the admin panel, with recent message history
- User list sorted by last activity
- Chat deletion with confirmation
- JSON storage with atomic, thread-safe writes
- All secrets live in `.env`, nothing is hard-coded

## Quick start
```bash
git clone https://github.com/Kverty125/feedback-relay-bot.git
cd feedback-relay-bot
pip install -r requirements.txt
cp .env.example .env      # Windows: copy .env.example .env
# put BOT_TOKEN (from @BotFather) and ADMIN_PASSWORD into .env
python bot.py
```

## Becoming an admin
Either:
1. Set `ADMIN_PASSWORD` in `.env`, start the bot and send that password to it in a
   private chat. The bot deletes your message with the password.
2. Put your Telegram ID into `ADMIN_IDS` (find it via [@userinfobot](https://t.me/userinfobot)).

## Usage (admin)
- Press **Users** (or send `/users`), pick a user. Everything you type next goes to that user.
- `/exit` leaves the current chat.

## Configuration (`.env`)
| Variable | Description |
|---|---|
| `BOT_TOKEN` | bot token, **required** |
| `ADMIN_PASSWORD` | admin login password (empty = disabled) |
| `ADMIN_IDS` | comma-separated admin Telegram IDs |
| `WELCOME_TEXT` | reply to `/start` |
| `DATA_FILE` | path to the data file (default `bot_data.json`) |
| `ENABLE_WEB` / `PORT` | tiny web server for hosts that require an open port |

## Security
- Never commit `.env` or your token. If a token leaks, revoke it: @BotFather → `/revoke`.
- Use a long, random `ADMIN_PASSWORD`.

## License
MIT
