import os
import sqlite3
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID")
DB_PATH = os.getenv("BOT_DB_PATH", "bot.db")

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            display_name TEXT NOT NULL,
            bio TEXT DEFAULT '',
            public_groups TEXT DEFAULT '',
            country TEXT DEFAULT '',
            city TEXT DEFAULT '',
            occupation TEXT DEFAULT '',
            public_links TEXT DEFAULT '',
            added_by_admin INTEGER DEFAULT 0
        )
    """)
    # Upgrade an existing database created by the earlier bot.
    existing = {r[1] for r in conn.execute("PRAGMA table_info(profiles)")}
    for name, definition in [
        ("country", "TEXT DEFAULT ''"),
        ("city", "TEXT DEFAULT ''"),
        ("occupation", "TEXT DEFAULT ''"),
        ("public_links", "TEXT DEFAULT ''"),
        ("added_by_admin", "INTEGER DEFAULT 0"),
    ]:
        if name not in existing:
            conn.execute(f"ALTER TABLE profiles ADD COLUMN {name} {definition}")
    return conn

def is_admin(update: Update) -> bool:
    return bool(ADMIN_USER_ID and str(update.effective_user.id) == ADMIN_USER_ID)

def profile_text(row):
    user_id, username, name, bio, groups, country, city, occupation, links = row
    lines = [f"ð¤ {name}", f"ð Telegram ID: {user_id}",
             f"ð Username: @{username}" if username else "ð Username: Not set"]
    for label, value in [
        ("ð Bio", bio), ("ð Country", country), ("ð City", city),
        ("ð¼ Occupation", occupation), ("ð¥ Public groups", groups),
        ("ð Public links", links)
    ]:
        if value:
            lines.append(f"{label}: {value}")
    return "\n".join(lines)

SELECT_FIELDS = """user_id, username, display_name, bio, public_groups,
                   country, city, occupation, public_links"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_line = "\n/addprofile â add a profile (admin only)" if is_admin(update) else ""
    await update.message.reply_text(
        "ð Public Profile Directory\n\n"
        "/register â save your own profile\n"
        "/lookup <username-or-ID> â search saved profiles\n"
        "/myprofile â view your profile\n"
        "/deleteprofile â delete your own profile\n"
        "/myid â show your Telegram numeric ID"
        f"{admin_line}\n\n"
        "Only information voluntarily provided or shared with permission is stored. "
        "Do not submit private contact details, passwords, or sensitive information."
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Your Telegram numeric ID is: {update.effective_user.id}")

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text(
            "Usage:\n/register Name | Bio | Country | City | Occupation | Public groups/links\n\n"
            "Example:\n/register Sam | Website designer | Nigeria | Port Harcourt | Designer | @publicgroup"
        )
        return
    p = [" ".join(context.args).split("|")[i].strip() if i < len(" ".join(context.args).split("|")) else ""
         for i in range(6)]
    name, bio, country, city, occupation, groups = p
    name = name or user.full_name
    conn = db()
    conn.execute(
        """INSERT INTO profiles
        (user_id, username, display_name, bio, public_groups, country, city, occupation, public_links, added_by_admin)
        VALUES(?,?,?,?,?,?,?,?,?,0)
        ON CONFLICT(user_id) DO UPDATE SET username=excluded.username,
        display_name=excluded.display_name, bio=excluded.bio,
        public_groups=excluded.public_groups, country=excluded.country,
        city=excluded.city, occupation=excluded.occupation,
        public_links=excluded.public_links, added_by_admin=0""",
        (user.id, user.username or "", name, bio, groups, country, city, occupation, "")
    )
    conn.commit()
    conn.close()
    await update.message.reply_text("â Your profile has been saved.")

async def addprofile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("â This command is available to the bot admin only.")
        return
    if not context.args:
        await update.message.reply_text(
            "Usage:\n/addprofile username | Name | Bio | Country | City | Occupation | Public groups/links\n\n"
            "Example:\n/addprofile @sam | Sam | Website designer | Nigeria | Port Harcourt | Designer | https://t.me/example\n\n"
            "Only add details the person has agreed to share or has clearly made public."
        )
        return
    parts = [p.strip() for p in " ".join(context.args).split("|", 6)]
    parts += [""] * (7 - len(parts))
    username, name, bio, country, city, occupation, links = parts
    username = username.lstrip("@").strip()
    if not username or not name:
        await update.message.reply_text("A username and display name are required.")
        return
    # Use a stable negative internal key for manually added directory entries.
    conn = db()
    existing = conn.execute("SELECT user_id FROM profiles WHERE lower(username)=lower(?)", (username,)).fetchone()
    key = existing[0] if existing else -abs(hash(username)) % 2_000_000_000 - 1
    conn.execute(
        """INSERT INTO profiles
        (user_id, username, display_name, bio, public_groups, country, city, occupation, public_links, added_by_admin)
        VALUES(?,?,?,?,?,?,?,?,?,1)
        ON CONFLICT(user_id) DO UPDATE SET username=excluded.username,
        display_name=excluded.display_name, bio=excluded.bio,
        public_groups=excluded.public_groups, country=excluded.country,
        city=excluded.city, occupation=excluded.occupation,
        public_links=excluded.public_links, added_by_admin=1""",
        (key, username, name, bio, "", country, city, occupation, links)
    )
    conn.commit()
    conn.close()
    await update.message.reply_text(f"â Saved @{username}. Search with /lookup {username}")

async def myprofile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = db()
    row = conn.execute(f"SELECT {SELECT_FIELDS} FROM profiles WHERE user_id=?",
                       (update.effective_user.id,)).fetchone()
    conn.close()
    await update.message.reply_text(profile_text(row) if row else "No profile found. Use /register.")

async def lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /lookup username_or_ID")
        return
    term = context.args[0].strip().lstrip("@")
    conn = db()
    if term.isdigit():
        row = conn.execute(f"SELECT {SELECT_FIELDS} FROM profiles WHERE user_id=?", (int(term),)).fetchone()
    else:
        row = conn.execute(f"SELECT {SELECT_FIELDS} FROM profiles WHERE lower(username)=lower(?)", (term,)).fetchone()
    conn.close()
    await update.message.reply_text(profile_text(row) if row else "No saved profile found.")

async def deleteprofile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = db()
    cur = conn.execute("DELETE FROM profiles WHERE user_id=?", (update.effective_user.id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("ðï¸ Your profile has been deleted." if cur.rowcount else "You do not have a saved profile.")

def main():
    if not TOKEN:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN in your environment.")
    app = Application.builder().token(TOKEN).build()
    for command, handler in [
        ("start", start), ("help", help_cmd), ("myid", myid),
        ("register", register), ("addprofile", addprofile),
        ("myprofile", myprofile), ("lookup", lookup),
        ("deleteprofile", deleteprofile)
    ]:
        app.add_handler(CommandHandler(command, handler))
    app.run_polling()

if __name__ == "__main__":
    main()
