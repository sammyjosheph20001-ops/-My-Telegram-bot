import os
import sqlite3
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DB_PATH = os.getenv("BOT_DB_PATH", "bot.db")

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            display_name TEXT NOT NULL,
            bio TEXT DEFAULT '',
            public_groups TEXT DEFAULT ''
        )
    """)
    return conn

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔎 Public Profile Lookup\n\n"
        "Commands:\n"
        "/register — create or update your voluntary public profile\n"
        "/lookup <username-or-ID> — find a profile registered with this bot\n"
        "/myprofile — view your profile\n"
        "/deleteprofile — remove your profile\n"
        "/help — show commands\n\n"
        "This bot only displays information users choose to submit. "
        "It cannot access private phone numbers, linked contacts, private chats, "
        "or hidden Telegram account history."
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text(
            "Usage:\n/register Your display name | Short bio | Public groups\n\n"
            "Example:\n/register Sam | Designer | @my_public_group"
        )
        return

    raw = " ".join(context.args)
    parts = [p.strip() for p in raw.split("|", 2)]
    display_name = parts[0] or user.full_name
    bio = parts[1] if len(parts) > 1 else ""
    groups = parts[2] if len(parts) > 2 else ""

    conn = db()
    conn.execute(
        "INSERT INTO profiles(user_id, username, display_name, bio, public_groups) "
        "VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
        "username=excluded.username, display_name=excluded.display_name, "
        "bio=excluded.bio, public_groups=excluded.public_groups",
        (user.id, user.username or "", display_name, bio, groups)
    )
    conn.commit()
    conn.close()
    await update.message.reply_text(
        "✅ Your profile has been saved.\n"
        "Only the details you submitted are searchable through this bot."
    )

async def profile_text(row):
    user_id, username, display_name, bio, groups = row
    return (
        f"👤 {display_name}\n"
        f"🆔 Telegram ID: {user_id}\n"
        f"🔗 Username: @{username}" if username else
        f"👤 {display_name}\n🆔 Telegram ID: {user_id}\n🔗 Username: Not set"
    ) + (
        f"\n\n📝 Bio: {bio}" if bio else ""
    ) + (
        f"\n\n👥 Public groups: {groups}" if groups else ""
    )

async def myprofile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = db()
    row = conn.execute(
        "SELECT user_id, username, display_name, bio, public_groups FROM profiles WHERE user_id=?",
        (update.effective_user.id,)
    ).fetchone()
    conn.close()
    if not row:
        await update.message.reply_text("No profile found. Use /register to create one.")
        return
    await update.message.reply_text(await profile_text(row))

async def lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /lookup username_or_ID")
        return
    term = context.args[0].strip()
    conn = db()
    if term.lstrip("@").isdigit():
        row = conn.execute(
            "SELECT user_id, username, display_name, bio, public_groups FROM profiles WHERE user_id=?",
            (int(term.lstrip("@")),)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT user_id, username, display_name, bio, public_groups FROM profiles WHERE lower(username)=lower(?)",
            (term.lstrip("@"),)
        ).fetchone()
    conn.close()
    if not row:
        await update.message.reply_text(
            "No voluntarily registered profile found. "
            "This bot does not scrape or reveal private Telegram information."
        )
        return
    await update.message.reply_text(await profile_text(row))

async def deleteprofile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = db()
    cur = conn.execute("DELETE FROM profiles WHERE user_id=?", (update.effective_user.id,))
    conn.commit()
    conn.close()
    if cur.rowcount:
        await update.message.reply_text("🗑️ Your profile has been deleted.")
    else:
        await update.message.reply_text("You do not have a saved profile.")

def main():
    if not TOKEN:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN in your environment before starting.")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("myprofile", myprofile))
    app.add_handler(CommandHandler("lookup", lookup))
    app.add_handler(CommandHandler("deleteprofile", deleteprofile))
    app.run_polling()

if __name__ == "__main__":
    main()
