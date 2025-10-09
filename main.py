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
from pymongo import MongoClient  # ✅ Added for MongoDB

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------- Time ----------------
current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

EXTRA_CODES = {"Kosovo": "XK"}  # special cases

# ---------------- Country Flag ----------------
def country_to_flag(country_name: str) -> str:
    code = EXTRA_CODES.get(country_name)
    if not code:
        try:
            country = pycountry.countries.lookup(country_name)
            code = country.alpha_2
        except LookupError:
            return ""
    return "".join(chr(127397 + ord(c)) for c in code.upper())

# ---------------- Configuration ----------------
LOGIN_URL = "http://51.83.103.80/ints/signin"
XHR_URL = "http://51.83.103.80/ints/agent/res/data_smscdr.php?fdate1=2025-09-05%2000:00:00&fdate2=2026-09-04%2023:59:59&frange=&fclient=&fnum=&fcli=&fgdate=&fgmonth=&fgrange=&fgclient=&fgnumber=&fgcli=&fg=0&sEcho=1&iColumns=9&sColumns=%2C%2C%2C%2C%2C%2C%2C%2C&iDisplayStart=0&iDisplayLength=3&mDataProp_0=0&sSearch_0=&bRegex_0=false&bSearchable_0=true&bSortable_0=true&mDataProp_1=1&sSearch_1=&bRegex_1=false&bSearchable_1=true&bSortable_1=true&mDataProp_2=2&sSearch_2=&bRegex_2=false&bSearchable_2=true&bSortable_2=true&mDataProp_3=3&sSearch_3=&bRegex_3=false&bSearchable_3=true&bSortable_3=true&mDataProp_4=4&sSearch_4=&bRegex_4=false&bSearchable_4=true&bSortable_4=true&mDataProp_5=5&sSearch_5=&bRegex_5=false&bSearchable_5=true&bSortable_5=true&mDataProp_6=6&sSearch_6=&bRegex_6=false&bSearchable_6=true&bSortable_6=true&mDataProp_7=7&sSearch_7=&bRegex_7=false&bSearchable_7=true&bSortable_7=true&mDataProp_8=8&sSearch_8=&bRegex_8=false&bSearchable_8=true&bSortable_8=false&sSearch=&bRegex=false&iSortCol_0=0&sSortDir_0=desc&iSortingCols=1&_=1756968295291"

USERNAME = os.getenv("USERNAME", "h2ideveloper898")
PASSWORD = os.getenv("PASSWORD", "112233")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8445473322:AAER8MAIhZMTW3RQW1vSKYC00CZ1tTOF2QQ")
DEVELOPER_ID = "@hiden_25"
CHANNEL_LINK = "https://t.me/freeotpss"

# ---------------- Headers ----------------
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "http://51.83.103.80/ints/login"
}
AJAX_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "http://51.83.103.80/ints/agent/SMSCDRStats"
}

# ---------------- Flask + Telegram Setup ----------------
app = Flask(__name__)
bot = telegram.Bot(token=BOT_TOKEN)
session = requests.Session()
seen = set()

# ---------------- MongoDB Configuration ----------------
MONGO_URI = "mongodb+srv://number25:number25@cluster0.kdeklci.mongodb.net/"
MONGO_DB_NAME = "otp_database"
MONGO_COLLECTION_NAME = "numbers"

mongo_client = MongoClient(MONGO_URI)
mongo_db = mongo_client[MONGO_DB_NAME]
numbers_collection = mongo_db[MONGO_COLLECTION_NAME]

# ✅ Save only unique numbers to MongoDB
def save_number_to_db(number: str):
    """Save unique number to MongoDB"""
    number = number.strip()
    if not number:
        return
    try:
        if not numbers_collection.find_one({"number": number}):
            numbers_collection.insert_one({
                "number": number,
                "timestamp": datetime.now()
            })
            print(f"✅ Saved to MongoDB: {number}")
        else:
            print(f"⚠️ Number already exists in DB: {number}")
    except Exception as e:
        print(f"❌ MongoDB insert error: {e}")

# ---------------- Helper Functions ----------------
def mask_number(number):
    if len(number) <= 6:
        return number
    mid = len(number) // 2
    return number[:mid-1] + "***" + number[mid+2:]

CHAT_IDS = ["-1001926462756"]

def extract_otp(message: str) -> str | None:
    message = message.strip()
    keyword_regex = re.search(r"(otp|code|pin|password)[^\d]{0,10}(\d[\d\-]{3,8})", message, re.I)
    if keyword_regex:
        return re.sub(r"\D", "", keyword_regex.group(2))
    reverse_regex = re.search(r"(\d[\d\-]{3,8})[^\w]{0,10}(otp|code|pin|password)", message, re.I)
    if reverse_regex:
        return re.sub(r"\D", "", reverse_regex.group(1))
    generic_regex = re.findall(r"\b\d[\d\-]{3,8}\b", message)
    if generic_regex:
        for num in generic_regex:
            num_clean = re.sub(r"\D", "", num)
            if 4 <= len(num_clean) <= 8 and not (1900 <= int(num_clean) <= 2099):
                return num_clean
    return None

# ---------------- Telegram Message ----------------
async def send_telegram_message(current_time, country, number, sender, message):
    flag = country_to_flag(country)
    otp = extract_otp(message)
    otp_line = f"<blockquote>🔑 <b>OTP:</b> <code>{html.escape(otp)}</code></blockquote>\n" if otp else ""

    formatted = (
        f"{flag} New {country} {sender} OTP Recived \n\n"
        f"<blockquote>🕰 <b>Time:</b> <b>{html.escape(str(current_time))}</b></blockquote>\n"
        f"<blockquote>🌍 <b>Country:</b> <b>{html.escape(country)} {flag}</b></blockquote>\n"
        f"<blockquote>📱 <b>Service:</b> <b>{html.escape(sender)}</b></blockquote>\n"
        f"<blockquote>📞 <b>Number:</b> <b>{html.escape(mask_number(number))}</b></blockquote>\n"
        f"{otp_line}"
        f"<blockquote>✉️ <b>Full Message:</b></blockquote>\n"
        f"<blockquote><code>{html.escape(message)}</code></blockquote>\n\n"
    )

    keyboard = [
        [InlineKeyboardButton("📱 Channel", url=f"{CHANNEL_LINK}")],
        [InlineKeyboardButton("👨‍💻 Developer", url=f"https://t.me/{DEVELOPER_ID.lstrip('@')}")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await asyncio.sleep(1)

    for chat_id in CHAT_IDS:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=formatted,
                reply_markup=reply_markup,
                disable_web_page_preview=True,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"❌ Failed to send to {chat_id}: {e}")

    # ✅ Save number to MongoDB (after sending)
    save_number_to_db(number)

# ---------------- Login ----------------
def login():
    res = session.get("http://51.83.103.80/ints/login", headers=HEADERS)
    soup = BeautifulSoup(res.text, "html.parser")
    captcha_text = None
    for string in soup.stripped_strings:
        if "What is" in string and "+" in string:
            captcha_text = string.strip()
            break
    match = re.search(r"What is\s*(\d+)\s*\+\s*(\d+)", captcha_text or "")
    if not match:
        print("❌ Captcha not found.")
        return False
    a, b = int(match.group(1)), int(match.group(2))
    captcha_answer = str(a + b)
    print(f"✅ Captcha solved: {a} + {b} = {captcha_answer}")
    payload = {"username": USERNAME, "password": PASSWORD, "capt": captcha_answer}
    res = session.post(LOGIN_URL, data=payload, headers=HEADERS)
    if "SMSCDRStats" not in res.text:
        print("❌ Login failed.")
        return False
    print("✅ Logged in successfully.")
    return True

# ---------------- OTP Fetch Loop ----------------
def fetch_otp_loop():
    print("\n🔄 Starting OTP fetch loop...\n")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    while True:
        try:
            res = session.get(XHR_URL, headers=AJAX_HEADERS)
            data = res.json()
            otps = data.get("aaData", [])
            otps = [row for row in otps if isinstance(row[0], str) and ":" in row[0]]
            new_found = False
            with open("otp_logs.txt", "a", encoding="utf-8") as f:
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
                    new_found = True
                    log_formatted = (
                        f"📱 Number: {number}\n"
                        f"🏷️ Sender ID: {sender}\n"
                        f"💬 Message: {message}\n"
                        f"{'-'*60}"
                    )
                    print(log_formatted)
                    f.write(log_formatted + "\n")
                    loop.run_until_complete(send_telegram_message(time_, operator, number, sender, message))
            if not new_found:
                print("⏳ No new OTPs.")
        except Exception as e:
            print("❌ Error fetching OTPs:", e)
        time.sleep(1.2)

# ---------------- Flask Routes ----------------
@app.route('/health')
def health():
    return Response("OK", status=200)

@app.route("/")
def root():
    logger.info("Root endpoint requested")
    return Response("OK", status=200)

# ---------------- Start Everything ----------------
def start_otp_loop():
    if login():
        fetch_otp_loop()

if __name__ == '__main__':
    otp_thread = threading.Thread(target=start_otp_loop, daemon=True)
    otp_thread.start()
    flask_thread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=8080), daemon=True)
    flask_thread.start()
    # Telegram listener not needed here since only sending OTPs
    while True:
        time.sleep(10)
