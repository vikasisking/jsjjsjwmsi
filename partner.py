# updated_bot.py
import telebot
from telebot import types
import json
import os
import random
from flask import Flask, Response
import threading
import queue
import requests
import re
import unicodedata
import html
import phonenumbers
import pycountry
import time
import hashlib
from bs4 import BeautifulSoup
import logging
from datetime import datetime
#from pymongo import MongoClient

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------- CONFIG ----------------
BOT_TOKEN = "8079330430:AAFZNzmPbYoMZT_o-eQ9lWPlHEQ7DTtw56o"
ADMIN_ID = 8093935563
bot = telebot.TeleBot(BOT_TOKEN)

DATA_FILE = "bot_data.json"
NUMBERS_DIR = "numbers"
os.makedirs(NUMBERS_DIR, exist_ok=True)

# --- REPLACED PANEL (new) ---
LOGIN_URL = "http://51.83.103.80/ints/signin"
XHR_URL = "http://51.83.103.80/ints/agent/res/data_smscdr.php?fdate1=2025-09-05%2000:00:00&fdate2=2026-09-04%2023:59:59&frange=&fclient=&fnum=&fcli=&fgdate=&fgmonth=&fgrange=&fgclient=&fgnumber=&fgcli=&fg=0&sEcho=1&iColumns=9&sColumns=%2C%2C%2C%2C%2C%2C%2C%2C&iDisplayStart=0&iDisplayLength=25&mDataProp_0=0&sSearch_0=&bRegex_0=false&bSearchable_0=true&bSortable_0=true&mDataProp_1=1&sSearch_1=&bRegex_1=false&bSearchable_1=true&bSortable_1=true&mDataProp_2=2&sSearch_2=&bRegex_2=false&bSearchable_2=true&bSortable_2=true&mDataProp_3=3&sSearch_3=&bRegex_3=false&bSearchable_3=true&bSortable_3=true&mDataProp_4=4&sSearch_4=&bRegex_4=false&bSearchable_4=true&bSortable_4=true&mDataProp_5=5&sSearch_5=&bRegex_5=false&bSearchable_5=true&bSortable_5=true&mDataProp_6=6&sSearch_6=&bRegex_6=false&bSearchable_6=true&bSortable_6=true&mDataProp_7=7&sSearch_7=&bRegex_7=false&bSearchable_7=true&bSortable_7=true&mDataProp_8=8&sSearch_8=&bRegex_8=false&bSearchable_8=true&bSortable_8=false&sSearch=&bRegex=false&iSortCol_0=0&sSortDir_0=desc&iSortingCols=1&_=1756968295291"
USERNAME = os.getenv("USERNAME", "h2ideveloper898")
PASSWORD = os.getenv("PASSWORD", "112233")

OTP_GROUP_IDS = ["1001926462756"]  # updated with multiple group IDs (default)
CHANNEL_LINK = "https://t.me/freeotpss"
BACKUP = "https://t.me/+cJJcOipvAohmODBl"
DEVELOPER_ID = "@NokosVenezuelabot"

# Headers for new panel
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "http://51.83.103.80/ints/login"
}
AJAX_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "http://51.83.103.80/ints/agent/SMSCDRStats"
}

# Session for HTTP requests
session = requests.Session()

# ---------------- DATA STORAGE ----------------
data = {}
numbers_by_country = {}
current_country = None
user_messages = {}         # chat_id -> message object
user_current_country = {}  # chat_id -> selected country
temp_uploads = {}          # admin_id -> list of numbers
user_numbers = {}          # number -> chat_id
seen_messages = set()
# --- Low Inventory Settings ---
LOW_INVENTORY_THRESHOLD = 10  # alert when below this number
LAST_ALERTED = {}  # to prevent repeated alerts
message_queue = queue.Queue()
numbers_collection = None

# ---------------- DATA FUNCTIONS ----------------
def load_data():
    global data, numbers_by_country, current_country
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            numbers_by_country = data.get("numbers_by_country", {})
            current_country = data.get("current_country")
    else:
        data = {"numbers_by_country": {}, "current_country": None}
        numbers_by_country = {}
        current_country = None

def save_data():
    data["numbers_by_country"] = numbers_by_country
    data["current_country"] = current_country
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

load_data()

# ---------------- FLASK ----------------
app = Flask(__name__)

@app.route("/")
def index():
    return "Bot is running"

@app.route("/health")
def health():
    return Response("OK", status=200)

def run_flask():
    app.run(host="0.0.0.0", port=5000)

# ---------------- TELEGRAM QUEUE SENDER ----------------
def send_to_telegram(msg, chat_ids=OTP_GROUP_IDS, kb=None):
    payload = {
        "text": msg[:3900],
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if kb:
        import json
        payload["reply_markup"] = json.dumps(kb.to_dict())
    for chat_id in chat_ids:
        payload["chat_id"] = chat_id
        for _ in range(3):
            try:
                r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data=payload, timeout=10)
                if r.status_code == 200:
                    break
            except Exception as e:
                logger.error(f"Failed to send to {chat_id}: {e}")
                time.sleep(1)

def sender_worker():
    while True:
        item = message_queue.get()
        if len(item) == 2:
            msg, chat_ids = item
            kb = None
        else:
            msg, chat_ids, kb = item
        send_to_telegram(msg, chat_ids, kb)
        message_queue.task_done()
        time.sleep(0.3)

# ---------------- ADMIN FILE UPLOAD ----------------
@bot.message_handler(content_types=["document"])
def handle_document(message):
    if message.from_user.id != ADMIN_ID:
        return bot.reply_to(message, "❌ You are not the admin.")
    if not message.document.file_name.endswith(".txt"):
        return bot.reply_to(message, "❌ Please upload a .txt file.")

    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    try:
        numbers = [line.strip() for line in downloaded_file.decode("utf-8").splitlines() if line.strip()]
    except Exception:
        # fallback to latin-1
        numbers = [line.strip() for line in downloaded_file.decode("latin-1").splitlines() if line.strip()]

    if not numbers:
        return bot.reply_to(message, "❌ File is empty.")

    temp_uploads[message.from_user.id] = numbers
    markup = types.InlineKeyboardMarkup()
    for country in sorted(numbers_by_country.keys()):
        markup.add(types.InlineKeyboardButton(country, callback_data=f"addto_{country}"))
    markup.add(types.InlineKeyboardButton("➕ New Country", callback_data="addto_new"))

    bot.reply_to(message, "📂 File received. Select country to add numbers:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("addto_"))
def callback_addto(call):
    if call.from_user.id != ADMIN_ID:
        return bot.answer_callback_query(call.id, "❌ Not authorized")
    numbers = temp_uploads.get(call.from_user.id, [])
    if not numbers:
        return bot.answer_callback_query(call.id, "❌ No uploaded numbers found")

    choice = call.data[6:]
    if choice == "new":
        bot.send_message(call.message.chat.id, "✍️ Send new country name:")
        bot.register_next_step_handler(call.message, save_new_country, numbers)
    else:
        existing = numbers_by_country.get(choice, [])
        merged = list(set(existing + numbers))
        numbers_by_country[choice] = merged
        save_data()
        file_path = os.path.join(NUMBERS_DIR, f"{choice}.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(merged))
        bot.edit_message_text(f"✅ Added {len(numbers)} numbers to *{choice}*",
                              call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        temp_uploads.pop(call.from_user.id, None)

def save_new_country(message, numbers):
    country = message.text.strip()
    if not country:
        return bot.reply_to(message, "❌ Invalid country name.")
    numbers_by_country[country] = numbers
    save_data()
    file_path = os.path.join(NUMBERS_DIR, f"{country}.txt")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(numbers))
    bot.reply_to(message, f"✅ Saved {len(numbers)} numbers under *{country}*", parse_mode="Markdown")
    temp_uploads.pop(message.from_user.id, None)

# ---------------- OTP FETCHER ----------------
EXTRA_CODES = {"Kosovo": "XK"}

def country_to_flag(country_name: str) -> str:
    code = EXTRA_CODES.get(country_name)
    if not code:
        try:
            country = pycountry.countries.lookup(country_name)
            code = country.alpha_2
        except LookupError:
            return ""
    return "".join(chr(127397 + ord(c)) for c in code.upper())

def login():
    try:
        res = session.get(LOGIN_URL, headers=HEADERS, timeout=10)
    except Exception as e:
        logger.error(f"❌ Error fetching login page: {e}")
        return False
    soup = BeautifulSoup(res.text, "html.parser")

    captcha_text = None
    for string in soup.stripped_strings:
        if "What is" in string and "+" in string:
            captcha_text = string.strip()
            break

    match = re.search(r"What is\s*(\d+)\s*\+\s*(\d+)", captcha_text or "")
    if not match:
        logger.error("❌ Captcha not found.")
        return False

    a, b = int(match.group(1)), int(match.group(2))
    captcha_answer = str(a + b)
    logger.info(f"✅ Captcha solved: {a} + {b} = {captcha_answer}")

    payload = {
        "username": USERNAME,
        "password": PASSWORD,
        "capt": captcha_answer
    }

    try:
        res = session.post(LOGIN_URL, data=payload, headers=HEADERS, timeout=10)
    except Exception as e:
        logger.error(f"❌ Login POST failed: {e}")
        return False

    if "SMSCDRStats" not in res.text:
        logger.error("❌ Login failed.")
        return False

    logger.info("✅ Logged in successfully.")
    return True

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

def mask_number(number: str) -> str:
    if len(number) <= 6:
        return number
    mid = len(number) // 2
    return number[:mid-1] + "***" + number[mid+2:]

def country_from_number(number: str) -> tuple[str, str]:
    try:
        parsed = phonenumbers.parse("+" + number)
        region = phonenumbers.region_code_for_number(parsed)
        if not region:
            return "Unknown", "🌍"
        country_obj = pycountry.countries.get(alpha_2=region)
        if not country_obj:
            return "Unknown", "🌍"
        flag = "".join([chr(127397 + ord(c)) for c in region])
        return country_obj.name, flag
    except:
        return "Unknown", "🌍"

def format_message(record, personal=False):
    number = record.get("num") or "Unknown"
    sender = record.get("cli") or "Unknown"
    message = record.get("message") or ""
    dt = record.get("dt") or ""
    country = record.get("country") or "Unknown"
    flag = country_to_flag(country)
    otp = extract_otp(message)
    otp_line = f"<b>OTP:</b> <code>{html.escape(otp)}</code>\n" if otp else ""

    if personal:
        formatted = (
            f"{flag} New {country} {sender} OTP Recived \n\n"
            f"<blockquote>🕰 <b>Time:</b> <b>{html.escape(str(dt))}</b></blockquote>\n"
            f"<blockquote>🌍 <b>Country:</b> <b>{html.escape(country)} {flag}</b></blockquote>\n"
            f"<blockquote>📱 <b>Service:</b> <b>{html.escape(sender)}</b></blockquote>\n"
            f"<blockquote>📞 <b>Number:</b> <b>{html.escape(mask_number(number))}</b></blockquote>\n"
            f"<blockquote>{otp_line}</blockquote>"
            f"<blockquote>✉️ <b>Full Message:</b></blockquote>\n"
            f"<blockquote><code>{html.escape(message)}</code></blockquote>\n\n"
            f"<blockquote>💥 <b>Powered By: @VASUHUB </b></blockquote>\n"
        )
    else:
        formatted = (
            f"{flag} New {country} {sender} OTP Recived \n\n"
            f"<blockquote>🕰 <b>Time:</b> <b>{html.escape(str(dt))}</b></blockquote>\n"
            f"<blockquote>🌍 <b>Country:</b> <b>{html.escape(country)} {flag}</b></blockquote>\n            "
            f"<blockquote>📱 <b>Service:</b> <b>{html.escape(sender)}</b></blockquote>\n"
            f"<blockquote>📞 <b>Number:</b> <b>{html.escape(mask_number(number))}</b></blockquote>\n"
            f"<blockquote>{otp_line}</blockquote>"
            f"<blockquote>✉️ <b>Full Message:</b></blockquote>\n"
            f"<blockquote><code>{html.escape(message)}</code></blockquote>\n\n"
        )
    return formatted, number

def broadcast_message(message):
    text = message.text
    success_count = 0
    fail_count = 0

    for user_id in active_users:
        try:
            bot.send_message(user_id, f"📢 Broadcast Message:\n\n{text}")
            success_count += 1
        except:
            fail_count += 1
        time.sleep(0.1)

    bot.reply_to(message, f"✅ Broadcast sent!\nSuccess: {success_count}\nFailed: {fail_count}")

def main_loop():
    logger.info("🚀 OTP Monitor Started...")
    if not login():
        logger.error("❌ Initial login failed. Exiting OTP loop.")
        return

    while True:
        try:
            res = session.get(XHR_URL, headers=AJAX_HEADERS, timeout=15)
            data = res.json()
            otps = data.get("aaData", [])
            otps = [row for row in otps if isinstance(row[0], str) and ":" in row[0]]

            new_found = False
            with open("otp_logs.txt", "a", encoding="utf-8") as f:
                for row in otps:
                    time_ = row[0]
                    country = row[1].split("-")[0]
                    number = row[2]
                    sender = row[3]
                    message = row[5]

                    hash_id = hashlib.md5((number + time_ + message).encode()).hexdigest()
                    if hash_id in seen_messages:
                        continue
                    seen_messages.add(hash_id)
                    new_found = True
                    
                    log_formatted = (
                        f"📱 Number:      {number}\n"
                        f"🏷️ Sender ID:   {sender}\n"
                        f"💬 Message:     {message}\n"
                        f"{'-'*60}"
                    )
                    f.write(log_formatted + "\n")
                    logger.info(log_formatted)

                    record = {
                        "dt": time_,
                        "country": country,
                        "num": number,
                        "cli": sender,
                        "message": message
                    }

                                        # send public group message
                    msg_group, _ = format_message(record, personal=False)
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("📱 Channel", url=CHANNEL_LINK))
                    keyboard.add(types.InlineKeyboardButton("🚀 Panel", url=f"https://t.me/{DEVELOPER_ID.lstrip('@')}"))
                    message_queue.put((msg_group, OTP_GROUP_IDS, keyboard))

                    # send personal message if this number was assigned to a user
                    chat_id = user_numbers.get(number)
                    if chat_id:
                        msg_personal, _ = format_message(record, personal=True)
                        message_queue.put((msg_personal, [chat_id]))

                    # --- 🗑️ Auto Remove Used Number From Memory + File ---
                    try:
                        # Normalize keys/number formats to match file entries
                        country_key = str(country).strip()
                        num_key = str(number).lstrip("+").strip()

                        if country_key in numbers_by_country:
                            numbers_list = [n.lstrip("+").strip() for n in numbers_by_country.get(country_key, [])]
                            if num_key in numbers_list:
                                numbers_list.remove(num_key)
                                numbers_by_country[country_key] = numbers_list

                                # 1️⃣ Update the country’s .txt file
                                file_path = os.path.join(NUMBERS_DIR, f"{country_key}.txt")
                                with open(file_path, "w", encoding="utf-8") as wf:
                                    wf.write("\n".join(numbers_list))

                                # 2️⃣ Save JSON (bot_data.json)
                                save_data()

                                # 3️⃣ Remove from user mapping so no reuse
                                if num_key in user_numbers:
                                    del user_numbers[num_key]

                                # 4️⃣ Log usage history
                                with open("used_numbers.txt", "a", encoding="utf-8") as used:
                                    used.write(f"{datetime.now().isoformat()} | {country_key} | {num_key}\n")

                                # 5️⃣ Print progress in console
                                logger.info(f"🗑️ Number {num_key} removed from {country_key}. Remaining: {len(numbers_list)}")
                    except Exception as e:
                        logger.error(f"❌ Error while removing used number {number}: {e}")
                    
                    try:
                                    remaining = len(numbers_list)
                                    if remaining <= LOW_INVENTORY_THRESHOLD:
                                        last_alert = LAST_ALERTED.get(country_key, 0)
                                        # Alert again only if more than 1 hour has passed since last alert
                                        if (time.time() - last_alert) > 3600:
                                            alert_msg = (
                                                f"⚠️ *Low Numbers Alert*\n"
                                                f"🌍 Country: {country_key}\n"
                                                f"📞 Remaining: {remaining} numbers\n"
                                                f"📁 File: `numbers/{country_key}.txt`"
                                            )
                                            bot.send_message(
                                                ADMIN_ID,
                                                alert_msg,
                                                parse_mode="Markdown"
                                            )
                                            LAST_ALERTED[country_key] = time.time()
                                            logger.warning(f"⚠️ Low inventory alert sent for {country_key} ({remaining} left)")
                    except Exception as e:
                        logger.error(f"❌ Low inventory alert error: {e}")

            if not new_found:
                logger.info("⏳ No new OTPs.")
        except Exception as e:
            logger.error(f"❌ Error fetching OTPs: {e}")
            # attempt re-login on auth errors or if session expired
            try:
                if "401" in str(e) or ("Unauthorized" in str(e)) or (hasattr(res, "status_code") and res.status_code == 401):
                    logger.info("Attempting to re-login...")
                    if not login():
                        logger.error("❌ Re-login failed.")
            except Exception:
                pass

        time.sleep(1.2)

# ---------------- USER BOT FUNCTIONS ----------------
def send_random_number(chat_id, country=None, edit=False):
    if country is None:
        country = user_current_country.get(chat_id)
        if not country:
            bot.send_message(chat_id, "❌ No country selected.")
            return
    numbers = numbers_by_country.get(country, [])
    if not numbers:
        bot.send_message(chat_id, f"❌ No numbers for {country}.")
        return
    number = random.choice(numbers)
    user_current_country[chat_id] = country
    user_numbers[number] = chat_id

    text = f"📞 Number for *{country}*:\n`{number}`"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔄 Change Number", callback_data="change_number"))
    markup.add(types.InlineKeyboardButton("🌍 Change Country", callback_data="change_country"))
    markup.add(types.InlineKeyboardButton("🔗 OTP GROUP", url="https://t.me/+FhMz9dj1RqIxOTc1"))

    if chat_id in user_messages:
        bot.edit_message_text(text, chat_id, user_messages[chat_id].message_id, reply_markup=markup, parse_mode="Markdown")
    else:
        msg = bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")
        user_messages[chat_id] = msg

active_users = set()
REQUIRED_CHANNELS = ["@freeotpss"]

@bot.message_handler(commands=["start"])
def start(message):
    chat_id = message.chat.id

    if message.from_user.id == ADMIN_ID:
        bot.send_message(chat_id, "👋 Welcome Admin!\nUse /adminhelp for commands.")
        return

    active_users.add(chat_id)

    not_joined = []
    for channel in REQUIRED_CHANNELS:
        try:
            member = bot.get_chat_member(channel, chat_id)
            if member.status not in ["member", "creator", "administrator"]:
                not_joined.append(channel)
        except:
            not_joined.append(channel)

    if not_joined:
        markup = types.InlineKeyboardMarkup()
        for ch in not_joined:
            markup.add(types.InlineKeyboardButton(f"🚀 Join {ch}", url=f"https://t.me/{ch[1:]}"))
        bot.send_message(chat_id, "❌ You must join all required channels to use the bot.", reply_markup=markup)
        return

    if not numbers_by_country:
        bot.send_message(chat_id, "❌ No countries available yet.")
        return

    markup = types.InlineKeyboardMarkup()
    for country in sorted(numbers_by_country.keys()):
        count = len(numbers_by_country.get(country, []))
        flag = country_to_flag(country)
        btn_text = f"{flag} {country} ({count} numbers)"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"user_select_{country}"))
    msg = bot.send_message(chat_id, "🌍 Choose a country:", reply_markup=markup)
    user_messages[chat_id] = msg

@bot.message_handler(commands=["broadcast"])
def broadcast_start(message):
    if message.from_user.id != ADMIN_ID:
        return bot.reply_to(message, "❌ You are not the admin.")

    msg = bot.reply_to(message, "✉️ Send the message you want to broadcast to all users:")
    bot.register_next_step_handler(msg, broadcast_message)

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    if call.from_user.id != ADMIN_ID:
        active_users.add(chat_id)
    data_str = call.data
    if data_str.startswith("user_select_"):
        country = data_str[12:]
        user_current_country[chat_id] = country
        send_random_number(chat_id, country, edit=True)
    elif data_str == "change_number":
        send_random_number(chat_id, user_current_country.get(chat_id), edit=True)
    elif data_str == "change_country":
        markup = types.InlineKeyboardMarkup()
        for country in sorted(numbers_by_country.keys()):
            markup.add(types.InlineKeyboardButton(country, callback_data=f"user_select_{country}"))
        if chat_id in user_messages:
            bot.edit_message_text("🌍 Select a country:", chat_id, user_messages[chat_id].message_id, reply_markup=markup)

@bot.message_handler(commands=["usercount"])
def user_count(message):
    if message.from_user.id != ADMIN_ID:
        return bot.reply_to(message, "❌ You are not the admin.")
    count = len(active_users)
    bot.reply_to(message, f"👥 Total users using the bot: {count}")

# ---------------- ADMIN COMMANDS ----------------
@bot.message_handler(commands=["setcountry"])
def set_country(message):
    global current_country
    if message.from_user.id != ADMIN_ID:
        return bot.reply_to(message, "❌ You are not the admin.")
    if len(message.text.split()) > 1:
        current_country = " ".join(message.text.split()[1:]).strip()
        if current_country not in numbers_by_country:
            numbers_by_country[current_country] = []
        save_data()
        bot.reply_to(message, f"✅ Current country set to: {current_country}")
    else:
        bot.reply_to(message, "Usage: /setcountry <country name>")

@bot.message_handler(commands=["remaining"])
def remaining_numbers(message):
    if message.from_user.id != ADMIN_ID:
        return bot.reply_to(message, "❌ You are not the admin.")
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return bot.reply_to(message, "Usage: /remaining <country>")
    country = parts[1].strip()
    if country not in numbers_by_country:
        return bot.reply_to(message, f"❌ Country '{country}' not found.")
    count = len(numbers_by_country[country])
    bot.reply_to(message, f"📊 {country} → {count} numbers left.")

@bot.message_handler(commands=["deletecountry"])
def delete_country(message):
    global current_country
    if message.from_user.id != ADMIN_ID:
        return bot.reply_to(message, "❌ You are not the admin.")
    if len(message.text.split()) > 1:
        country = " ".join(message.text.split()[1:]).strip()
        if country in numbers_by_country:
            del numbers_by_country[country]
            if current_country == country:
                current_country = None
            file_path = os.path.join(NUMBERS_DIR, f"{country}.txt")
            if os.path.exists(file_path):
                os.remove(file_path)
            save_data()
            bot.reply_to(message, f"✅ Deleted country: {country}")
        else:
            bot.reply_to(message, f"❌ Country '{country}' not found.")
    else:
        bot.reply_to(message, "Usage: /deletecountry <country name>")

@bot.message_handler(commands=["cleannumbers"])
def clear_numbers(message):
    if message.from_user.id != ADMIN_ID:
        return bot.reply_to(message, "❌ You are not the admin.")
    if len(message.text.split()) > 1:
        country = " ".join(message.text.split()[1:]).strip()
        if country in numbers_by_country:
            numbers_by_country[country] = []
            file_path = os.path.join(NUMBERS_DIR, f"{country}.txt")
            open(file_path, "w").close()
            save_data()
            bot.reply_to(message, f"✅ Cleared numbers for {country}.")
        else:
            bot.reply_to(message, f"❌ Country '{country}' not found.")
    else:
        bot.reply_to(message, "Usage: /cleannumbers <country name>")

@bot.message_handler(commands=["listcountries"])
def list_countries(message):
    if message.from_user.id != ADMIN_ID:
        return bot.reply_to(message, "❌ You are not the admin.")
    if not numbers_by_country:
        return bot.reply_to(message, "❌ No countries available.")
    text = "🌍 Available countries and number counts:\n"
    for country, nums in sorted(numbers_by_country.items()):
        text += f"- {country}: {len(nums)} numbers\n"
    bot.reply_to(message, text)

@bot.message_handler(commands=["adminhelp"])
def admin_help(message):
    if message.from_user.id != ADMIN_ID:
        return bot.reply_to(message, "❌ You are not the admin.")
    help_text = """ 🔧 *Admin Commands*: - /setcountry <country>: Set current country for uploading `.txt`. - Upload `.txt`: Add numbers (bot will ask country). - /deletecountry <country>: Delete a country and its numbers. - /cleannumbers <country>: Clear numbers for a country (keep country). - /listcountries: View all countries and number counts. - /adminhelp: Show this help. """
    bot.reply_to(message, help_text, parse_mode="Markdown")

# ---------------- START BOTH ----------------
def run_bot():
    bot.infinity_polling()

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    threading.Thread(target=run_bot).start()
    threading.Thread(target=sender_worker, daemon=True).start()
    threading.Thread(target=main_loop, daemon=True).start()
