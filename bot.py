# ================== GAMING BOT ==================
# Ek hi file mein poora bot — copy, paste, run!

import asyncio
import aiohttp
import time
import json
import random
import logging
import sqlite3
import os
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ================== CONFIG ==================
BOT_TOKEN = "8880531578:AAFH6S2UlEpTaF2B20gXtPyuAyzSk6vxOes"
ADMIN_IDS = [8335116442]  # Apna ID daalo (real Telegram user ID)
BOT_NAME = "🎮 Gaming Empire"
# =============================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ================== DATABASE ==================
DB_PATH = "gaming_bot.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        coins INTEGER DEFAULT 1000,
        bank INTEGER DEFAULT 0,
        bank_max INTEGER DEFAULT 5000,
        xp INTEGER DEFAULT 0,
        level INTEGER DEFAULT 1,
        total_xp INTEGER DEFAULT 0,
        games_played INTEGER DEFAULT 0,
        games_won INTEGER DEFAULT 0,
        games_lost INTEGER DEFAULT 0,
        coins_earned INTEGER DEFAULT 0,
        coins_lost INTEGER DEFAULT 0,
        last_daily TEXT,
        daily_streak INTEGER DEFAULT 0,
        items TEXT DEFAULT '[]',
        is_banned INTEGER DEFAULT 0,
        joined_at TEXT,
        last_active TEXT,
        referred_by INTEGER,
        referral_count INTEGER DEFAULT 0
    )''')
    
    # Shop table
    c.execute('''CREATE TABLE IF NOT EXISTS shop (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        description TEXT,
        price INTEGER,
        category TEXT,
        emoji TEXT,
        stock INTEGER DEFAULT -1,
        is_active INTEGER DEFAULT 1
    )''')
    
    # Active games table
    c.execute('''CREATE TABLE IF NOT EXISTS active_games (
        game_id TEXT PRIMARY KEY,
        user_id INTEGER,
        game_type TEXT,
        data TEXT,
        created_at TEXT
    )''')
    
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()
    conn.close()
    return user

def create_user(user_id, username=None, first_name=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    c.execute('''INSERT OR IGNORE INTO users 
        (user_id, username, first_name, joined_at, last_active) 
        VALUES (?, ?, ?, ?, ?)''', 
        (user_id, username, first_name, now, now))
    conn.commit()
    conn.close()

def update_user(user_id, **kwargs):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for key, value in kwargs.items():
        c.execute(f"UPDATE users SET {key} = ? WHERE user_id = ?", (value, user_id))
    conn.commit()
    conn.close()

def get_or_create_user(user_id, username=None, first_name=None):
    user = get_user(user_id)
    if not user:
        create_user(user_id, username, first_name)
        user = get_user(user_id)
    else:
        update_user(user_id, last_active=datetime.utcnow().isoformat())
    return user

def get_top_users(category="coins", limit=10):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    order_map = {
        "coins": "coins DESC",
        "level": "level DESC, xp DESC",
        "games": "games_won DESC",
        "net_worth": "(coins + bank) DESC"
    }
    order = order_map.get(category, "coins DESC")
    
    c.execute(f"SELECT user_id, first_name, username, coins, level, games_won FROM users WHERE is_banned = 0 ORDER BY {order} LIMIT ?", (limit,))
    users = c.fetchall()
    conn.close()
    return users

def get_user_dict(user_id):
    user = get_user(user_id)
    if not user:
        return None
    
    columns = ["user_id", "username", "first_name", "coins", "bank", "bank_max", "xp", "level", 
               "total_xp", "games_played", "games_won", "games_lost", "coins_earned", "coins_lost",
               "last_daily", "daily_streak", "items", "is_banned", "joined_at", "last_active",
               "referred_by", "referral_count"]
    
    return dict(zip(columns, user))

# ================== GAMES DATA ==================
TRIVIA_QUESTIONS = [
    {"q": "What is the capital of India?", "a": ["New Delhi", "Mumbai", "Kolkata", "Chennai"], "c": 0},
    {"q": "Who developed the Python programming language?", "a": ["Guido van Rossum", "Dennis Ritchie", "James Gosling", "Bjarne Stroustrup"], "c": 0},
    {"q": "What is 7 × 8 + 4?", "a": ["60", "56", "52", "48"], "c": 0},
    {"q": "Which planet is known as Red Planet?", "a": ["Mars", "Venus", "Jupiter", "Saturn"], "c": 0},
    {"q": "What is the chemical symbol for Gold?", "a": ["Au", "Ag", "Cu", "Fe"], "c": 0},
    {"q": "Who wrote 'Ramayana'?", "a": ["Valmiki", "Ved Vyasa", "Tulsidas", "Kalidasa"], "c": 0},
    {"q": "Which is the largest ocean in the world?", "a": ["Pacific", "Atlantic", "Indian", "Arctic"], "c": 0},
    {"q": "What is the square root of 144?", "a": ["12", "14", "16", "11"], "c": 0},
    {"q": "Which Indian sportsperson won Olympic gold in 2021?", "a": ["Neeraj Chopra", "PV Sindhu", "Mirabai Chanu", "Bajrang Punia"], "c": 0},
    {"q": "What does CPU stand for?", "a": ["Central Processing Unit", "Computer Personal Unit", "Central Program Unit", "Core Processing Unit"], "c": 0},
]

RPS_CHOICES = ["🪨 Rock", "📄 Paper", "✂️ Scissors"]

# ================== HELPER FUNCTIONS ==================
async def add_xp(user_id, xp_amount, context):
    user = get_user_dict(user_id)
    if not user:
        return
    
    new_xp = user["xp"] + xp_amount
    new_total_xp = user["total_xp"] + xp_amount
    new_level = user["level"]
    
    # Level up check
    xp_needed = int(new_level * 100 * 1.5)
    leveled_up = False
    while new_xp >= xp_needed:
        new_xp -= xp_needed
        new_level += 1
        xp_needed = int(new_level * 100 * 1.5)
        leveled_up = True
    
    update_user(user_id, xp=new_xp, level=new_level, total_xp=new_total_xp)
    
    if leveled_up:
        # Level up reward
        reward = new_level * 100
        update_user(user_id, coins=get_user_dict(user_id)["coins"] + reward)
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎉 **LEVEL UP!**\nYou're now **Level {new_level}**!\n💰 +{reward} coins reward!"
            )
        except:
            pass

def add_coins(user_id, amount):
    user = get_user_dict(user_id)
    if not user:
        return False
    new_coins = user["coins"] + amount
    new_earned = user["coins_earned"] + (amount if amount > 0 else 0)
    new_lost = user["coins_lost"] + (abs(amount) if amount < 0 else 0)
    update_user(user_id, coins=new_coins, coins_earned=new_earned, coins_lost=new_lost)
    return True

def deduct_coins(user_id, amount):
    return add_coins(user_id, -amount)

async def send_main_menu(update_or_context, user_id=None, context=None, edit=False):
    user = get_user_dict(user_id or update_or_context.effective_user.id)
    if not user:
        return
    
    name = user["first_name"] or user["username"] or "Player"
    level = user["level"]
    coins = user["coins"]
    bank = user["bank"]
    games = user["games_played"]
    wins = user["games_won"]
    
    text = (
        f"🎮 **Welcome to {BOT_NAME}!**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👤 **{name}** | Lv.{level}\n"
        f"💰 `{coins}` | 🏦 `{bank}`\n"
        f"📊 Games: {games} | Wins: {wins}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"Choose a game below!"
    )
    
    keyboard = [
        [InlineKeyboardButton("🎯 Guess Number", callback_data="game_guess"),
         InlineKeyboardButton("🪨 RPS", callback_data="game_rps")],
        [InlineKeyboardButton("🎲 Dice Roll", callback_data="game_dice"),
         InlineKeyboardButton("🪙 Coin Flip", callback_data="game_coin")],
        [InlineKeyboardButton("🎰 Slots", callback_data="game_slots"),
         InlineKeyboardButton("💡 Trivia", callback_data="game_trivia")],
        [InlineKeyboardButton("💰 Economy", callback_data="menu_economy"),
         InlineKeyboardButton("🏆 Leaderboard", callback_data="menu_leaderboard")],
        [InlineKeyboardButton("📊 Profile", callback_data="menu_profile"),
         InlineKeyboardButton("🛒 Shop", callback_data="menu_shop")],
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if edit and hasattr(update_or_context, 'message'):
        await update_or_context.message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    elif edit and hasattr(update_or_context, 'edit_message_text'):
        await update_or_context.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update_or_context.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

# ================== COMMANDS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username
    first_name = user.first_name
    
    # Check referral
    args = context.args
    if args and args[0].startswith("ref_"):
        try:
            ref_id = int(args[0].replace("ref_", ""))
            if ref_id != user_id:
                get_or_create_user(user_id, username, first_name)
                update_user(ref_id, referral_count=get_user_dict(ref_id)["referral_count"] + 1)
                # Reward referrer
                add_coins(ref_id, 200)
        except:
            pass
    
    get_or_create_user(user_id, username, first_name)
    await send_main_menu(update, user_id)

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user_dict(user_id)
    if not user:
        await update.message.reply_text("Please /start first!")
        return
    
    name = user["first_name"] or user["username"] or "Player"
    level = user["level"]
    xp = user["xp"]
    xp_needed = int(level * 100 * 1.5)
    coins = user["coins"]
    bank = user["bank"]
    net_worth = coins + bank
    games = user["games_played"]
    wins = user["games_won"]
    losses = user["games_lost"]
    win_rate = round((wins / games * 100) if games > 0 else 0, 2)
    earned = user["coins_earned"]
    lost = user["coins_lost"]
    streak = user["daily_streak"]
    
    text = (
        f"📊 **{name}'s Profile**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👤 **Level:** {level}\n"
        f"⭐ **XP:** {xp}/{xp_needed}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💰 **Coins:** {coins:,}\n"
        f"🏦 **Bank:** {bank:,}\n"
        f"💎 **Net Worth:** {net_worth:,}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🎮 **Games:** {games}\n"
        f"✅ **Wins:** {wins}\n"
        f"❌ **Losses:** {losses}\n"
        f"📈 **Win Rate:** {win_rate}%\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🪙 **Earned:** {earned:,}\n"
        f"💸 **Lost:** {lost:,}\n"
        f"🔥 **Streak:** {streak} days\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🆔 ID: `{user_id}`"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="menu_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user_dict(user_id)
    if not user:
        await update.message.reply_text("Please /start first!")
        return
    
    now = datetime.utcnow()
    last_daily = None
    if user["last_daily"]:
        last_daily = datetime.fromisoformat(user["last_daily"])
    
    if last_daily and (now - last_daily).total_seconds() < 86400:
        next_claim = last_daily + timedelta(days=1)
        remaining = next_claim - now
        hours, remainder = divmod(int(remaining.total_seconds()), 3600)
        mins, secs = divmod(remainder, 60)
        await update.message.reply_text(f"⚠️ Already claimed daily! Next in **{hours}h {mins}m**")
        return
    
    streak = user["daily_streak"]
    if last_daily and (now - last_daily).total_seconds() < 172800:  # 48 hours = streak continues
        streak += 1
    else:
        streak = 1
    
    base_reward = 500
    streak_bonus = min(streak * 50, 500)  # Max +500 for 10 day streak
    level_bonus = user["level"] * 10
    total_reward = base_reward + streak_bonus + level_bonus
    
    update_user(user_id, last_daily=now.isoformat(), daily_streak=streak)
    add_coins(user_id, total_reward)
    await add_xp(user_id, 25, context)
    
    text = (
        f"✅ **Daily Reward Claimed!**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💰 **Base:** +{base_reward}\n"
        f"🔥 **Streak x{streak}:** +{streak_bonus}\n"
        f"📊 **Level Bonus:** +{level_bonus}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🎁 **Total:** +{total_reward} coins\n"
        f"⭐ **XP:** +25"
    )
    
    await update.message.reply_text(text)

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    category = context.args[0] if context.args else "coins"
    
    cat_names = {"coins": "💰 Richest", "level": "⭐ Highest Level", "games": "🎮 Most Wins", "net_worth": "💎 Net Worth"}
    cat_name = cat_names.get(category, "💰 Richest")
    
    users = get_top_users(category, 15)
    
    if not users:
        await update.message.reply_text("No users yet!")
        return
    
    text = f"🏆 **{cat_name} Leaderboard**\n━━━━━━━━━━━━━━━\n"
    
    medals = ["🥇", "🥈", "🥉"]
    for i, user in enumerate(users):
        medal = medals[i] if i < 3 else f"{i+1}."
        name = user[1] or user[2] or f"User{user[0]}"
        value = f"💰 {user[3]:,}" if category == "coins" else f"⭐ Lv.{user[4]}" if category == "level" else f"🎮 {user[5]} wins"
        text += f"{medal} **{name}** — {value}\n"
    
    keyboard = [
        [
            InlineKeyboardButton("💰 Coins", callback_data="lb_coins"),
            InlineKeyboardButton("⭐ Level", callback_data="lb_level"),
            InlineKeyboardButton("🎮 Wins", callback_data="lb_games"),
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="menu_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    
    if len(args) < 2:
        await update.message.reply_text("Usage: `/transfer @username 100` or `/transfer 123456789 100`")
        return
    
    try:
        amount = int(args[-1])
        target = args[0]
        
        if target.startswith("@"):
            target = target[1:]
            # Find user by username
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT user_id FROM users WHERE username = ?", (target,))
            result = c.fetchone()
            conn.close()
            if not result:
                await update.message.reply_text("User not found!")
                return
            target_id = result[0]
        else:
            target_id = int(target)
        
        if target_id == user_id:
            await update.message.reply_text("Can't transfer to yourself!")
            return
        
        if amount < 10:
            await update.message.reply_text("Minimum transfer is 10 coins")
            return
        
        user = get_user_dict(user_id)
        if user["coins"] < amount:
            await update.message.reply_text(f"Insufficient coins! You have {user['coins']:,}")
            return
        
        deduct_coins(user_id, amount)
        add_coins(target_id, amount)
        
        await update.message.reply_text(f"✅ Transferred **{amount:,}** coins to `{target_id}`")
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"💰 Received **{amount:,}** coins from `{user_id}`"
            )
        except:
            pass
    except:
        await update.message.reply_text("Invalid format! Use: `/transfer @username 100`")

async def slots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user_dict(user_id)
    if not user:
        await update.message.reply_text("Please /start first!")
        return
    
    args = context.args
    bet = 100
    if args:
        try:
            bet = int(args[0])
            if bet < 10:
                await update.message.reply_text("Minimum bet is 10 coins")
                return
            if bet > 10000:
                await update.message.reply_text("Maximum bet is 10,000 coins")
                return
        except:
            await update.message.reply_text("Invalid bet amount!")
            return
    
    if user["coins"] < bet:
        await update.message.reply_text(f"Insufficient coins! You have {user['coins']:,}")
        return
    
    symbols = ["🍒", "🍋", "🍊", "🍇", "🔔", "💎", "7️⃣", "⭐", "🎰"]
    
    # Spin
    result = [random.choice(symbols) for _ in range(3)]
    
    # Check wins
    multiplier = 0
    if result[0] == result[1] == result[2]:
        if result[0] == "7️⃣":
            multiplier = 10  # Jackpot!
        elif result[0] == "💎":
            multiplier = 8
        elif result[0] == "🔔":
            multiplier = 6
        elif result[0] == "⭐":
            multiplier = 5
        elif result[0] == "🎰":
            multiplier = 4
        else:
            multiplier = 3
    elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
        multiplier = 2
    else:
        multiplier = 0
    
    winnings = bet * multiplier
    net = winnings - bet
    
    deduct_coins(user_id, bet)
    if winnings > 0:
        add_coins(user_id, winnings)
    
    update_user(user_id, games_played=user["games_played"] + 1)
    if winnings > bet:
        update_user(user_id, games_won=user["games_won"] + 1)
    else:
        update_user(user_id, games_lost=user["games_lost"] + 1)
    
    await add_xp(user_id, 10, context)
    
    result_text = " | ".join(result)
    status = "😢 Lost" if net <= 0 else "🎉 Won!"
    
    text = (
        f"🎰 **SLOTS**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"`  {result_text}  `\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💰 **Bet:** {bet:,}\n"
        f"💵 **Won:** {winnings:,}\n"
        f"📊 **Net:** {'+' if net > 0 else ''}{net:,}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"**{status}**"
    )
    
    keyboard = [
        [InlineKeyboardButton("🎰 Play Again", callback_data="game_slots"),
         InlineKeyboardButton("🔙 Menu", callback_data="menu_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

# ================== CALLBACK HANDLER ==================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    
    user = get_user_dict(user_id)
    if not user:
        get_or_create_user(user_id, query.from_user.username, query.from_user.first_name)
        user = get_user_dict(user_id)
    
    # ====== GAME CALLBACKS ======
    if data == "game_guess":
        number = random.randint(1, 10)
        # Store game
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        game_data = json.dumps({"number": number, "attempts": 0, "max_attempts
