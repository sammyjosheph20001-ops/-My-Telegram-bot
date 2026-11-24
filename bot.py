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
        [InlineKeyboardButton(
            "Search public Telegram links",
            url=f"https://www.google.com/search?q={q1}"
        )],
        [InlineKeyboardButton(
            "Search public group mentions",
            url=f"https://www.google.com/search?q={q2}"
        )],
        [InlineKeyboardButton(
            "Check TGStat",
            url=f"https://tgstat.com/search?query={q3}"
        )]
    ])

    await update.message.reply_text(
        f"🔎 Public group references for @{username}\n\n"
        "These searches may find public group links or mentions. "
        "A mention does not prove membership. Private groups cannot be checked.",
        reply_markup=keyboard
    )
