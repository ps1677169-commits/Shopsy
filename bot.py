#!/usr/bin/env python3
"""
Shopsy SuperCoin Farm Bot – Ultimate Edition
Telegram bot with mass account management, auto-farm, clickable buttons, and permanent rotating proxies.

================================================================
CREDITS
================================================================
Made with ❤️ by @hey_berlin
Version: 1.1.0
================================================================
"""
import os
import json
import time
import random
import logging
import asyncio
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Optional, List

import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, MessageHandler, filters
)

# ======================== CONFIG ========================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable not set!")

DB_FILE = "shopsy.db"
VERSION = "1.1.0"
AUTHOR = "@hey_berlin"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ======================== PERMANENT PROXY POOL ========================
PROXY_POOL = [
    "http://GlwcQObskG0cCTOa:Dejrd8zYxOjjqcY9@geo.floppydata.com:10080",
    "http://DzBnvAfHHqPDqFll:wZV0cVNbFix79t4K@geo.floppydata.com:10080",
    "http://ykmPCzNWrQdPQ5Ul:zmLyZetwxrpjhqSd@geo-dc.floppydata.com:10080",
    "http://8LH6ieLzPxNZajZU:Jg5OLu0HmU9CoKzB@geo.floppydata.com:10080",
    "http://1yec3wWxjvCXPc5V:qpcpD67Y7Tg0XHIm@geo.floppydata.com:10080",
    "http://lqSo9YnxZ5E309Ii:zTAmx7ZKcThqFsDi@geo-dc.floppydata.com:10080",
    "http://0Bgry9z3xKvu6xnL:Z4v24Ab1kp9lkvHD@geo-dc.floppydata.com:10080",
    "http://zidoqPECIrGNoa0D:vwYU094925uFjEP5@geo.floppydata.com:10080",
    "http://hB0Gt9IQUtvEcyVi:Q2LEkIFYvcu9x0SG@geo.floppydata.com:10080",
    "http://ZKBo0bpg4dxC5fAI:WQcfXONgARKS9XSi@geo.floppydata.com:10080",
    "http://lq3PPnLp6GDa60Py:xrcPiH7zyHjCtTTG@geo.floppydata.com:10080",
    "http://D7LPlz8eDBINP8Xh:OdEEumBcXxCSYIOS@geo.floppydata.com:10080",
    "http://HnIRwhAH2LOSsKmb:ZA2mzTEJCrTJ3ze4@geo-dc.floppydata.com:10080",
    "http://hdty6YibAlNwm9To:OT5yYUH4nMZZdWXb@geo-dc.floppydata.com:10080",
    "http://K9k2rVZWvLQZL8Ni:1N8Z7l4lApE2K2dr@geo-dc.floppydata.com:10080",
    "http://KYT9fdyDu0e8cyVk:EgFG7FDAkl36ILu2@geo-dc.floppydata.com:10080",
]

# ======================== DATABASE ========================
def init_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT UNIQUE,
            name TEXT DEFAULT 'User',
            cookie TEXT,
            vid TEXT,
            dc INTEGER DEFAULT 1,
            coins INTEGER DEFAULT 0,
            today_coins INTEGER DEFAULT 0,
            total_earned INTEGER DEFAULT 0,
            last_farm TEXT,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER,
            action TEXT,
            message TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('mode', 'FAST')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_farm', '0')")
    conn.commit()
    conn.close()

def get_conn():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def get_setting(key, default='FAST'):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key, value):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def log_action(account_id, action, message):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO logs (account_id, action, message) VALUES (?, ?, ?)",
              (account_id, action, message))
    conn.commit()
    conn.close()

# ======================== PROXY MANAGER ========================
class ProxyManager:
    def __init__(self):
        self.pool = PROXY_POOL.copy()
        self.current_index = 0
        self.failed_proxies = set()

    def get_proxy(self) -> Optional[Dict]:
        if not self.pool:
            return None
        attempts = 0
        while attempts < len(self.pool):
            proxy = self.pool[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.pool)
            if proxy not in self.failed_proxies:
                return {'http': proxy, 'https': proxy}
            attempts += 1
        self.failed_proxies.clear()
        if self.pool:
            return {'http': self.pool[0], 'https': self.pool[0]}
        return None

    def mark_fail(self, proxy: str):
        self.failed_proxies.add(proxy)

    def mark_success(self, proxy: str):
        if proxy in self.failed_proxies:
            self.failed_proxies.remove(proxy)

proxy_manager = ProxyManager()

# ======================== SHOPSY CLIENT ========================
class ShopsyClient:
    def __init__(self, phone: str, cookie: str = None, vid: str = None, dc: int = 1):
        self.phone = phone
        self.cookie = cookie
        self.vid = vid
        self.dc = dc
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json"
        })
        self.base_url = "https://api.shopsy.in"
        self.logged_in = bool(cookie)
        self.current_proxy = None

    def _get_host(self) -> str:
        hosts = {
            1: "https://1.rose.ap1.fikpart.net",
            2: "https://2.rose.ap1.fikpart.net",
            3: "https://3.rose.ap1.fikpart.net",
            4: "https://4.rose.ap1.fikpart.net"
        }
        return hosts.get(self.dc, hosts[1])

    def _request(self, method, url, **kwargs):
        proxy = proxy_manager.get_proxy()
        if proxy:
            kwargs['proxies'] = proxy
            self.current_proxy = proxy.get('http')
        try:
            resp = self.session.request(method, url, timeout=15, **kwargs)
            if resp.status_code < 400:
                if self.current_proxy:
                    proxy_manager.mark_success(self.current_proxy)
            return resp
        except Exception as e:
            if self.current_proxy:
                proxy_manager.mark_fail(self.current_proxy)
                logger.warning(f"Proxy {self.current_proxy} failed: {e}")
            kwargs.pop('proxies', None)
            return self.session.request(method, url, timeout=15, **kwargs)

    def request_otp(self) -> Dict:
        url = f"{self._get_host()}/api/v1/auth/otp"
        payload = {"phone": self.phone}
        resp = self._request("POST", url, json=payload)
        return resp.json()

    def verify_otp(self, otp: str) -> Dict:
        url = f"{self._get_host()}/api/v1/auth/login"
        payload = {"phone": self.phone, "otp": otp}
        resp = self._request("POST", url, json=payload)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success"):
                self.cookie = data.get("cookie")
                self.vid = data.get("vid")
                self.dc = data.get("dc", 1)
                self.logged_in = True
        return resp.json()

    def get_profile(self) -> Dict:
        url = f"{self._get_host()}/api/v1/user/profile"
        resp = self._request("GET", url, cookies={"cookie": self.cookie})
        return resp.json()

    def claim_login_bonus(self) -> Dict:
        url = f"{self._get_host()}/api/v1/rewards/login"
        resp = self._request("POST", url, cookies={"cookie": self.cookie})
        return resp.json()

    def start_game(self, game: str) -> Dict:
        url = f"{self._get_host()}/api/v1/games/{game}/start"
        resp = self._request("POST", url, cookies={"cookie": self.cookie})
        return resp.json()

    def finish_game(self, game: str, session_id: str, score: int = 0) -> Dict:
        url = f"{self._get_host()}/api/v1/games/{game}/finish"
        payload = {"sessionId": session_id, "score": score}
        resp = self._request("POST", url, json=payload, cookies={"cookie": self.cookie})
        return resp.json()

    def get_coins(self) -> Dict:
        url = f"{self._get_host()}/api/v1/coins"
        resp = self._request("GET", url, cookies={"cookie": self.cookie})
        return resp.json()

    def get_games_status(self) -> Dict:
        url = f"{self._get_host()}/api/v1/games/status"
        resp = self._request("GET", url, cookies={"cookie": self.cookie})
        return resp.json()

# ======================== FARM ENGINE ========================
class FarmEngine:
    GAMES = [
        {"name": "super_runner", "wait": 94, "coins": 2, "earnable": 12},
        {"name": "city_builder", "wait": 18, "coins": 2, "earnable": 10},
        {"name": "fruit_crush", "wait": 18, "coins": 2, "earnable": 8},
        {"name": "grocery_match", "wait": 18, "coins": 2, "earnable": 6},
    ]

    def __init__(self, client: ShopsyClient, mode: str = "FAST"):
        self.client = client
        self.mode = mode
        self.total_coins = 0

    async def farm(self, callback=None) -> Dict:
        results = {"games": [], "coins": 0, "status": "success", "details": ""}
        try:
            bonus = self.client.claim_login_bonus()
            if bonus.get("success"):
                coins = bonus.get("coins", 0)
                results["coins"] += coins
                results["details"] += f"Login bonus: +{coins} "

            status = self.client.get_games_status()
            pending = status.get("pending", 6)

            for game in self.GAMES:
                if pending <= 0:
                    break
                start_resp = self.client.start_game(game["name"])
                if not start_resp.get("success"):
                    continue
                session_id = start_resp.get("sessionId")
                wait_time = game["wait"] if self.mode == "FAST" else game["wait"] + 30
                if self.mode == "SLOW":
                    wait_time = game["wait"] + 60
                if callback:
                    await callback(f"🎮 {game['name']} ... {wait_time}s")
                await asyncio.sleep(wait_time)
                finish_resp = self.client.finish_game(game["name"], session_id)
                if finish_resp.get("success"):
                    coins = finish_resp.get("coins", game["coins"])
                    results["coins"] += coins
                    results["games"].append({
                        "name": game["name"],
                        "coins": coins,
                        "session": session_id
                    })
                    pending -= 1
                    results["details"] += f"{game['name']}: +{coins} "
            self.total_coins = results["coins"]
            results["status"] = "complete"
        except Exception as e:
            results["status"] = f"error: {str(e)}"
            results["details"] = str(e)
        return results

# ======================== TELEGRAM BOT ========================
pending_otp = {}
pending_delete = {}
PHONE, OTP, DELETE_CONFIRM = range(3)

async def safe_send(update: Update, text: str, reply_markup=None, parse_mode="HTML"):
    try:
        if reply_markup:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            await update.message.reply_text(text, parse_mode=parse_mode)
    except Exception as e:
        logger.error(f"Failed to send with {parse_mode}: {e}")
        try:
            if reply_markup:
                await update.message.reply_text(text, reply_markup=reply_markup)
            else:
                await update.message.reply_text(text)
        except Exception as e2:
            logger.error(f"Failed to send plain text: {e2}")

async def start(update: Update, context):
    keyboard = [
        [InlineKeyboardButton("➕ Add Account", callback_data="add_account")],
        [InlineKeyboardButton("📋 My Accounts", callback_data="list_accounts")],
        [InlineKeyboardButton("🚀 Farm All", callback_data="farm_all")],
        [InlineKeyboardButton("📊 Stats", callback_data="stats")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
        [InlineKeyboardButton("📤 Export / 📥 Import", callback_data="export_import")],
        [InlineKeyboardButton("📜 Logs", callback_data="logs")],
        [InlineKeyboardButton("📈 Credits", callback_data="credits")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = (
        "🛒 <b>Shopsy SuperCoin Farm Bot</b>\n\n"
        "Earn coins automatically by playing mini-games.\n"
        "Add your Shopsy account and start farming!\n\n"
        f"🌐 Proxy: <b>✅ Auto-Rotating ({len(PROXY_POOL)} proxies)</b>\n\n"
        "────────────────────\n"
        "👨‍💻 <b>Made with ❤️ by @hey_berlin</b>"
    )
    await safe_send(update, text, reply_markup, "HTML")

async def credits_command(update: Update, context):
    text = (
        f"📈 <b>Credits</b>\n\n"
        f"<b>Bot:</b> Shopsy SuperCoin Farm Bot\n"
        f"<b>Version:</b> {VERSION}\n"
        f"<b>Developer:</b> @hey_berlin\n"
        f"<b>Made with:</b> ❤️ + Python + Telegram\n\n"
        f"<b>Special Thanks:</b> The Shopsy community, early testers, and contributors.\n\n"
        f"🔗 <b>Repo:</b> <a href='https://github.com/YOUR_USERNAME/shopsy-farm-bot'>GitHub</a>\n\n"
        f"💡 If you like this bot, consider starring the repo!\n\n"
        "────────────────────\n"
        "👨‍💻 <b>Made with ❤️ by @hey_berlin</b>"
    )
    await safe_send(update, text, None, "HTML")

async def button_handler(update: Update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    async def reply(text, reply_markup=None, parse_mode="HTML"):
        try:
            await query.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception as e:
            logger.error(f"Callback reply error: {e}")
            try:
                await query.message.reply_text(text, reply_markup=reply_markup)
            except Exception as e2:
                logger.error(f"Callback plain fallback error: {e2}")

    if data == "credits":
        text = (
            f"📈 <b>Credits</b>\n\n"
            f"<b>Bot:</b> Shopsy SuperCoin Farm Bot\n"
            f"<b>Version:</b> {VERSION}\n"
            f"<b>Developer:</b> @hey_berlin\n"
            f"<b>Made with:</b> ❤️ + Python + Telegram\n\n"
            f"<b>Special Thanks:</b> The Shopsy community, early testers, and contributors.\n\n"
            f"🔗 <b>Repo:</b> <a href='https://github.com/YOUR_USERNAME/shopsy-farm-bot'>GitHub</a>\n\n"
            f"💡 If you like this bot, consider starring the repo!\n\n"
            "────────────────────\n"
            "👨‍💻 <b>Made with ❤️ by @hey_berlin</b>"
        )
        await reply(text)
        return

    if data == "add_account":
        logger.info("📱 Add Account button clicked – entering PHONE state")
        text = (
            "📱 <b>Add Account</b>\n\n"
            "Send your phone number with country code:\n"
            "<code>+919890902059</code>\n\n"
            "Or upload a JSON file with multiple accounts."
        )
        await reply(text)
        return PHONE

    elif data == "list_accounts":
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT id, phone, name, coins, today_coins, active, total_earned FROM accounts ORDER BY id")
        rows = c.fetchall()
        conn.close()
        if not rows:
            await reply("No accounts added yet.")
            return
        msg = "<b>📋 Your Accounts</b>\n\n"
        for row in rows:
            status = "🟢 Active" if row[5] else "🔴 Inactive"
            msg += (
                f"<code>{row[1]}</code> – <b>{row[2]}</b>\n"
                f"  💰 Total: {row[3]} | Today: {row[4]}\n"
                f"  📈 Lifetime: {row[6]}\n"
                f"  {status}\n\n"
            )
        keyboard = []
        for row in rows[:5]:
            keyboard.append([
                InlineKeyboardButton(f"🎮 Farm {row[2]}", callback_data=f"farm_{row[0]}"),
                InlineKeyboardButton(f"⏸️ {'Pause' if row[5] else 'Resume'}", callback_data=f"toggle_{row[0]}"),
                InlineKeyboardButton(f"🗑️", callback_data=f"delete_{row[0]}")
            ])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await reply(msg, reply_markup)

    elif data.startswith("farm_"):
        acc_id = int(data.split("_")[1])
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT phone, cookie, vid, dc, name FROM accounts WHERE id = ? AND active = 1", (acc_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            await reply("❌ Account not found or inactive.")
            return
        await reply(f"🎮 Farming <b>{row[4]}</b>...")
        client = ShopsyClient(row[0], row[1], row[2], row[3])
        engine = FarmEngine(client, get_setting('mode', 'FAST'))
        result = await engine.farm()
        if result["status"] == "complete":
            conn = get_conn()
            c = conn.cursor()
            c.execute(
                "UPDATE accounts SET coins = coins + ?, today_coins = today_coins + ?, total_earned = total_earned + ?, last_farm = ? WHERE id = ?",
                (result["coins"], result["coins"], result["coins"], datetime.now().isoformat(), acc_id)
            )
            conn.commit()
            conn.close()
            await reply(f"✅ {row[4]} – earned {result['coins']} coins\n{result['details']}")
        else:
            await reply(f"❌ Failed: {result['status']}")

    elif data.startswith("toggle_"):
        acc_id = int(data.split("_")[1])
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT active FROM accounts WHERE id = ?", (acc_id,))
        row = c.fetchone()
        if row:
            new_status = 0 if row[0] else 1
            c.execute("UPDATE accounts SET active = ? WHERE id = ?", (new_status, acc_id))
            conn.commit()
        conn.close()
        await reply(f"✅ Account {'activated' if new_status else 'paused'}.")
        await button_handler(update, context)

    elif data.startswith("delete_"):
        acc_id = int(data.split("_")[1])
        pending_delete[user_id] = acc_id
        keyboard = [
            [InlineKeyboardButton("✅ Yes, delete", callback_data="confirm_delete")],
            [InlineKeyboardButton("❌ Cancel", callback_data="back")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await reply("⚠️ <b>Delete this account?</b> This cannot be undone.", reply_markup)
        return DELETE_CONFIRM

    elif data == "confirm_delete":
        acc_id = pending_delete.pop(user_id, None)
        if acc_id:
            conn = get_conn()
            c = conn.cursor()
            c.execute("DELETE FROM accounts WHERE id = ?", (acc_id,))
            conn.commit()
            conn.close()
            await reply("🗑️ Account deleted.")
        else:
            await reply("No account to delete.")
        await button_handler(update, context)

    elif data == "farm_all":
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT id, phone, cookie, vid, dc, name FROM accounts WHERE active = 1")
        accounts = c.fetchall()
        conn.close()
        if not accounts:
            await reply("No active accounts. Add one first.")
            return
        msg = await query.message.reply_text("🚀 <b>Farming all accounts...</b>", parse_mode="HTML")
        total_coins = 0
        results = []
        for acc in accounts:
            client = ShopsyClient(acc[1], acc[2], acc[3], acc[4])
            engine = FarmEngine(client, get_setting('mode', 'FAST'))
            result = await engine.farm()
            if result["status"] == "complete":
                conn = get_conn()
                c = conn.cursor()
                c.execute(
                    "UPDATE accounts SET coins = coins + ?, today_coins = today_coins + ?, total_earned = total_earned + ?, last_farm = ? WHERE id = ?",
                    (result["coins"], result["coins"], result["coins"], datetime.now().isoformat(), acc[0])
                )
                conn.commit()
                conn.close()
                total_coins += result["coins"]
                results.append(f"✅ {acc[5]}: +{result['coins']} coins")
            else:
                results.append(f"❌ {acc[5]}: {result['status']}")
        await msg.edit_text(
            f"🏁 <b>Farming complete!</b>\n"
            f"Total coins earned: {total_coins}\n\n"
            + "\n".join(results),
            parse_mode="HTML"
        )

    elif data == "stats":
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM accounts WHERE active = 1")
        active = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM accounts")
        total_acc = c.fetchone()[0]
        c.execute("SELECT SUM(coins) FROM accounts")
        total = c.fetchone()[0] or 0
        c.execute("SELECT SUM(today_coins) FROM accounts")
        today = c.fetchone()[0] or 0
        c.execute("SELECT SUM(total_earned) FROM accounts")
        lifetime = c.fetchone()[0] or 0
        conn.close()
        await reply(
            f"📊 <b>Stats</b>\n\n"
            f"👤 Active accounts: {active}/{total_acc}\n"
            f"💰 Total coins: {total}\n"
            f"📈 Earned today: {today}\n"
            f"🏆 Lifetime earnings: {lifetime}"
        )

    elif data == "settings":
        current_mode = get_setting('mode', 'FAST')
        auto_farm = get_setting('auto_farm', '0')
        keyboard = [
            [InlineKeyboardButton(f"⚡ Mode: {current_mode}", callback_data="toggle_mode")],
            [InlineKeyboardButton(f"🔄 Auto-Farm: {'ON' if auto_farm == '1' else 'OFF'}", callback_data="toggle_auto")],
            [InlineKeyboardButton("📅 Set Interval", callback_data="set_interval")],
            [InlineKeyboardButton("🔙 Back", callback_data="back")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await reply("⚙️ <b>Settings</b>", reply_markup)

    elif data == "toggle_mode":
        modes = ["FAST", "NORMAL", "SLOW"]
        current = get_setting('mode', 'FAST')
        next_mode = modes[(modes.index(current) + 1) % len(modes)]
        set_setting('mode', next_mode)
        await reply(f"✅ Mode changed to: <b>{next_mode}</b>")
        await button_handler(update, context)

    elif data == "toggle_auto":
        current = get_setting('auto_farm', '0')
        new = '1' if current == '0' else '0'
        set_setting('auto_farm', new)
        await reply(f"🔄 Auto-farm {'enabled' if new == '1' else 'disabled'}.")
        await button_handler(update, context)

    elif data == "set_interval":
        await reply(
            "📅 <b>Set Auto-Farm Interval</b>\n\n"
            "Send the number of hours (e.g., <code>2</code> for every 2 hours).\n"
            "Minimum 1 hour, maximum 24 hours.",
            parse_mode="HTML"
        )
        return ConversationHandler.ENTER_INTERVAL

    elif data == "export_import":
        keyboard = [
            [InlineKeyboardButton("📤 Export Accounts", callback_data="export")],
            [InlineKeyboardButton("📥 Import Accounts", callback_data="import")],
            [InlineKeyboardButton("🔙 Back", callback_data="back")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await reply("📤 <b>Export / Import</b>", reply_markup)

    elif data == "export":
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT phone, cookie, vid, dc, name FROM accounts")
        rows = c.fetchall()
        conn.close()
        if not rows:
            await reply("No accounts to export.")
            return
        data = [{"phone": r[0], "cookie": r[1], "vid": r[2], "dc": r[3], "name": r[4]} for r in rows]
        with open("accounts_export.json", "w") as f:
            json.dump(data, f, indent=2)
        await query.message.reply_document(
            document=open("accounts_export.json", "rb"),
            filename=f"accounts_{datetime.now().strftime('%Y%m%d')}.json"
        )

    elif data == "import":
        await reply(
            "📥 <b>Import Accounts</b>\n\n"
            "Send a JSON file in this format:\n"
            "<code>[{\"phone\": \"+91...\", \"cookie\": \"...\", \"vid\": \"...\", \"dc\": 1, \"name\": \"User\"}]</code>",
            parse_mode="HTML"
        )
        return ConversationHandler.ENTER_IMPORT

    elif data == "logs":
        conn = get_conn()
        c = conn.cursor()
        c.execute("""
            SELECT a.phone, l.action, l.message, l.timestamp
            FROM logs l JOIN accounts a ON l.account_id = a.id
            ORDER BY l.timestamp DESC LIMIT 20
        """)
        rows = c.fetchall()
        conn.close()
        if not rows:
            await reply("No logs yet.")
            return
        msg = "📜 <b>Recent Logs</b>\n\n"
        for row in rows:
            msg += f"<code>{row[0]}</code> – {row[1]}: {row[2][:30]}\n  {row[3][:16]}\n\n"
        await reply(msg)

    elif data == "back":
        await start(update, context)

    return ConversationHandler.END

# ==================== MESSAGE HANDLERS ====================
async def phone_input(update: Update, context):
    logger.info(f"📱 Phone input received: {update.message.text}")
    phone = update.message.text.strip()
    if not phone.startswith("+") or len(phone) < 10:
        await safe_send(update, "❌ Invalid phone. Use format: <code>+919890902059</code>", parse_mode="HTML")
        return ConversationHandler.END
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM accounts WHERE phone = ?", (phone,))
    exists = c.fetchone()
    conn.close()
    if exists:
        await safe_send(update, "❌ This phone is already added.", parse_mode="HTML")
        return ConversationHandler.END
    client = ShopsyClient(phone)
    logger.info(f"📤 Requesting OTP for {phone}")
    resp = client.request_otp()
    logger.info(f"📥 OTP response: {resp}")
    if resp.get("success"):
        pending_otp[phone] = (client, resp.get("requestId"))
        await safe_send(update, f"✅ OTP sent to <code>{phone}</code>\nSend the 6-digit OTP.", parse_mode="HTML")
        return OTP
    else:
        await safe_send(update, f"❌ Failed: {resp.get('message', 'Unknown error')}", parse_mode="HTML")
        return ConversationHandler.END

async def otp_input(update: Update, context):
    logger.info(f"🔑 OTP received: {update.message.text}")
    otp = update.message.text.strip()
    if len(otp) != 6 or not otp.isdigit():
        await safe_send(update, "❌ Invalid OTP. Enter 6 digits.", parse_mode="HTML")
        return OTP
    phone = None
    for p, (client, _) in pending_otp.items():
        if client.phone:
            phone = p
            break
    if not phone:
        await safe_send(update, "❌ No pending OTP. Start with /start", parse_mode="HTML")
        return ConversationHandler.END
    client, _ = pending_otp.pop(phone, (None, None))
    if not client:
        await safe_send(update, "❌ Session expired.", parse_mode="HTML")
        return ConversationHandler.END
    logger.info(f"🔐 Verifying OTP for {phone}")
    resp = client.verify_otp(otp)
    logger.info(f"✅ Verification response: {resp}")
    if resp.get("success"):
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            "INSERT INTO accounts (phone, cookie, vid, dc, name) VALUES (?, ?, ?, ?, ?)",
            (phone, client.cookie, client.vid, client.dc, resp.get('name', 'User'))
        )
        acc_id = c.lastrowid
        conn.commit()
        conn.close()
        log_action(acc_id, "ADD", "Account added")
        await safe_send(update, f"✅ <b>Account added!</b>\n📱 <code>{phone}</code>\n👤 {resp.get('name', 'User')}", parse_mode="HTML")
    else:
        await safe_send(update, f"❌ OTP failed: {resp.get('message', 'Unknown error')}", parse_mode="HTML")
    return ConversationHandler.END

async def file_input(update: Update, context):
    document = update.message.document
    if not document.file_name.endswith('.json'):
        await safe_send(update, "❌ Upload a .json file.", parse_mode="HTML")
        return
    file = await context.bot.get_file(document.file_id)
    content = await file.download_as_bytearray()
    try:
        data = json.loads(content.decode('utf-8'))
    except:
        await safe_send(update, "❌ Invalid JSON.", parse_mode="HTML")
        return
    if not isinstance(data, list):
        await safe_send(update, "❌ JSON must be a list.", parse_mode="HTML")
        return
    added = 0
    for acc in data:
        phone = acc.get('phone')
        if not phone:
            continue
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO accounts (phone, cookie, vid, dc, name) VALUES (?, ?, ?, ?, ?)",
            (phone, acc.get('cookie'), acc.get('vid'), acc.get('dc', 1), acc.get('name', 'User'))
        )
        if c.rowcount:
            added += 1
            log_action(c.lastrowid, "IMPORT", "Imported from file")
        conn.commit()
        conn.close()
    await safe_send(update, f"✅ Imported {added} accounts.", parse_mode="HTML")

async def interval_input(update: Update, context):
    try:
        hours = int(update.message.text.strip())
        if hours < 1 or hours > 24:
            raise ValueError
        set_setting('auto_farm_interval', str(hours))
        await safe_send(update, f"✅ Interval set to {hours} hours.", parse_mode="HTML")
    except:
        await safe_send(update, "❌ Send a number between 1 and 24.", parse_mode="HTML")
    return ConversationHandler.END

async def cancel(update: Update, context):
    await safe_send(update, "❌ Cancelled.", parse_mode="HTML")
    return ConversationHandler.END

# ==================== AUTO-FARM SCHEDULER ====================
async def auto_farm_job(context):
    if get_setting('auto_farm', '0') != '1':
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, phone, cookie, vid, dc, name FROM accounts WHERE active = 1")
    accounts = c.fetchall()
    conn.close()
    for acc in accounts:
        client = ShopsyClient(acc[1], acc[2], acc[3], acc[4])
        engine = FarmEngine(client, get_setting('mode', 'FAST'))
        result = await engine.farm()
        if result["status"] == "complete":
            conn = get_conn()
            c = conn.cursor()
            c.execute(
                "UPDATE accounts SET coins = coins + ?, today_coins = today_coins + ?, total_earned = total_earned + ?, last_farm = ? WHERE id = ?",
                (result["coins"], result["coins"], result["coins"], datetime.now().isoformat(), acc[0])
            )
            conn.commit()
            conn.close()
            log_action(acc[0], "AUTO_FARM", f"Earned {result['coins']} coins")

# ==================== MAIN ====================
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # Delete webhook
    try:
        resp = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
        if resp.status_code == 200:
            logger.info("✅ Webhook deleted successfully")
        else:
            logger.warning(f"⚠️ Webhook deletion response: {resp.text}")
    except Exception as e:
        logger.warning(f"⚠️ Could not delete webhook: {e}")

    # REGISTER HANDLERS IN THE CORRECT ORDER
    # 1. Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("credits", credits_command))

    # 2. Callback query handler - THIS MUST BE BEFORE CONVERSATION HANDLER
    app.add_handler(CallbackQueryHandler(button_handler))

    # 3. Message handlers
    app.add_handler(MessageHandler(filters.Document.ALL, file_input))

    # 4. Conversation handler - only for phone/OTP flow
    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(button_handler, pattern="^add_account$"),
        ],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_input)],
            OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND, otp_input)],
            DELETE_CONFIRM: [CallbackQueryHandler(button_handler, pattern="^confirm_delete$")],
        },
        fallbacks=[
            CommandHandler("start", start),
            CallbackQueryHandler(button_handler, pattern="^back$"),
        ],
        allow_reentry=True,
    )
    app.add_handler(conv_handler)

    # Job queue
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(auto_farm_job, interval=3600, first=60)
        logger.info("✅ JobQueue enabled – auto-farm scheduled")
    else:
        logger.warning("⚠️ JobQueue not available – auto-farm disabled")

    logger.info("Bot started polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
