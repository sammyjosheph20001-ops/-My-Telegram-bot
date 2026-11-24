import os
import sqlite3
from urllib.parse import quote_plus
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
    existing = {r[1] for r in conn.execute("PRAGMA table_info(profiles)")}
    for name, definition in [
        ("country", "TEXT DEFAULT ''"), ("city", "TEXT DEFAULT ''"),
        ("occupation", "TEXT DEFAULT ''"), ("public_links", "TEXT DEFAULT ''"),
        ("added_by_admin", "INTEGER DEFAULT 0"),
    ]:
        if name not in existing:
            conn.execute(f"ALTER TABLE profiles ADD COLUMN {name} {definition}")
    return conn


def is_admin(update: Update) -> bool:
    return bool(ADMIN_USER_ID and str(update.effective_user.id) == ADMIN_USER_ID)


def profile_text(row):
    user_id, username, name, bio, groups_text, country, city, occupation, links = row
    lines = [f"ð¤ {name}", f"ð Telegram ID: {user_id}",
             f"ð Username: @{username}" if username else "ð Username: Not set"]
    for label, value in [
        ("ð Bio", bio), ("ð Country", country), ("ð City", city),
        ("ð¼ Occupation", occupation), ("ð¥ Public groups", groups_text),
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
        "ð Public Profile Directory & Public Search\n\n"
        "/register â save your own profile\n"
        "/lookup <username-or-ID> â search saved profiles\n"
        "/groupsearch <keywords> â find public Telegram group search results\n"
        "/publicsearch <username> â search public web mentions of a username\n"
        "/groups <username> â search public group references for a username\n"
        "/myprofile â view your profile\n"
        "/deleteprofile â delete your own profile\n"
        "/myid â show your Telegram numeric ID"
        f"{admin_line}\n\n"
        "Public searches show indexed references only. They cannot reveal private group memberships, phone numbers, or private chats."
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Your Telegram numeric ID is: {update.effective_user.id}")


async def groupsearch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /groupsearch Data Sale Ireland")
        return
    query = " ".join(context.args).strip()
    q = quote_plus(query + " Telegram group")
    q_tme = quote_plus(query + " site:t.me")
    q_tgstat = quote_plus(query)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Search public Telegram links", url=f"https://www.google.com/search?q={q_tme}")],
        [InlineKeyboardButton("Search the web", url=f"https://www.google.com/search?q={q}")],
        [InlineKeyboardButton("Search TGStat directory", url=f"https://tgstat.com/search?query={q_tgstat}")],
    ])
    await update.message.reply_text(
        f"ð Public group search for: {query}\n\n"
        "These links search public listings and indexed pages. Results may be incomplete or outdated; "
        "check the group name, description, and invite link before joining.",
        reply_markup=keyboard
    )


async def publicsearch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /publicsearch @username")
        return
    username = context.args[0].strip().lstrip("@")
    if not username or any(ch.isspace() for ch in username):
        await update.message.reply_text("Please provide one Telegram username, e.g. /publicsearch @example")
        return
    exact = quote_plus('"@' + username + '" Telegram')
    tme = quote_plus('"' + username + '" site:t.me')
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Open Telegram profile", url=f"https://t.me/{quote_plus(username)}")],
        [InlineKeyboardButton("Search public web mentions", url=f"https://www.google.com/search?q={exact}")],
        [InlineKeyboardButton("Search public Telegram links", url=f"https://www.google.com/search?q={tme}")],
    ])
    await update.message.reply_text(
        f"ð Public search links for @{username}\n\n"
        "This can find indexed public mentions or links, but it cannot list every group a person belongs to. "
        "Private memberships and private account information are not accessible.",
        reply_markup=keyboard
    )


async def groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /groups @username")
        return
    username = context.args[0].strip().lstrip("@")
    if not username or any(ch.isspace() for ch in username):
        await update.message.reply_text("Enter one valid username.")
        return
    q1 = quote_plus(f'"{username}" site:t.me')
    q2 = quote_plus(f'"@{username}" Telegram group')
    q3 = quote_plus(username)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Search public Telegram links", url=f"https://www.google.com/search?q={q1}")],
        [InlineKeyboardButton("Search public group mentions", url=f"https://www.google.com/search?q={q2}")],
        [InlineKeyboardButton("Check TGStat", url=f"https://tgstat.com/search?query={q3}")]
    ])
    await update.message.reply_text(
        f"ð Public group references for @{username}\n\n"
        "These searches may find public group links or mentions. A mention does not prove membership. "
        "Private groups cannot be checked.",
        reply_markup=keyboard
    )


async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage:\n/register Name | Bio | Country | City | Occupation | Public groups/links\n\n"
            "Example:\n/register Sam | Website designer | Nigeria | Port Harcourt | Designer | @publicgroup"
        )
        return
    fields = " ".join(context.args).split("|")
    fields = [fields[i].strip() if i < len(fields) else "" for i in range(6)]
    name, bio, country, city, occupation, groups_text = fields
    user = update.effective_user
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
        (user.id, user.username or "", name, bio, groups_text, country, city, occupation, "")
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
    await update.message.reply_text(profile_text(row) if row else "No saved profile found. Try /publicsearch username for public web search links.")


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
    handlers = [
        ("start", start), ("help", help_cmd), ("myid", myid),
        ("groupsearch", groupsearch), ("publicsearch", publicsearch),
        ("groups", groups), ("register", register), ("addprofile", addprofile),
        ("myprofile", myprofile), ("lookup", lookup),
        ("deleteprofile", deleteprofile),
    ]
    for command, handler in handlers:
        app.add_handler(CommandHandler(command, handler))
    app.run_polling()


if __name__ == "__main__":
    main()
