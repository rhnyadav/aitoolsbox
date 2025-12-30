import os
import time
import logging
import asyncio
import aiosqlite

from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

# =========================
# ENV CONFIG
# =========================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
FORCE_SUB_CHANNEL = os.getenv("FORCE_SUB_CHANNEL")  # optional
ADS_ENABLED = os.getenv("ADS_ENABLED", "true").lower() == "true"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing")

# =========================
# LOGGING
# =========================
logging.basicConfig(level=logging.INFO)

# =========================
# DATABASE
# =========================
DB_NAME = "bot.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS usage_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            tool TEXT,
            used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS banned_users (
            user_id INTEGER PRIMARY KEY
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS ad_logs (
            user_id INTEGER,
            shown_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        await db.commit()

async def add_user(user):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
            (user.id, user.username, user.first_name)
        )
        await db.commit()

async def is_banned(user_id: int) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT 1 FROM banned_users WHERE user_id=?",
            (user_id,)
        ) as cursor:
            return await cursor.fetchone() is not None

# =========================
# RATE LIMIT
# =========================
COOLDOWN = 6
_last_request = {}

def rate_limit(user_id: int) -> bool:
    now = time.time()
    last = _last_request.get(user_id, 0)
    if now - last < COOLDOWN:
        return False
    _last_request[user_id] = now
    return True

# =========================
# KEYBOARDS
# =========================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Instagram Reels", callback_data="ig")],
        [InlineKeyboardButton("▶️ YouTube Video", callback_data="yt")],
        [InlineKeyboardButton("📘 Facebook Video", callback_data="fb")],
        [InlineKeyboardButton("🖼 Image ➜ PDF", callback_data="img_pdf")],
        [InlineKeyboardButton("📄 PDF ➜ Image", callback_data="pdf_img")],
        [InlineKeyboardButton("🔊 Text ➜ Voice", callback_data="tts")],
        [InlineKeyboardButton("✍️ Caption Generator", callback_data="caption")],
        [InlineKeyboardButton("🏷 Hashtag Generator", callback_data="hashtag")]
    ])

# =========================
# START COMMAND
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await add_user(user)

    text = (
        "👋 *Welcome to AI Tools + Downloader FREE Bot*\n\n"
        "✅ Unlimited Free Tools\n"
        "⚡ Fast & Secure\n"
        "🚫 No Payment Required\n\n"
        "👇 Select a tool below"
    )

    await update.message.reply_text(
        text,
        reply_markup=main_menu(),
        parse_mode="Markdown"
    )

# =========================
# TOOLS HANDLER
# =========================
TOOL_MESSAGES = {
    "ig": "📥 Send Instagram Reel link",
    "yt": "▶️ Send YouTube video link",
    "fb": "📘 Send Facebook video link",
    "img_pdf": "🖼 Send image to convert into PDF",
    "pdf_img": "📄 Send PDF to convert into images",
    "tts": "🔊 Send text to convert into voice",
    "caption": "✍️ Send topic for caption",
    "hashtag": "🏷 Send topic for hashtags",
}

async def tools_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    if await is_banned(user_id):
        await query.message.reply_text("🚫 You are banned.")
        return

    if not rate_limit(user_id):
        await query.message.reply_text("⏳ Please wait before next request.")
        return

    tool = query.data
    context.user_data["active_tool"] = tool

    await query.message.reply_text(
        f"🛠 *Tool Activated*\n\n{TOOL_MESSAGES.get(tool)}",
        parse_mode="Markdown"
    )

# =========================
# ADMIN COMMANDS
# =========================
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    await update.message.reply_text(
        "👑 *Admin Panel*\n\n"
        "/stats\n"
        "/ban <user_id>\n"
        "/unban <user_id>\n"
        "/broadcast <message>",
        parse_mode="Markdown"
    )

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    try:
        user_id = int(context.args[0])
    except:
        await update.message.reply_text("Usage: /ban <user_id>")
        return

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR IGNORE INTO banned_users (user_id) VALUES (?)",
            (user_id,)
        )
        await db.commit()

    await update.message.reply_text(f"🚫 User {user_id} banned")

# =========================
# ERROR HANDLER
# =========================
async def error_handler(update, context: ContextTypes.DEFAULT_TYPE):
    logging.error("Error occurred", exc_info=context.error)

# =========================
# MAIN
# =========================
async def main():
    await init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CallbackQueryHandler(tools_handler))

    app.add_error_handler(error_handler)

    print("🤖 Bot is running...")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
