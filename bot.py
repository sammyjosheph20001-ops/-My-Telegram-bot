import os
import sqlite3
import asyncio
import re
from html.parser import HTMLParser
from urllib.parse import quote_plus, urlparse, parse_qs, unquote
from urllib.request import Request, urlopen
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID")
DB_PATH = os.getenv("BOT_DB_PATH", "bot.db")



class SearchResultsParser(HTMLParser):
    """Extract public result titles, URLs and snippets from DuckDuckGo HTML."""
    def __init__(self):
        super().__init__()
        self.results = []
        self.current = None
        self.capture = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "")
        if tag == "a" and "result__a" in classes:
            if self.current and self.current.get("title"):
                self.results.append(self.current)
            self.current = {"title": "", "url": attrs.get("href", ""), "snippet": ""}
            self.capture = "title"
        elif self.current and tag in ("a", "div") and "result__snippet" in classes:
            self.capture = "snippet"

    def handle_data(self, data):
        if self.current and self.capture in ("title", "snippet"):
            self.current[self.capture] += data

    def handle_endtag(self, tag):
        if self.current and tag == "a" and self.capture == "title":
            self.capture = None
        if self.current and tag == "div" and self.capture == "snippet":
            self.capture = None

    def handle_startendtag(self, tag, attrs):
        pass

    def close(self):
        super().close()
        if self.current and self.current.get("title"):
            self.results.append(self.current)
            self.current = None


def fetch_public_results(query, limit=5):
    """Fetch publicly indexed web results; no private Telegram data is accessed."""
    url = "https://html.duckduckgo.com/html/?q=" + quote_plus(query)
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=12) as response:
        html = response.read().decode("utf-8", errors="replace")
    parser = SearchResultsParser()
    parser.feed(html)
    parser.close()

    results = []
    for item in parser.results:
        link = item["url"]
        parsed = urlparse(link)
        if "duckduckgo.com" in parsed.netloc:
            target = parse_qs(parsed.query).get("uddg", [""])[0]
            if target:
                link = unquote(target)
        if not link.startswith(("http://", "https://")):
            continue
        title = re.sub(r"\s+", " ", item["title"]).strip()
        snippet = re.sub(r"\s+", " ", item["snippet"]).strip()
        results.append((title[:180], link, snippet[:350]))
        if len(results) >= limit:
            break
    return results


async def send_search_results(update, query, heading):
    await update.message.reply_text(f"ð {heading}\nSearching public web indexesâ¦")
    try:
        results = await asyncio.to_thread(fetch_public_results, query, 5)
    except Exception:
        results = []

    if not results:
        await update.message.reply_text(
            "I couldn't retrieve readable results right now. The public search service may be unavailable. "
            "Try again later."
        )
        return

    for index, (title, link, snippet) in enumerate(results, 1):
        text = f"{index}. {title}\n{snippet or 'No preview available.'}\n{link}"
        await update.message.reply_text(text, disable_web_page_preview=True)


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
    await send_search_results(
        update, f'"{query}" Telegram public group',
        f"Public Telegram group search for: {query}"
    )


async def publicsearch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /publicsearch @username")
        return
    username = context.args[0].strip().lstrip("@")
    if not username or any(ch.isspace() for ch in username):
        await update.message.reply_text("Please provide one Telegram username, e.g. /publicsearch @example")
        return
    await send_search_results(
        update, f'"@{username}" Telegram',
        f"Public web mentions for @{username}"
    )


async def groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /groups @username")
        return
    username = context.args[0].strip().lstrip("@")
    if not username or any(ch.isspace() for ch in username):
        await update.message.reply_text("Enter one valid username.")
        return
    query = f'"{username}" (site:t.me OR Telegram group)'
    await send_search_results(
        update, query,
        f"Publicly indexed group references for @{username}"
    )
    await update.message.reply_text(
        "Note: these are public web-index results only. A mention or link does not prove "
        "that the account is a member of a group. Private memberships cannot be checked."
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
