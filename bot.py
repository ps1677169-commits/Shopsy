import os
import logging
import asyncio
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler
)
from proxy_manager import ProxyManager
from checker import GrainotchChecker

# ================== CONFIG ==================
BOT_TOKEN = "8848695021:AAGZPLZLgrZkv9qcxlaRGUSQuLl25JyRPvc"
ADMIN_ID = -7249306811  # admin chat ID
PROXY_FILE = "proxies.txt"

# ================== GLOBALS ==================
proxy_manager = ProxyManager()
checker = None
check_task = None
current_mobile = "9369556930"

# Conversation states
PROXY_FILE_STATE = 1

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# ================== HELPERS ==================
async def send_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mobile = current_mobile
    proxy_count = proxy_manager.get_count()
    running = checker is not None and checker.running
    status = (
        f"📊 **Current Status**\n"
        f"Mobile: `{mobile}`\n"
        f"Proxies: `{proxy_count}` active\n"
        f"Checker: `{'🟢 Running' if running else '🔴 Stopped'}`"
    )
    await update.message.reply_text(status)

# ================== HANDLERS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 **Grainotch Code Checker Bot**\n\n"
        "Commands:\n"
        "/check <mobile> [num_codes] – Start checking (default 200)\n"
        "/stop – Stop current check\n"
        "/proxy add – Upload `.txt` file with proxies\n"
        "/proxy list – Show active proxies (first 5)\n"
        "/proxy clear – Remove all proxies\n"
        "/valid – Show all valid codes found\n"
        "/status – Show current config\n"
        "/help – Show this message"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def valid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    codes = GrainotchChecker.get_all_valid_codes()
    if not codes:
        await update.message.reply_text("No valid codes found yet.")
        return
    text = f"✅ **Total Valid Codes:** {len(codes)}\n\n"
    # Show first 20
    for i, code in enumerate(codes[:20]):
        text += f"{i+1}. `{code}`\n"
    if len(codes) > 20:
        text += f"\n... and {len(codes)-20} more."
    await update.message.reply_text(text)

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_mobile, checker, check_task
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /check <mobile> [num_codes]")
        return
    mobile = args[0]
    num_codes = int(args[1]) if len(args) > 1 else 200
    if not mobile.isdigit() or len(mobile) < 10:
        await update.message.reply_text("Invalid mobile number.")
        return
    if checker and checker.running:
        await update.message.reply_text("⚠️ A check is already running. Use /stop first.")
        return

    current_mobile = mobile
    checker = GrainotchChecker(proxy_manager, bot=context.bot, admin_id=ADMIN_ID)
    await update.message.reply_text(
        f"✅ Starting check for {mobile} with {num_codes} codes.\n"
        f"Proxies in use: {proxy_manager.get_count()}\n"
        f"Use /stop to halt."
    )

    async def run_and_report():
        try:
            result = await checker.run_check(mobile, num_codes, concurrency=30)
            report = (
                f"🏁 **Check completed!**\n"
                f"Total tested: {result['total']}\n"
                f"Valid found: {result['valid']}\n"
                f"Time: {result['time']}s\n"
                f"Speed: {result['speed']} codes/sec\n"
                f"Valid codes saved in `valid_codes.json`"
            )
            await update.message.reply_text(report)
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")
        finally:
            global check_task
            check_task = None

    check_task = asyncio.create_task(run_and_report())

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global checker, check_task
    if checker and checker.running:
        checker.stop()
        await update.message.reply_text("🛑 Check stopped.")
        if check_task:
            check_task.cancel()
            check_task = None
    else:
        await update.message.reply_text("No check is running.")

async def proxy_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Please send a `.txt` file with proxies (one per line).\n"
        "Format: `ip:port` or `user:pass@ip:port`\n"
        "Send /cancel to abort."
    )
    return PROXY_FILE_STATE

async def proxy_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if not document or not document.file_name.endswith('.txt'):
        await update.message.reply_text("Please send a valid `.txt` file.")
        return PROXY_FILE_STATE

    file = await context.bot.get_file(document.file_id)
    file_path = f"temp_{document.file_name}"
    await file.download_to_drive(file_path)

    try:
        count = proxy_manager.load_from_file(file_path)
        await update.message.reply_text(f"✅ Added {count} proxies. Total: {proxy_manager.get_count()}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
    finally:
        os.remove(file_path)
    return ConversationHandler.END

async def proxy_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END

async def proxy_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = proxy_manager.get_count()
    if count == 0:
        await update.message.reply_text("No proxies loaded.")
        return
    proxies = proxy_manager.proxies
    text = f"🔧 **Active Proxies ({count})**\n"
    for p in proxies[:5]:
        text += f"- `{p}`\n"
    if count > 5:
        text += f"... and {count-5} more."
    await update.message.reply_text(text)

async def proxy_clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    proxy_manager.clear()
    await update.message.reply_text("✅ All proxies cleared.")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_status(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.error("Exception:", exc_info=context.error)
    await update.message.reply_text("An unexpected error occurred.")

# ================== MAIN ==================
def main():
    # Preload proxies from default file if exists
    if os.path.exists(PROXY_FILE):
        try:
            count = proxy_manager.load_from_file(PROXY_FILE)
            print(f"Loaded {count} proxies from {PROXY_FILE}")
        except:
            pass

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("check", check_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("valid", valid_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("proxy", proxy_list_command))
    app.add_handler(CommandHandler("proxyclear", proxy_clear_command))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("proxyadd", proxy_add_command)],
        states={PROXY_FILE_STATE: [MessageHandler(filters.Document.ALL, proxy_file_handler)]},
        fallbacks=[CommandHandler("cancel", proxy_cancel)]
    )
    app.add_handler(conv_handler)

    app.add_error_handler(error_handler)

    print("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
