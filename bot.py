# ================== GAMING BOT v2 — FULL FIXED ==================
# Features: Gacha, Bank, Loan, Gift, Admin, 60/40 Win Rate

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
BOT_TOKEN = "8880531578:AAFH6S2UlEpTaF2B20gXtPyuAyzSk6vxOes"  # ⚠️ REVOKE THIS AND GET A NEW ONE FROM @BotFather
BOT_NAME = "KAYRUU"
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
        loan_date TEXT
    )''')
    
    # Gacha characters / items table
    c.execute('''CREATE TABLE IF NOT EXISTS gacha_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        rarity TEXT,
        emoji TEXT,
        description TEXT,
        rate REAL
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

def get_user_dict(user_id):
    user = get_user(user_id)
    if not user:
        return None
    
    columns = ["user_id", "username", "first_name", "coins", "bank", "bank_max", "xp", "level", 
               "total_xp", "games_played", "games_won", "games_lost", "coins_earned", "coins_lost",
               "last_daily", "daily_streak", "items", "is_banned", "joined_at", "last_active",
               "referred_by", "referral_count", "loan", "loan_date"]
    
    return dict(zip(columns, user))

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

# ================== GACHA DATA ==================
DEFAULT_GACHA_ITEMS = [
    # (name, rarity, emoji, description, rate)
    ("Common Sword", "Common", "🗡️", "A basic sword", 40.0),
    ("Iron Shield", "Common", "🛡️", "A sturdy shield", 30.0),
    ("Healing Potion", "Uncommon", "🧪", "Restores HP", 15.0),
    ("Mana Crystal", "Uncommon", "🔮", "Crystal of pure mana", 10.0),
    ("Rare Bow", "Rare", "🏹", "A finely crafted bow", 2.5),
    ("Enchanted Ring", "Rare", "💍", "Ring of ancient power", 1.5),
    ("Legendary Blade", "Legendary", "⚔️", "Blade of the ancients", 0.7),
    ("Dragon Crown", "Legendary", "👑", "Crown of the dragon king", 0.3),
]

def init_gacha():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM gacha_items")
    count = c.fetchone()[0]
    if count == 0:
        for item in DEFAULT_GACHA_ITEMS:
            c.execute("INSERT INTO gacha_items (name, rarity, emoji, description, rate) VALUES (?, ?, ?, ?, ?)", item)
        conn.commit()
    conn.close()

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
            return {"id": item[0], "name": item[1], "rarity": item[2], "emoji": item[3], "description": item[4]}
    return items[-1]

# ================== HELPERS ==================
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

def add_item_to_user(user_id, gacha_item):
    user = get_user_dict(user_id)
    items = json.loads(user["items"]) if user["items"] else []
    items.append(gacha_item)
    update_user(user_id, items=json.dumps(items))

def is_admin(user_id):
    """Auto-admin: first user who starts the bot becomes admin."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users ORDER BY joined_at ASC LIMIT 1")
    first_user = c.fetchone()
    conn.close()
    # Also check if user_id is in a special admin list
    # For simplicity, we treat the first user as admin.
    # You can change this logic.
    return first_user and user_id == first_user[0]

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
    
    text = (
        f"🎮 **Welcome to {BOT_NAME}!**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👤 {first_name or username or 'Player'}\n"
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
        [InlineKeyboardButton("✨ Gacha", callback_data="menu_gacha"),
         InlineKeyboardButton("💰 Economy", callback_data="menu_economy")],
        [InlineKeyboardButton("🏆 Leaderboard", callback_data="menu_leaderboard"),
         InlineKeyboardButton("📊 Profile", callback_data="menu_profile")],
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def admin_addcoins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ You are not an admin!")
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: `/addcoins @user 999999` or `/addcoins user_id 999999`")
        return
    
    try:
        target = args[0]
        amount = int(args[1])
        
        if target.startswith("@"):
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT user_id FROM users WHERE username = ?", (target[1:],))
            result = c.fetchone()
            conn.close()
            if not result:
                await update.message.reply_text("User not found!")
                return
            target_id = result[0]
        else:
            target_id = int(target)
        
        add_coins(target_id, amount)
        await update.message.reply_text(f"✅ Added **{amount:,}** coins to `{target_id}`")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def admin_setcoins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ You are not an admin!")
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: `/setcoins @user 999999`")
        return
    
    try:
        target = args[0]
        amount = int(args[1])
        
        if target.startswith("@"):
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT user_id FROM users WHERE username = ?", (target[1:],))
            result = c.fetchone()
            conn.close()
            if not result:
                await update.message.reply_text("User not found!")
                return
            target_id = result[0]
        else:
            target_id = int(target)
        
        update_user(target_id, coins=amount)
        await update.message.reply_text(f"✅ Set **{amount:,}** coins for `{target_id}`")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def gift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    
    if len(args) < 2:
        await update.message.reply_text("Usage: `/gift @user 100`")
        return
    
    try:
        amount = int(args[-1])
        target = args[0]
        
        if target.startswith("@"):
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT user_id FROM users WHERE username = ?", (target[1:],))
            result = c.fetchone()
            conn.close()
            if not result:
                await update.message.reply_text("User not found!")
                return
            target_id = result[0]
        else:
            target_id = int(target)
        
        if target_id == user_id:
            await update.message.reply_text("Can't gift yourself!")
            return
        
        if amount < 10:
            await update.message.reply_text("Minimum gift is 10 coins")
            return
        
        user = get_user_dict(user_id)
        if user["coins"] < amount:
            await update.message.reply_text(f"Insufficient coins! You have {user['coins']:,}")
            return
        
        deduct_coins(user_id, amount)
        add_coins(target_id, amount)
        
        await update.message.reply_text(f"🎁 Gifted **{amount:,}** coins to `{target_id}`")
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"🎁 You received **{amount:,}** coins as a gift from `{user_id}`!"
            )
        except:
            pass
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

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
    loan = user["loan"]
    
    items = json.loads(user["items"]) if user["items"] else []
    items_text = ""
    if items:
        rarities = {"Legendary": "⚜️", "Rare": "🔹", "Uncommon": "🔸", "Common": "▫️"}
        for it in items[-5:]:
            r_emoji = rarities.get(it.get("rarity", ""), "▫️")
            items_text += f"{r_emoji} {it.get('emoji', '')} {it.get('name', 'Unknown')}\n"
    
    text = (
        f"📊 **{name}'s Profile**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👤 **Level:** {level}\n"
        f"⭐ **XP:** {xp}/{xp_needed}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💰 **Coins:** {coins:,}\n"
        f"🏦 **Bank:** {bank:,} / {user['bank_max']:,}\n"
        f"💎 **Net Worth:** {net_worth:,}\n"
        f"🏦 **Loan:** {loan:,}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🎮 **Games:** {games}\n"
        f"✅ **Wins:** {wins}\n"
        f"❌ **Losses:** {losses}\n"
        f"📈 **Win Rate:** {win_rate}%\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🪙 **Earned:** {earned:,}\n"
        f"💸 **Lost:** {lost:,}\n"
        f"🔥 **Streak:** {streak} days\n"
    )
    
    if items_text:
        text += f"━━━━━━━━━━━━━━━\n**🎒 Recent Items:**\n{items_text}"
    
    text += f"\n🆔 ID: `{user_id}`"
    
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
        [InlineKeyboardButton("💰 Coins", callback_data="lb_coins"),
         InlineKeyboardButton("⭐ Level", callback_data="lb_level"),
         InlineKeyboardButton("🎮 Wins", callback_data="lb_games")],
        [InlineKeyboardButton("🔙 Back", callback_data="menu_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def loan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user_dict(user_id)
    if not user:
        await update.message.reply_text("Please /start first!")
        return
    
    args = context.args
    if not args:
        # Show loan info
        text = (
            f"🏦 **Loan System**\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📊 Current Loan: **{user['loan']:,}** coins\n"
            f"📈 Max Loan: **{(user['level'] * 500):,}** coins\n"
            f"💸 Interest: **10%** daily\n"
            f"━━━━━━
