import html
import json
import requests
from urllib.parse import urljoin
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)
import logging

# =========================
# Logging
# =========================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# =========================
# Config
# =========================
REST_API_URL = "http://catalog:5001"

# keep END symbol available even if we don't use states now
ADD_SENSOR, ADD_SITUATION, SENSOR_DETAILS, UPDATE_PROFILE = range(4)

# Your requested token (hard-coded, per your instruction)
TELEGRAM_TOKEN = "8439269111:AAFVv-C_qC0cfMC9oXomfxlMbkKNUlSq9Fo"

# Admins (Telegram user IDs)
ADMINS = [6378242947, 650295422, 6605276431, 548805315]


def is_admin(user_id: int) -> bool:
    return user_id in ADMINS


# =========================
# REST helpers
# =========================
def api_get(endpoint):
    try:
        r = requests.get(f"{REST_API_URL}/{endpoint}", timeout=10)
        if r.status_code == 200:
            return r.json()
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"API GET error: {e}")
        return None


def api_post(endpoint, data):
    try:
        r = requests.post(f"{REST_API_URL}/{endpoint}", json=data, timeout=10)
        return r.status_code in (200, 201)
    except requests.exceptions.RequestException as e:
        logger.error(f"API POST error: {e}")
        return False


def api_put(endpoint, data):
    try:
        r = requests.put(f"{REST_API_URL}/{endpoint}", json=data, timeout=10)
        return r.status_code == 200
    except requests.exceptions.RequestException as e:
        logger.error(f"API PUT error: {e}")
        return False


def api_delete(endpoint):
    try:
        r = requests.delete(f"{REST_API_URL}/{endpoint}", timeout=10)
        return r.status_code == 200
    except requests.exceptions.RequestException as e:
        logger.error(f"API DELETE error: {e}")
        return False


# =========================
# Service helpers
# =========================
def _sensor_service_url():
    svc = api_get("services/sensor")
    if not svc or "url" not in svc:
        return None
    # normalize trailing slash
    return svc["url"].rstrip("/")


def _panel_service():
    svc = api_get("services/adminPanel")
    if not svc or "url" not in svc:
        return None
    return {"url": svc["url"].rstrip("/"), "port": svc.get("port")}


def start_recording_for(user_id: int):
    """
    Try several common patterns so we work with your existing sensor service.
    Returns (ok: bool, message: str)
    """
    base = _sensor_service_url()
    if not base:
        return False, "Sensor service not found."

    # Candidate GET endpoints (in order)
    get_candidates = [
        f"{base}/start/{user_id}",
        f"{base}/{user_id}/start",
        f"{base}/{user_id}",  # legacy "run" path
    ]
    for url in get_candidates:
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                return True, "Recording started."
        except Exception as e:
            logger.warning(f"start GET attempt failed {url}: {e}")

    # Candidate POST endpoint
    try:
        r = requests.post(f"{base}/start", json={"user_id": user_id}, timeout=10)
        if r.status_code in (200, 201):
            return True, "Recording started."
    except Exception as e:
        logger.warning(f"start POST attempt failed {base}/start: {e}")

    return False, "Failed to start recording."


def stop_recording_for(user_id: int):
    """
    Try several common patterns for stopping.
    Returns (ok: bool, message: str)
    """
    url = _sensor_service_url()
    base = urljoin(url, "/")
    if not base:
        return False, "Sensor service not found."

    get_candidates = [
        f"{base}/stop/{user_id}",
        f"{base}/{user_id}/stop",
    ]
    for url in get_candidates:
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                return True, "Recording stopped."
        except Exception as e:
            logger.warning(f"stop GET attempt failed {url}: {e}")

    try:
        r = requests.post(f"{base}/stop", json={"user_id": user_id}, timeout=10)
        if r.status_code in (200, 201):
            return True, "Recording stopped."
    except Exception as e:
        logger.warning(f"stop POST attempt failed {base}/stop: {e}")

    return False, "Failed to stop recording."


def get_report_for(user_id: int):
    panel = _panel_service()
    if not panel:
        return False, "Report service not found."
    url = panel["url"]
    port = panel.get("port")
    full = f"{url}:{port}/report/{user_id}" if port else f"{url}/report/{user_id}"
    try:
        r = requests.get(full, timeout=15)
        if r.status_code == 200:
            try:
                data = r.json()
            except Exception:
                data = r.text
            if not data:
                return True, "No report found."
            # keep it short to avoid Telegram 4096 char limit
            text = html.escape(json.dumps(data, ensure_ascii=False)[:1200])
            return True, text
        return False, f"Failed to fetch report (HTTP {r.status_code})."
    except Exception as e:
        logger.error(f"Error fetching report {full}: {e}")
        return False, "Error while fetching report."


# =========================
# Telegram Handlers
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = api_get(f"users/{chat_id}")
    if user:
        await update.message.reply_text(
            f"👋 Welcome back, {html.escape(user['full_name'])}!\nUse /menu."
        )
    else:
        await update.message.reply_text(
            "🏥 Welcome to Human Health Monitoring!\n\n"
            "Please register with your full name using:\n"
            "/register <your full name>"
        )


async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if len(context.args) < 1:
        await update.message.reply_text("Please provide your full name: /register <your name>")
        return
    full_name = " ".join(context.args)
    if api_post("users", {"user_chat_id": chat_id, "full_name": full_name}):
        await update.message.reply_text(f"✅ Registered, {html.escape(full_name)}.\nUse /menu.")
    else:
        await update.message.reply_text("❌ Registration failed. Try again.")


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not api_get(f"users/{chat_id}"):
        await update.message.reply_text("Please register first with /register <your name>")
        return

    if is_admin(chat_id):
        keyboard = [
            [InlineKeyboardButton("▶️ Start all", callback_data="admin_start_all")],
            [InlineKeyboardButton("⏹ Stop all", callback_data="admin_stop_all")],
            [InlineKeyboardButton("📊 Monitor all", callback_data="admin_monitor_all")],
            [InlineKeyboardButton("👥 Manage users", callback_data="admin_user_list")],
            [InlineKeyboardButton("📄 Get my report", callback_data="get_report")],
            [InlineKeyboardButton("🗑 Remove my profile", callback_data="delete_profile")],
        ]
        text = "🛠 Admin menu:"
    else:
        keyboard = [
            [InlineKeyboardButton("▶️ Start", callback_data="start_recording")],
            [InlineKeyboardButton("📄 Get report", callback_data="get_report")],
            [InlineKeyboardButton("⏹ Stop", callback_data="stop_recording")],
            [InlineKeyboardButton("🗑 Remove profile", callback_data="delete_profile")],
        ]
        text = "📋 Main menu:"

    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id

    # user must exist
    user = api_get(f"users/{chat_id}")
    if not user:
        await query.edit_message_text("Please register first with /register <your name>")
        return ConversationHandler.END

    admin_mode = is_admin(chat_id)

    # ===== Normal user buttons =====
    if query.data == "start_recording":
        ok, msg = start_recording_for(chat_id)
        await query.edit_message_text("✅ " + msg if ok else "❌ " + msg)

    elif query.data == "stop_recording":
        ok, msg = stop_recording_for(chat_id)
        await query.edit_message_text("✅ " + msg if ok else "❌ " + msg)

    elif query.data == "get_report":
        ok, text = get_report_for(chat_id)
        await query.edit_message_text(text if ok else "❌ " + text, parse_mode="HTML")

    elif query.data == "delete_profile":
        keyboard = [
            [
                InlineKeyboardButton("Yes, delete my data", callback_data=f"confirm_delete_{chat_id}"),
                InlineKeyboardButton("Cancel", callback_data="cancel_delete"),
            ]
        ]
        await query.edit_message_text(
            "⚠️ Are you sure you want to delete your profile and all data?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif query.data.startswith("confirm_delete_"):
        target_user = int(query.data.split("_")[-1])
        if api_delete(f"users/{target_user}"):
            await query.edit_message_text("✅ Your profile and all data have been deleted.")
        else:
            await query.edit_message_text("❌ Failed to delete profile.")

    elif query.data == "cancel_delete":
        await query.edit_message_text("Profile deletion cancelled.")

    # ===== Admin buttons =====
    elif query.data == "admin_start_all" and admin_mode:
        users = api_get("users") or []
        started, failed = 0, 0
        for u in users:
            ok, _ = start_recording_for(int(u["user_chat_id"]))
            started += 1 if ok else 0
            failed += 0 if ok else 1
        await query.edit_message_text(f"▶️ Started for {started} users. Failed: {failed}.")

    elif query.data == "admin_stop_all" and admin_mode:
        users = api_get("users") or []
        stopped, failed = 0, 0
        for u in users:
            ok, _ = stop_recording_for(int(u["user_chat_id"]))
            stopped += 1 if ok else 0
            failed += 0 if ok else 1
        await query.edit_message_text(f"⏹ Stopped for {stopped} users. Failed: {failed}.")

    elif query.data == "admin_monitor_all" and admin_mode:
        users = api_get("users") or []
        lines = []
        shown = 0
        for u in users:
            uid = int(u["user_chat_id"])
            ok, snippet = get_report_for(uid)
            if ok:
                name = html.escape(u.get("full_name", str(uid)))
                lines.append(f"• <b>{name}</b> (ID {uid})\n<code>{snippet[:600]}</code>")
                shown += 1
            if shown >= 8:  # keep message size safe
                lines.append("… (truncated)")
                break
        if not lines:
            await query.edit_message_text("No reports found.")
        else:
            await query.edit_message_text("\n\n".join(lines), parse_mode="HTML")

    elif query.data == "admin_user_list" and admin_mode:
        users = api_get("users") or []
        if not users:
            await query.edit_message_text("No users found.")
            return ConversationHandler.END

        keyboard = [
            [InlineKeyboardButton(f"{html.escape(u['full_name'])} (ID: {u['user_chat_id']})",
                                  callback_data=f"admin_user_{u['user_chat_id']}")]
            for u in users
        ]
        keyboard.append([InlineKeyboardButton("Cancel", callback_data="cancel")])
        await query.edit_message_text(
            "👥 User list — choose one:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML",
        )

    elif query.data.startswith("admin_user_") and admin_mode:
        target_id = int(query.data.split("_")[-1])
        user_target = api_get(f"users/{target_id}")
        if not user_target:
            await query.edit_message_text("User not found.")
            return ConversationHandler.END

        keyboard = [
            [InlineKeyboardButton("▶️ Start", callback_data=f"admin_start_user_{target_id}")],
            [InlineKeyboardButton("⏹ Stop", callback_data=f"admin_stop_user_{target_id}")],
            [InlineKeyboardButton("📄 Get report", callback_data=f"admin_get_report_{target_id}")],
            [InlineKeyboardButton("🗑️ Remove user", callback_data=f"admin_delete_user_{target_id}")],
            [InlineKeyboardButton("⬅️ Back to list", callback_data="admin_user_list")],
        ]
        await query.edit_message_text(
            f"Managing: <b>{html.escape(user_target['full_name'])}</b> (ID {target_id})",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML",
        )

    elif query.data.startswith("admin_start_user_") and admin_mode:
        target_id = int(query.data.split("_")[-1])
        ok, msg = start_recording_for(target_id)
        await query.edit_message_text(f"User {target_id}: " + ("✅ " + msg if ok else "❌ " + msg))

    elif query.data.startswith("admin_stop_user_") and admin_mode:
        target_id = int(query.data.split("_")[-1])
        ok, msg = stop_recording_for(target_id)
        await query.edit_message_text(f"User {target_id}: " + ("✅ " + msg if ok else "❌ " + msg))

    elif query.data.startswith("admin_get_report_") and admin_mode:
        target_id = int(query.data.split("_")[-1])
        ok, text = get_report_for(target_id)
        await query.edit_message_text(
            (f"📄 Report for {target_id}:\n\n{text}" if ok else "❌ " + text),
            parse_mode="HTML",
        )

    elif query.data.startswith("admin_delete_user_") and admin_mode:
        target_id = int(query.data.split("_")[-1])
        keyboard = [
            [
                InlineKeyboardButton("Yes, delete user", callback_data=f"confirm_admin_delete_{target_id}"),
                InlineKeyboardButton("Cancel", callback_data="admin_user_list"),
            ]
        ]
        await query.edit_message_text(
            f"⚠️ Delete user {target_id} and all data?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif query.data.startswith("confirm_admin_delete_") and admin_mode:
        target_id = int(query.data.split("_")[-1])
        if api_delete(f"users/{target_id}"):
            await query.edit_message_text(f"✅ User {target_id} deleted.")
        else:
            await query.edit_message_text("❌ Failed to delete user.")

    elif query.data == "cancel":
        await query.edit_message_text("Operation cancelled.")

    else:
        await query.edit_message_text("Action not recognized or not permitted.")

    return ConversationHandler.END


# (kept for backward-compat with old code paths, but now unused)
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="Exception while handling update:", exc_info=context.error)
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text("An error occurred. Please try again.")
    except Exception:
        pass


def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Core commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("menu", menu))

    # Single callback handler drives the whole UI
    application.add_handler(CallbackQueryHandler(button_handler))

    # Error handler
    application.add_error_handler(error_handler)

    application.run_polling()


if __name__ == "__main__":
    main()
