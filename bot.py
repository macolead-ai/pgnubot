import os
import re
import logging
import secrets
import string
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("bot")

# ============================================================
# Health server (Render/Railway need an open port)
# ============================================================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "text/plain"); self.end_headers()
        self.wfile.write(b"Pass Bot alive.")
    def do_HEAD(self):
        self.send_response(200); self.send_header("Content-Type", "text/plain"); self.end_headers()
    def log_message(self, format, *args):
        return

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()

# ============================================================
# Password generator (cryptographically secure)
# ============================================================
LOWER = string.ascii_lowercase
UPPER = string.ascii_uppercase
DIGITS = string.digits
SYMBOLS = "!@#$%^&*()-_=+[]{}<>?"

def generate_password(length: int = 16) -> str:
    pool = LOWER + UPPER + DIGITS + SYMBOLS
    # Force at least one of each type
    required = [
        secrets.choice(LOWER),
        secrets.choice(UPPER),
        secrets.choice(DIGITS),
        secrets.choice(SYMBOLS),
    ]
    pwd = required + [secrets.choice(pool) for _ in range(max(0, length - len(required)))]
    rng = secrets.SystemRandom()
    rng.shuffle(pwd)
    return "".join(pwd[:length])

# ============================================================
# Strength checker
# ============================================================
def check_strength(pwd: str) -> str:
    score = 0
    length = len(pwd)
    if length >= 8: score += 1
    if length >= 12: score += 1
    if length >= 16: score += 1
    if re.search(r"[a-z]", pwd): score += 1
    if re.search(r"[A-Z]", pwd): score += 1
    if re.search(r"[0-9]", pwd): score += 1
    if re.search(r"[^a-zA-Z0-9]", pwd): score += 1

    rating = {
        0: ("🔴 Very Weak", "Crackable in seconds"),
        1: ("🔴 Very Weak", "Crackable in seconds"),
        2: ("🟠 Weak", "Crackable in minutes"),
        3: ("🟠 Weak", "Crackable in hours"),
        4: ("🟡 Fair", "Crackable in days"),
        5: ("🟢 Strong", "Crackable in years"),
        6: ("🟢 Strong", "Practically uncrackable"),
        7: ("💎 Very Strong", "Practically uncrackable"),
    }
    label, desc = rating.get(score, ("🟢 Strong", ""))
    return f"{label}\n_{desc}_\nLength: {length} chars"

# ============================================================
# Menus
# ============================================================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ Quick (16 chars, strong)", callback_data="gen_quick")],
        [InlineKeyboardButton("🛠 Custom Length", callback_data="ask_custom")],
        [InlineKeyboardButton("📋 Bulk (5 passwords)", callback_data="gen_bulk")],
        [InlineKeyboardButton("🔍 Check My Password", callback_data="ask_check")],
    ])

def back_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="home")]])

# ============================================================
# Handlers
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "🔐 *Password Generator*\n\n"
        "Generate strong, random passwords using cryptographically secure methods.\n\n"
        "Pick an option:",
        reply_markup=main_menu(),
        parse_mode="Markdown",
    )

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "home":
        context.user_data.clear()
        await query.edit_message_text(
            "🔐 *Password Generator*\n\nPick an option:",
            reply_markup=main_menu(),
            parse_mode="Markdown",
        )
        return

    if data == "gen_quick":
        pwd = generate_password(length=16)
        strength = check_strength(pwd)
        await query.edit_message_text(
            f"🔐 *Your password:*\n\n`{pwd}`\n\n{strength}\n\n_Tap the password to copy._",
            reply_markup=main_menu(),
            parse_mode="Markdown",
        )
        return

    if data == "gen_bulk":
        pwds = [generate_password(length=16) for _ in range(5)]
        text = "🔐 *5 strong passwords:*\n\n" + "\n".join(f"`{p}`" for p in pwds)
        await query.edit_message_text(
            text + "\n\n_Tap any to copy._",
            reply_markup=main_menu(),
            parse_mode="Markdown",
        )
        return

    if data == "ask_custom":
        context.user_data["mode"] = "custom"
        await query.edit_message_text(
            "🛠 *Custom Password*\n\nSend me a number for the length (between 4 and 64).\n\nExample: `20`",
            reply_markup=back_kb(),
            parse_mode="Markdown",
        )
        return

    if data == "ask_check":
        context.user_data["mode"] = "check"
        await query.edit_message_text(
            "🔍 *Check Password Strength*\n\nSend me a password to analyze.\n\n"
            "_(Note: for testing only — don't paste real account passwords.)_",
            reply_markup=back_kb(),
            parse_mode="Markdown",
        )
        return

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("mode")
    text = update.message.text.strip()

    if mode == "custom":
        try:
            length = int(text)
            if length < 4 or length > 64:
                raise ValueError
        except ValueError:
            await update.message.reply_text("⚠️ Send a number between 4 and 64.")
            return
        pwd = generate_password(length=length)
        strength = check_strength(pwd)
        await update.message.reply_text(
            f"🔐 *Your password ({length} chars):*\n\n`{pwd}`\n\n{strength}",
            reply_markup=main_menu(),
            parse_mode="Markdown",
        )
        context.user_data.pop("mode", None)
        return

    if mode == "check":
        strength = check_strength(text)
        await update.message.reply_text(
            f"🔍 *Password analysis:*\n\n{strength}",
            reply_markup=main_menu(),
            parse_mode="Markdown",
        )
        context.user_data.pop("mode", None)
        return

    await update.message.reply_text(
        "Tap a button to start. Use /start.",
        reply_markup=main_menu(),
    )

# ============================================================
# Main
# ============================================================
def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        log.critical("BOT_TOKEN env var missing!")
        return

    threading.Thread(target=run_health_server, daemon=True).start()

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(menu_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    log.info("Password Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
