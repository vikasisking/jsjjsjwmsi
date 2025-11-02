import requests
import re
import time
import hashlib
import html
from bs4 import BeautifulSoup
from flask import Flask, Response
import threading
import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import asyncio
import os
import logging
import pycountry
from datetime import datetime
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

EXTRA_CODES = {"Kosovo": "XK"}
LOGIN_URL = "http://51.83.103.80/ints/signin"
XHR_URL = "http://51.83.103.80/ints/agent/res/data_smscdr.php?fdate1=2025-09-05%2000:00:00&fdate2=2026-09-04%2023:59:59&frange=&fclient=&fnum=&fcli=&fgdate=&fgmonth=&fgrange=&fgclient=&fgnumber=&fgcli=&fg=0&sEcho=1&iColumns=9&sColumns=%2C%2C%2C%2C%2C%2C%2C%2C&iDisplayStart=0&iDisplayLength=1&mDataProp_0=0&sSearch_0=&bRegex_0=false&bSearchable_0=true&bSortable_0=true&mDataProp_1=1&sSearch_1=&bRegex_1=false&bSearchable_1=true&bSortable_1=true&mDataProp_2=2&sSearch_2=&bRegex_2=false&bSearchable_2=true&bSortable_2=true&mDataProp_3=3&sSearch_3=&bRegex_3=false&bSearchable_3=true&bSortable_3=true&mDataProp_4=4&sSearch_4=&bRegex_4=false&bSearchable_4=true&bSortable_4=true&mDataProp_5=5&sSearch_5=&bRegex_5=false&bSearchable_5=true&bSortable_5=true&mDataProp_6=6&sSearch_6=&bRegex_6=false&bSearchable_6=true&bSortable_6=true&mDataProp_7=7&sSearch_7=&bRegex_7=false&bSearchable_7=true&bSortable_7=true&mDataProp_8=8&sSearch_8=&bRegex_8=false&bSearchable_8=true&bSortable_8=false&sSearch=&bRegex=false&iSortCol_0=0&sSortDir_0=desc&iSortingCols=1&_=1756968295291"
USERNAME = os.getenv("USERNAME", "Parrner473vr")
PASSWORD = os.getenv("PASSWORD", "112233")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8446081188:AAEuiBt4q-1eTklPeN1Hu2mmnqs5DgTRb98")

CHAT_IDS = ["-1001926462756"]
CHANNEL_LINK = "https://t.me/freeotpss"
ADMIN_ID = 7761576669

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "http://51.83.103.80/ints/login"
}
AJAX_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "http://51.83.103.80/ints/agent/SMSCDRStats"
}

app = Flask(__name__)
bot = telegram.Bot(token=BOT_TOKEN)
session = requests.Session()
seen = set()

def country_to_flag(country_name: str) -> str:
    code = EXTRA_CODES.get(country_name)
    if not code:
        try:
            country = pycountry.countries.lookup(country_name)
            code = country.alpha_2
        except LookupError:
            return ""
    return "".join(chr(127397 + ord(c)) for c in code.upper())

# ───────────────────────────────────────────────────────────────
# LOGIN HANDLER
def login():
    res = session.get("http://51.83.103.80/ints/login", headers=HEADERS)
    soup = BeautifulSoup(res.text, "html.parser")
    captcha_text = next((s.strip() for s in soup.stripped_strings if "What is" in s and "+" in s), None)

    match = re.search(r"What is\s*(\d+)\s*\+\s*(\d+)", captcha_text or "")
    if not match:
        logger.error("❌ Captcha not found.")
        return False

    captcha_answer = str(int(match.group(1)) + int(match.group(2)))
    payload = {"username": USERNAME, "password": PASSWORD, "capt": captcha_answer}
    res = session.post(LOGIN_URL, data=payload, headers=HEADERS)
    if "SMSCDRStats" not in res.text:
        logger.error("❌ Login failed.")
        return False
    return True

# ───────────────────────────────────────────────────────────────
# UTILITIES
def mask_number(number):
    if len(number) <= 6:
        return number
    mid = len(number) // 2
    return number[:mid-1] + "***" + number[mid+2:]

def extract_otp(message: str) -> str | None:
    message = message.strip()
    keyword_regex = re.search(r"(otp|code|pin|password)[^\d]{0,10}(\d[\d\-]{3,8})", message, re.I)
    if keyword_regex:
        return re.sub(r"\D", "", keyword_regex.group(2))
    reverse_regex = re.search(r"(\d[\d\-]{3,8})[^\w]{0,10}(otp|code|pin|password)", message, re.I)
    if reverse_regex:
        return re.sub(r"\D", "", reverse_regex.group(1))
    generic_regex = re.findall(r"\b\d[\d\-]{3,8}\b", message)
    for num in generic_regex:
        num_clean = re.sub(r"\D", "", num)
        if 4 <= len(num_clean) <= 8 and not (1900 <= int(num_clean) <= 2099):
            return num_clean
    return None

# ───────────────────────────────────────────────────────────────
# TELEGRAM MESSAGING
async def send_telegram_message(current_time, country, number, sender, message):
    flag = country_to_flag(country)
    otp = extract_otp(message)
    otp_line = f"<b>🔐 OTP:</b> <code>{html.escape(otp)}</code>\n\n" if otp else ""
    formatted = (
        f"<b>{flag} {country} OTP Received</b>\n"
        f"<b>━━━━━━━━━━━━━━━━</b>\n"
        f"🌍 <b>Country:</b> <code>{html.escape(country)}</code>\n"
        f"📱 <b>Service:</b> <code>{html.escape(sender)}</code>\n"
        f"📞 <b>Number:</b> <code>{html.escape(mask_number(number))}</code>\n\n"
        f"{otp_line}"
        f"💬 <b>Message:</b>\n<code>{html.escape(message)}</code>\n"
        f"<b>━━━━━━━━━━━━━━━━</b>"
    )

    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("📡 Channel", url=CHANNEL_LINK)]])

    await asyncio.sleep(0.8)
    for chat_id in CHAT_IDS:
        try:
            await bot.send_message(chat_id=chat_id, text=formatted, reply_markup=reply_markup,
                                   disable_web_page_preview=True, parse_mode="HTML")
        except Exception as e:
            logger.error(f"❌ Failed to send to {chat_id}: {e}")

# ───────────────────────────────────────────────────────────────
# TELEGRAM COMMANDS
async def add_chat(update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ You are not allowed to use this command.")
    if not context.args:
        return await update.message.reply_text("Usage: /addchat <chat_id>")
    chat_id = context.args[0]
    if chat_id not in CHAT_IDS:
        CHAT_IDS.append(chat_id)
        await update.message.reply_text(f"✅ Chat ID {chat_id} added.")
    else:
        await update.message.reply_text("⚠️ Already in the list.")

async def remove_chat(update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ You are not allowed to use this command.")
    if not context.args:
        return await update.message.reply_text("Usage: /removechat <chat_id>")
    chat_id = context.args[0]
    if chat_id in CHAT_IDS:
        CHAT_IDS.remove(chat_id)
        await update.message.reply_text(f"✅ Chat ID {chat_id} removed.")
    else:
        await update.message.reply_text("⚠️ Not found in the list.")

async def start_command(update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("📢 Join Channel", url="https://t.me/freeotpss"),
            InlineKeyboardButton("💬 Codr Group", url="https://t.me/+RLHEkgCBOe8xOWM1")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "✅ Bot is Active & Running!\n\n👇 Stay connected with our community:",
        reply_markup=reply_markup
    )

def start_telegram_listener():
    tg_app = Application.builder().token(BOT_TOKEN).build()
    tg_app.add_handler(CommandHandler("start", start_command))
    tg_app.add_handler(CommandHandler("addchat", add_chat))
    tg_app.add_handler(CommandHandler("removechat", remove_chat))
    tg_app.run_polling()

# ───────────────────────────────────────────────────────────────
# FETCH LOOP
def fetch_otp_loop():
    logger.info("🔄 Starting OTP fetch loop...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    while True:
        try:
            res = session.get(XHR_URL, headers=AJAX_HEADERS)
            data = res.json()
            otps = [row for row in data.get("aaData", []) if isinstance(row[0], str) and ":" in row[0]]

            for row in otps:
                time_ = row[0]
                operator = row[1].split("-")[0]
                number = row[2]
                sender = row[3]
                message = row[5]
                hash_id = hashlib.md5((number + time_ + message).encode()).hexdigest()

                if hash_id in seen:
                    continue
                seen.add(hash_id)

                logger.info(f"📱 New OTP from {number} ({sender})")
                loop.run_until_complete(send_telegram_message(time_, operator, number, sender, message))

        except Exception as e:
            logger.error(f"❌ Error fetching OTPs: {e}")
            time.sleep(5)
            login()

        time.sleep(1.2)

# ───────────────────────────────────────────────────────────────
# FLASK ENDPOINTS
@app.route('/health')
def health():
    return Response("OK", status=200)

@app.route('/')
def root():
    logger.info("Root endpoint requested")
    return Response("OK", status=200)

# ───────────────────────────────────────────────────────────────
# START THREADS
def start_otp_loop():
    if login():
        fetch_otp_loop()

if __name__ == '__main__':
    threading.Thread(target=start_otp_loop, daemon=True).start()
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=8080), daemon=True).start()
    start_telegram_listener()
