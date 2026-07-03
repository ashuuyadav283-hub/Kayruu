import asyncio
import json
import logging
import math
import os
import random
import re
import sqlite3
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Optional

import httpx
from telegram import (
    ChatMemberAdministrator,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    ChatPermissions,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# ─── CONFIG ────────────────────────────────────────────────────────────────────

BOT_TOKEN = os.getenv("8880531578:AAFH6S2UlEpTaF2B20gXtPyuAyzSk6vxOes")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "8335116442").split(",")))
OWNER_ID = int(os.getenv("OWNER_ID", "8335116442"))
DB_PATH = "kazumi.db"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── DATABASE SETUP ────────────────────────────────────────────────────────────

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.row_factory = sqlite3.Row
c = conn.cursor()

c.executescript("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    coins INTEGER DEFAULT 0,
    bank INTEGER DEFAULT 0,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    karma INTEGER DEFAULT 0,
    married_to INTEGER DEFAULT NULL,
    streak INTEGER DEFAULT 0,
    last_daily TEXT DEFAULT NULL,
    afk_reason TEXT DEFAULT NULL,
    afk_since TEXT DEFAULT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS groups (
    group_id INTEGER PRIMARY KEY,
    group_name TEXT,
    welcome_enabled INTEGER DEFAULT 1,
    welcome_image TEXT DEFAULT NULL,
    chatbot_enabled INTEGER DEFAULT 0,
    chatbot_model TEXT DEFAULT 'claude',
    start_image TEXT DEFAULT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS loans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lender_id INTEGER,
    borrower_id INTEGER,
    amount INTEGER,
    repaid INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposer_id INTEGER,
    target_id INTEGER,
    status TEXT DEFAULT 'pending',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    key TEXT,
    value TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS shop_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    type TEXT,
    price INTEGER
);

CREATE TABLE IF NOT EXISTS inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    item_id INTEGER,
    quantity INTEGER DEFAULT 1,
    FOREIGN KEY(item_id) REFERENCES shop_items(id)
);

CREATE TABLE IF NOT EXISTS achievements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    badge TEXT,
    unlocked_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS waifu_gacha (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    waifu_name TEXT,
    rarity TEXT,
    pulled_at TEXT DEFAULT CURRENT_TIMESTAMP
);
""")
conn.commit()

# ─── HELPER FUNCTIONS ──────────────────────────────────────────────────────────

def get_user(user_id: int) -> dict:
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if row is None:
        c.execute(
            "INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
            (user_id, "", ""),
        )
        conn.commit()
        return {"user_id": user_id, "coins": 0, "bank": 0, "xp": 0, "level": 1, "karma": 0,
                "married_to": None, "streak": 0, "afk_reason": None, "afk_since": None}
    return dict(row)

def get_group(group_id: int) -> dict:
    c.execute("SELECT * FROM groups WHERE group_id = ?", (group_id,))
    row = c.fetchone()
    if row is None:
        return {"group_id": group_id, "welcome_enabled": 1, "chatbot_enabled": 0, "chatbot_model": "claude"}
    return dict(row)

def add_xp(user_id: int, amount: int = 10) -> bool:
    user = get_user(user_id)
    new_xp = user["xp"] + amount
    new_level = int(math.sqrt(new_xp / 100)) + 1
    c.execute("UPDATE users SET xp = ?, level = ? WHERE user_id = ?", (new_xp, new_level, user_id))
    conn.commit()
    return new_level > user["level"]

def add_coins(user_id: int, amount: int):
    c.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()

def time_now() -> str:
    return datetime.now().isoformat()

async def is_group_admin(update: Update, user_id: int) -> bool:
    chat = update.effective_chat
    if chat.type == "private":
        return user_id in ADMIN_IDS
    try:
        member = await chat.get_member(user_id)
        return member.status in ("administrator", "creator")
    except:
        return False

# ─── AI CHATBOT ────────────────────────────────────────────────────────────────

async def ask_claude(prompt: str, system: str = "You are a helpful anime-themed assistant named Kazumi. Be cute and friendly.") -> str:
    if not ANTHROPIC_API_KEY:
        return "✨ AI is not configured yet. Please set ANTHROPIC_API_KEY."
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": "claude-sonnet-4-20250514", "max_tokens": 500, "system": system, "messages": [{"role": "user", "content": prompt}]},
        )
        data = resp.json()
        return data["content"][0]["text"]

async def ask_openai(prompt: str, system: str = "You are a helpful anime-themed assistant named Kazumi.") -> str:
    if not OPENAI_API_KEY:
        return "✨ AI is not configured yet. Please set OPENAI_API_KEY."
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json={"model": "gpt-4o", "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]},
        )
        data = resp.json()
        return data["choices"][0]["message"]["content"]

async def ai_chat(prompt: str, model: str = "claude") -> str:
    if model == "openai":
        return await ask_openai(prompt)
    return await ask_claude(prompt)

# ─── IMAGE GENERATION ──────────────────────────────────────────────────────────

async def generate_anime(prompt: str) -> Optional[str]:
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.prodia.com/v1/sd/generate",
                headers={"X-Prodia-Key": os.getenv("PRODIA_KEY", "")},
                json={"model": "anything-v5.safetensors", "prompt": f"anime style, {prompt}, high quality, cute",
                      "negative_prompt": "bad anatomy, ugly, deformed", "steps": 30, "cfg_scale": 7},
            )
            data = resp.json()
            return data.get("imageUrl")
    except Exception as e:
        logger.error(f"Image gen error: {e}")
        return None

# ─── TEXT-TO-SPEECH ────────────────────────────────────────────────────────────

async def anime_tts(text: str) -> Optional[str]:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.voicerss.org/",
                params={"key": os.getenv("VOICERSS_KEY", ""), "hl": "ja-jp", "src": text[:200], "f": "mp3"},
            )
            if resp.status_code == 200:
                fname = f"tts_{int(time.time())}.mp3"
                with open(fname, "wb") as f:
                    f.write(resp.content)
                return fname
    except Exception as e:
        logger.error(f"TTS error: {e}")
    return None

# ─── COMMAND HANDLERS ──────────────────────────────────────────────────────────

# ── SETTINGS ──
async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if not await is_group_admin(update, user.id):
        await update.message.reply_text("❌ This command is for admins only.")
        return
    gs = get_group(chat.id)
    text = (
        f"⚙️ **{chat.title} — Settings**\n\n"
        f"👋 Welcome: `{'ON' if gs['welcome_enabled'] else 'OFF'}`\n"
        f"🤖 AI Chatbot: `{'ON' if gs['chatbot_enabled'] else 'OFF'}` ({gs.get('chatbot_model','claude')})\n\n"
        f"Commands:\n"
        f"`/welcome on/off` — Toggle welcome messages\n"
        f"`/chatbot` — Configure AI settings\n"
        f"`/setstart` — Update start image (owner only)"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def welcome_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if not await is_group_admin(update, user.id):
        return
    args = context.args
    if not args or args[0].lower() not in ("on", "off"):
        await update.message.reply_text("Usage: `/welcome on` or `/welcome off`", parse_mode=ParseMode.MARKDOWN)
        return
    enabled = 1 if args[0].lower() == "on" else 0
    c.execute("UPDATE groups SET welcome_enabled = ? WHERE group_id = ?", (enabled, chat.id))
    conn.commit()
    await update.message.reply_text(f"👋 Welcome messages are now **{'ON' if enabled else 'OFF'}**.", parse_mode=ParseMode.MARKDOWN)

async def setstart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Only the bot owner can use this.")
        return
    if not update.message.reply_to_message or not update.message.reply_to_message.photo:
        await update.message.reply_text("Reply to an image with `/setstart` to set it as the start image.", parse_mode=ParseMode.MARKDOWN)
        return
    photo = update.message.reply_to_message.photo[-1]
    file = await photo.get_file()
    url = file.file_path
    chat = update.effective_chat
    c.execute("UPDATE groups SET start_image = ? WHERE group_id = ?", (url, chat.id))
    conn.commit()
    await update.message.reply_text("✅ Start image updated!")

# ── CHATBOT ──
async def chatbot_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if not await is_group_admin(update, user.id):
        return
    args = context.args
    if not args:
        gs = get_group(chat.id)
        await update.message.reply_text(
            f"🤖 **AI Chatbot Settings**\n\n"
            f"Currently: `{'ON' if gs['chatbot_enabled'] else 'OFF'}` — Model: `{gs.get('chatbot_model','claude')}`\n\n"
            f"Usage:\n`/chatbot on` — Enable\n`/chatbot off` — Disable\n`/chatbot model claude` — Claude\n`/chatbot model openai` — GPT-4o",
            parse_mode=ParseMode.MARKDOWN)
        return
    if args[0].lower() == "on":
        c.execute("UPDATE groups SET chatbot_enabled = 1 WHERE group_id = ?", (chat.id,))
        conn.commit()
        await update.message.reply_text("🤖 AI chatbot enabled!")
    elif args[0].lower() == "off":
        c.execute("UPDATE groups SET chatbot_enabled = 0 WHERE group_id = ?", (chat.id,))
        conn.commit()
        await update.message.reply_text("🤖 AI chatbot disabled!")
    elif args[0].lower() == "model" and len(args) > 1:
        model = args[1].lower()
        if model in ("claude", "openai"):
            c.execute("UPDATE groups SET chatbot_model = ? WHERE group_id = ?", (model, chat.id))
            conn.commit()
            await update.message.reply_text(f"✅ Model set to `{model}`.", parse_mode=ParseMode.MARKDOWN)

# ── DRAW & SPEAK ──
async def draw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text("🎨 Usage: `/draw cute cat girl with flowers`", parse_mode=ParseMode.MARKDOWN)
        return
    msg = await update.message.reply_text("🎨 Drawing... please wait~")
    image_url = await generate_anime(prompt)
    if image_url:
        await msg.delete()
        await update.message.reply_photo(photo=image_url, caption=f"🎨 `{prompt}`")
    else:
        await msg.edit_text("❌ Failed to generate image. Is the API configured?")

async def speak(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args) or (update.message.reply_to_message.text if update.message.reply_to_message else "")
    if not text:
        await update.message.reply_text("🔊 Usage: `/speak Hello there!`", parse_mode=ParseMode.MARKDOWN)
        return
    msg = await update.message.reply_text("🔊 Generating voice...")
    audio_path = await anime_tts(text)
    if audio_path:
        with open(audio_path, "rb") as f:
            await update.message.reply_audio(audio=f, title="Kazumi TTS", performer="Kazumi")
        os.remove(audio_path)
        await msg.delete()
    else:
        await msg.edit_text("❌ TTS failed. Is the API configured?")

# ── MEMORY ──
async def memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    if not args:
        c.execute("SELECT key, value FROM memories WHERE user_id = ?", (user_id,))
        rows = c.fetchall()
        if not rows:
            await update.message.reply_text("📝 No memories saved yet. Use `/remember key value` to save one.", parse_mode=ParseMode.MARKDOWN)
            return
        text = "📝 **Your Memories:**\n\n"
        for row in rows:
            text += f"• `{row['key']}`: {row['value'][:50]}\n"
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        return
    if len(args) >= 2:
        key = args[0]
        value = " ".join(args[1:])
        c.execute("INSERT OR REPLACE INTO memories (user_id, key, value) VALUES (?, ?, ?)", (user_id, key, value))
        conn.commit()
        await update.message.reply_text(f"✅ Saved `{key}` → {value[:50]}", parse_mode=ParseMode.MARKDOWN)

async def forgetme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    c.execute("DELETE FROM memories WHERE user_id = ?", (user_id,))
    conn.commit()
    await update.message.reply_text("🧹 All your memories have been erased. ✨")

# ── RIDDLE ──
RIDDLES = [
    {"q": "What has keys but can't open locks?", "a": "a piano"},
    {"q": "What has a head and a tail but no body?", "a": "a coin"},
    {"q": "What gets wetter the more it dries?", "a": "a towel"},
    {"q": "I speak without a mouth and hear without ears. What am I?", "a": "an echo"},
    {"q": "The more you take, the more you leave behind. What am I?", "a": "footsteps"},
]

async def riddle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    r = random.choice(RIDDLES)
    context.user_data["riddle_answer"] = r["a"]
    await update.message.reply_text(f"🧩 **Riddle:** {r['q']}\n\nReply with your answer!", parse_mode=ParseMode.MARKDOWN)

# ── SOCIAL & LOVE ──
async def propose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not update.message.reply_to_message:
        await update.message.reply_text("💍 Reply to someone's message to propose to them!")
        return
    target = update.message.reply_to_message.from_user
    if target.id == user.id:
        await update.message.reply_text("💍 You can't marry yourself!")
        return
    user_data = get_user(user.id)
    target_data = get_user(target.id)
    if user_data["married_to"]:
        await update.message.reply_text("💔 You're already married! Use `/divorce` first.", parse_mode=ParseMode.MARKDOWN)
        return
    if target_data["married_to"]:
        await update.message.reply_text(f"💔 {target.first_name} is already taken!")
        return
    c.execute("INSERT INTO proposals (proposer_id, target_id) VALUES (?, ?)", (user.id, target.id))
    conn.commit()
    keyboard = [[
        InlineKeyboardButton("💍 Accept", callback_data=f"marry_accept_{user.id}_{target.id}"),
        InlineKeyboardButton("💔 Decline", callback_data=f"marry_decline_{user.id}_{target.id}"),
    ]]
    await update.message.reply_text(
        f"💍 **{user.first_name}** is proposing to **{target.first_name}**!\n\n{target.first_name}, do you accept?",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def marry_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = get_user(user.id)
    if data["married_to"]:
        spouse = get_user(data["married_to"])
        await update.message.reply_text(f"💞 **{user.first_name}** is married to **{spouse.get('first_name','Unknown')}** 💞", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("💔 You're not married yet. Use `/propose` to find love!", parse_mode=ParseMode.MARKDOWN)

async def divorce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = get_user(user.id)
    if not data["married_to"]:
        await update.message.reply_text("💔 You're not married!")
        return
    c.execute("UPDATE users SET married_to = NULL WHERE user_id IN (?, ?)", (user.id, data["married_to"]))
    conn.commit()
    await update.message.reply_text("💔 You are now single. Take care~")

async def couple(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("💘 Reply to someone to see your compatibility!")
        return
    user = update.effective_user
    target = update.message.reply_to_message.from_user
    score = random.randint(50, 100)
    hearts = "💕" * (score // 20)
    await update.message.reply_text(
        f"💘 **Love Match**\n\n{user.first_name} × {target.first_name}\nCompatibility: **{score}%**\n{hearts}\n\n{'A match made in heaven! ✨' if score > 85 else 'There is potential! 🌸' if score > 65 else 'Maybe just friends... 🌿'}")

async def couples_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    c.execute("""
        SELECT u1.user_id, u1.first_name, u2.user_id, u2.first_name
        FROM users u1 JOIN users u2 ON u1.married_to = u2.user_id
        WHERE u1.user_id < u2.user_id
    """)
    rows = c.fetchall()
    if not rows:
        await update.message.reply_text("💞 No couples yet. Use `/propose` to start a romance!", parse_mode=ParseMode.MARKDOWN)
        return
    text = "💞 **Couples of the Day** 💞\n\n"
    for row in rows:
        text += f"• {row['first_name']} 💕 {row[3]}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# ── AFK ──
async def afk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    reason = " ".join(context.args) if context.args else "AFK"
    c.execute("UPDATE users SET afk_reason = ?, afk_since = ? WHERE user_id = ?", (reason, time_now(), user.id))
    conn.commit()
    await update.message.reply_text(f"💤 {user.first_name} is now AFK: {reason}")

async def brb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await afk(update, context)

# ── KARMA ──
async def karma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
    data = get_user(user.id)
    await update.message.reply_text(f"⭐ **{user.first_name}**'s Karma: `{data['karma']}`", pa# Economy
    app.add_handler(CommandHandler("gift", gift))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("bal", bal))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("weekly", weekly))
    app.add_handler(CommandHandler("claim", claim))
    app.add_handler(CommandHandler("shop", shop))
    app.add_handler(CommandHandler("buy", buy))
    app.add_handler(CommandHandler("give", give_coins))
    app.add_handler(CommandHandler("bet", bet))
    app.add_handler(CommandHandler("spin", spin))
    app.add_handler(CommandHandler("fortune", fortune))
    app.add_handler(CommandHandler("bank", bank))
    app.add_handler(CommandHandler("search", search_user))
    app.add_handler(CommandHandler("achievements", achievements))
    app.add_handler(CommandHandler("support", support_cmd))
    app.add_handler(CommandHandler("season", season_leaderboard))
    app.add_handler(CommandHandler("missions", missions))
    app.add_handler(CommandHandler("cooldowns", cooldowns))
    app.add_handler(CommandHandler("loan", loan))

    # Games
    app.add_handler(CommandHandler("rps", rps))
    app.add_handler(CommandHandler("diceduel", diceduel))
    app.add_handler(CommandHandler("war", war))
    app.add_handler(CommandHandler("trivia", trivia))
    app.add_handler(CommandHandler("taprace", taprace))

    # Callback
    app.add_handler(CallbackQueryHandler(button_callback))

    # Messages
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.add_error_handler(error_handler)

    logger.info("🤖 Kazumi bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
