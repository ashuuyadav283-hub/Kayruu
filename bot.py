# ================== GAMING BOT v3 — RANDOM WIN/LOSS + SHOP + WAR/HP SYSTEM ==================

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
BOT_TOKEN = "8880531578:AAFH6S2UlEpTaF2B20gXtPyuAyzSk6vxOes"  # ⚠️ REVOKE KAR DE BHAI! @BotFather se naya token le
BOT_NAME = "🎮 Kayru Empire"
# =============================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ================== DATABASE ==================
DB_PATH = "gaming_bot.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
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
        referral_count INTEGER DEFAULT 0,
        loan INTEGER DEFAULT 0,
        loan_date TEXT,
        hp INTEGER DEFAULT 100,
        max_hp INTEGER DEFAULT 100,
        armor INTEGER DEFAULT 0,
        war_wins INTEGER DEFAULT 0,
        war_losses INTEGER DEFAULT 0
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS gacha_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        rarity TEXT,
        emoji TEXT,
        description TEXT,
        rate REAL,
        hp_bonus INTEGER DEFAULT 0,
        armor_bonus INTEGER DEFAULT 0
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS shop (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        description TEXT,
        price INTEGER,
        category TEXT,
        emoji TEXT,
        hp_bonus INTEGER DEFAULT 0,
        armor_bonus INTEGER DEFAULT 0,
        stock INTEGER DEFAULT -1,
        is_active INTEGER DEFAULT 1
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS active_games (
        game_id TEXT PRIMARY KEY,
        user_id INTEGER,
        game_type TEXT,
        data TEXT,
        created_at TEXT
    )''')
    
    conn.commit()
    conn.close()

def init_shop():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM shop")
    count = c.fetchone()[0]
    if count == 0:
        shop_items = [
            ("Health Potion (Small)", "+25 HP", 100, "healing", "🧪", 25, 0, 100),
            ("Health Potion (Large)", "+60 HP", 250, "healing", "🧪", 60, 0, 50),
            ("Health Potion (Mega)", "+100 HP", 500, "healing", "💊", 100, 0, 20),
            ("Full Heal", "Full HP restore", 800, "healing", "❤️‍🩹", 999, 0, 10),
            ("Leather Armor", "+10 Armor", 300, "armor", "🛡️", 0, 10, 50),
            ("Iron Armor", "+25 Armor", 600, "armor", "🛡️", 0, 25, 30),
            ("Steel Armor", "+50 Armor", 1200, "armor", "🛡️", 0, 50, 15),
            ("Dragon Scale Armor", "+100 Armor", 2500, "armor", "🛡️", 0, 100, 5),
            ("HP Boost (Permanent)", "+50 Max HP", 2000, "permanent", "💪", 50, 0, 10),
            ("Armor Boost (Permanent)", "+20 Max Armor", 3000, "permanent", "🔰", 0, 20, 5),
            ("Lucky Charm", "+10% war win chance", 1500, "special", "🍀", 0, 0, 20),
            ("War Sword", "+15 damage in war", 1000, "weapon", "⚔️", 0, 0, 25),
            ("Magic Staff", "+25 damage in war", 2000, "weapon", "🔮", 0, 0, 10),
            ("Godly Blade", "+50 damage in war", 5000, "weapon", "🗡️", 0, 0, 3),
        ]
        for item in shop_items:
            c.execute('''INSERT INTO shop (name, description, price, category, emoji, hp_bonus, armor_bonus, stock) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', item)
        conn.commit()
    conn.close()

def init_gacha():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM gacha_items")
    count = c.fetchone()[0]
    if count == 0:
        items = [
            ("Common Sword", "Common", "🗡️", "A basic sword", 40.0, 0, 0),
            ("Iron Shield", "Common", "🛡️", "A sturdy shield", 30.0, 0, 5),
            ("Healing Herb", "Common", "🌿", "Restores 10 HP", 25.0, 10, 0),
            ("Mana Crystal", "Uncommon", "🔮", "Crystal of pure mana", 15.0, 0, 0),
            ("Steel Helm", "Uncommon", "⛑️", "+15 Armor", 8.0, 0, 15),
            ("Rare Bow", "Rare", "🏹", "A finely crafted bow", 2.5, 0, 0),
            ("Enchanted Ring", "Rare", "💍", "+25 Max HP", 1.5, 25, 0),
            ("Phoenix Feather", "Legendary", "🪶", "+50 HP & +20 Armor", 0.7, 50, 20),
            ("Dragon Crown", "Legendary", "👑", "Crown of the dragon king (+100 HP)", 0.3, 100, 30),
        ]
        for item in items:
            c.execute('''INSERT INTO gacha_items (name, rarity, emoji, description, rate, hp_bonus, armor_bonus) 
                        VALUES (?, ?, ?, ?, ?, ?, ?)''', item)
        conn.commit()
    conn.close()

# ================== DATABASE HELPERS ==================
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
        (user_id, username, first_name, joined_at, last_active, hp, max_hp, armor) 
        VALUES (?, ?, ?, ?, ?, 100, 100, 0)''', 
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

def get_user_dict(user_id):
    user = get_user(user_id)
    if not user:
        return None
    columns = ["user_id", "username", "first_name", "coins", "bank", "bank_max", "xp", "level", 
               "total_xp", "games_played", "games_won", "games_lost", "coins_earned", "coins_lost",
               "last_daily", "daily_streak", "items", "is_banned", "joined_at", "last_active",
               "referred_by", "referral_count", "loan", "loan_date", "hp", "max_hp", "armor",
               "war_wins", "war_losses"]
    return dict(zip(columns, user))

def get_top_users(category="coins", limit=10):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    order_map = {
        "coins": "coins DESC",
        "level": "level DESC, xp DESC",
        "games": "games_won DESC",
        "net_worth": "(coins + bank) DESC",
        "war": "war_wins DESC"
    }
    order = order_map.get(category, "coins DESC")
    c.execute(f"SELECT user_id, first_name, username, coins, level, games_won, war_wins FROM users WHERE is_banned = 0 ORDER BY {order} LIMIT ?", (limit,))
    users = c.fetchall()
    conn.close()
    return users

def get_all_shop_items():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM shop WHERE is_active = 1 ORDER BY price ASC")
    items = c.fetchall()
    conn.close()
    return items

def get_shop_item(item_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM shop WHERE id = ?", (item_id,))
    item = c.fetchone()
    conn.close()
    return item

def get_all_gacha_items():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM gacha_items")
    items = c.fetchall()
    conn.close()
    return items

def pull_gacha():
    items = get_all_gacha_items()
    r = random.uniform(0, 100)
    cumulative = 0
    for item in items:
        cumulative += item[4]  # rate
        if r <= cumulative:
            return {"id": item[0], "name": item[1], "rarity": item[2], "emoji": item[3], "description": item[4], 
                    "hp_bonus": item[6], "armor_bonus": item[7]}
    return items[-1]

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

def add_item_to_user(user_id, item_dict):
    user = get_user_dict(user_id)
    items = json.loads(user["items"]) if isinstance(user["items"], str) and user["items"] else (user["items"] or [])
    item_dict["obtained_at"] = datetime.utcnow().isoformat()
    items.append(item_dict)
    update_user(user_id, items=json.dumps(items))

def get_user_items(user_id):
    user = get_user_dict(user_id)
    if not user:
        return []
    items = user["items"]
    if isinstance(items, str):
        return json.loads(items) if items else []
    return items or []

async def add_xp(user_id, xp_amount, context):
    user = get_user_dict(user_id)
    if not user:
        return
    new_xp = user["xp"] + xp_amount
    new_total_xp = user["total_xp"] + xp_amount
    new_level = user["level"]
    xp_needed = int(new_level * 100 * 1.5)
    leveled_up = False
    while new_xp >= xp_needed:
        new_xp -= xp_needed
        new_level += 1
        xp_needed = int(new_level * 100 * 1.5)
        leveled_up = True
    update_user(user_id, xp=new_xp, level=new_level, total_xp=new_total_xp)
    if leveled_up:
        reward = new_level * 100
        user = get_user_dict(user_id)
        update_user(user_id, coins=user["coins"] + reward, max_hp=user["max_hp"] + 10)  # +10 max HP per level
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎉 **LEVEL UP!**\nYou're now **Level {new_level}**!\n💰 +{reward} coins\n❤️ +10 Max HP"
            )
        except:
            pass

def is_admin(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users ORDER BY joined_at ASC LIMIT 1")
    first_user = c.fetchone()
    conn.close()
    return first_user and user_id == first_user[0]

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

# ================== COMMANDS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username
    first_name = user.first_name
    
    args = context.args
    if args and args[0].startswith("ref_"):
        try:
            ref_id = int(args[0].replace("ref_", ""))
            if ref_id != user_id:
                get_or_create_user(user_id, username, first_name)
                update_user(ref_id, referral_count=get_user_dict(ref_id)["referral_count"] + 1)
                add_coins(ref_id, 200)
        except:
            pass
    
    get_or_create_user(user_id, username, first_name)
    user_data = get_user_dict(user_id)
    
    text = (
        f"🎮 **Welcome to {BOT_NAME}!**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👤 {first_name or username or 'Player'} | Lv.{user_data['level']}\n"
        f"❤️ HP: {user_data['hp']}/{user_data['max_hp']} | 🛡️ Armor: {user_data['armor']}\n"
        f"💰 {user_data['coins']:,} coins\n"
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
        [InlineKeyboardButton("⚔️ WAR", callback_data="game_war"),
         InlineKeyboardButton("✨ Gacha", callback_data="menu_gacha")],
        [InlineKeyboardButton("🛒 Shop", callback_data="menu_shop"),
         InlineKeyboardButton("💰 Economy", callback_data="menu_economy")],
        [InlineKeyboardButton("🏆 Leaderboard", callback_data="menu_leaderboard"),
         InlineKeyboardButton("📊 Profile", callback_data="menu_profile")],
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def profile_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user_dict(user_id)
    if not user:
        await update.message.reply_text("Please /start first!")
        return
    
    name = user["first_name"] or user["username"] or "Player"
    
    items = get_user_items(user_id)
    
    text = (
        f"📊 **{name}'s Profile**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👤 **Level:** {user['level']}\n"
        f"⭐ **XP:** {user['xp']}/{int(user['level'] * 100 * 1.5)}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"❤️ **HP:** {user['hp']}/{user['max_hp']}\n"
        f"🛡️ **Armor:** {user['armor']}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💰 **Coins:** {user['coins']:,}\n"
        f"🏦 **Bank:** {user['bank']:,}/{user['bank_max']:,}\n"
        f"💎 **Net Worth:** {user['coins'] + user['bank']:,}\n"
        f"🏦 **Loan:** {user['loan']:,}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🎮 **Games:** {user['games_played']}\n"
        f"✅ **Wins:** {user['games_won']}\n"
        f"❌ **Losses:** {user['games_lost']}\n"
        f"📈 **Win Rate:** {round((user['games_won'] / user['games_played'] * 100) if user['games_played'] > 0 else 0, 2)}%\n"
        f"━━━━━━━━━━━━━━━\n"
        f"⚔️ **War Wins:** {user['war_wins']}\n"
        f"⚔️ **War Losses:** {user['war_losses']}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🪙 **Earned:** {user['coins_earned']:,}\n"
        f"💸 **Lost:** {user['coins_lost']:,}\n"
        f"🔥 **Streak:** {user['daily_streak']} days\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🎒 **Items Owned:** {len(items)}\n"
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
    if last_daily and (now - last_daily).total_seconds() < 172800:
        streak += 1
    else:
        streak = 1
    
    base_reward = 500
    streak_bonus = min(streak * 50, 500)
    level_bonus = user["level"] * 10
    total_reward = base_reward + streak_bonus + level_bonus
    
    # Full HP restore on daily
    update_user(user_id, last_daily=now.isoformat(), daily_streak=streak, hp=user["max_hp"])
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
        f"❤️ **HP Fully Restored!**\n"
        f"⭐ **XP:** +25"
    )
    
    await update.message.reply_text(text)

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    category = context.args[0] if context.args else "coins"
    
    cat_names = {"coins": "💰 Richest", "level": "⭐ Highest Level", "games": "🎮 Most Wins", "net_worth": "💎 Net Worth", "war": "⚔️ War Champions"}
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
        if category == "war":
            value = f"⚔️ {user[6]} war wins"
        elif category == "coins":
            value = f"💰 {user[3]:,}"
        elif category == "level":
            value = f"⭐ Lv.{user[4]}"
        else:
            value = f"🎮 {user[5]} wins"
        text += f"{medal} **{name}** — {value}\n"
    
    keyboard = [
        [InlineKeyboardButton("💰 Coins", callback_data="lb_coins"),
         InlineKeyboardButton("⭐ Level", callback_data="lb_level"),
         InlineKeyboardButton("🎮 Wins", callback_data="lb_games")],
        [InlineKeyboardButton("⚔️ War", callback_data="lb_war"),
         InlineKeyboardButton("🔙 Back", callback_data="menu_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def gift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    
    if len(args) < 2:
        await u
