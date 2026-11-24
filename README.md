# Telegram Public Profile Lookup Bot

A safe starter bot with a Telegram-style lookup card. Users voluntarily register the
details that can be searched by other users.

## Included
- `/start`, `/help`
- `/register Name | Bio | Public groups`
- `/myprofile`
- `/lookup username_or_ID`
- `/deleteprofile`
- SQLite storage

## Important limitations
Telegram bots cannot query arbitrary private account records. This bot does not
collect or expose private phone numbers, linked contacts, private chats, or
unavailable username-change history. It only returns profiles voluntarily
registered with this bot.

## Run
1. Install Python 3.10+.
2. Install dependencies:
   `pip install -r requirements.txt`
3. Create a bot with Telegram's official BotFather.
4. Set your token as an environment variable (do not post it in chat):
   - macOS/Linux: `export TELEGRAM_BOT_TOKEN="YOUR_TOKEN"`
   - Windows PowerShell: `$env:TELEGRAM_BOT_TOKEN="YOUR_TOKEN"`
5. Run:
   `python bot.py`

The database `bot.db` is created automatically in the working directory.
