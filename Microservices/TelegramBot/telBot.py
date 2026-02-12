from __future__ import annotations

import html
import json
import logging
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
)

# Allow running from this file location
sys.path.append(str(Path(__file__).parent.parent.parent))

from Microservices.Common.config import Config
from Microservices.Common.utils import ServiceRegistry

# Optional chart libs 
try:
    import io
    from datetime import datetime

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    import pandas as pd

    CHARTS_AVAILABLE = True
except Exception:
    CHARTS_AVAILABLE = False


# Logging 
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("telegram_bot.log", mode="a")],
)
logger = logging.getLogger("telegram-bot")


# Services / config
CATALOG_URL = Config.SERVICES["catalog_url"].rstrip("/")
TELEGRAM_TOKEN = Config.TELEGRAM_TOKEN
ADMINS = {int(uid) for uid in Config.ADMIN_USERS.keys()}

registry = ServiceRegistry()
DATABASE_ADAPTER_URL = (registry.get_service_url("databaseAdapter") or "").rstrip("/")

# Conversation states
(DEVICE_TYPE,) = range(1)


# -------------------------
# Small HTTP helpers
# -------------------------
def _request_json(
    method: str,
    url: str,
    *,
    json_body: Any = None,
    params: Dict[str, Any] | None = None,
) -> Tuple[int, Any]:
    """Return (status_code, json_or_text). Never raises."""
    try:
        r = requests.request(method, url, json=json_body, params=params, timeout=15)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, r.text
    except requests.RequestException as e:
        logger.error("HTTP error %s %s: %s", method, url, e)
        return 0, str(e)


def api_get(endpoint: str) -> Any:
    code, data = _request_json("GET", f"{CATALOG_URL}/{endpoint.lstrip('/')}")
    return data if code == 200 else None


def api_post(endpoint: str, data: Any) -> bool:
    code, body = _request_json("POST", f"{CATALOG_URL}/{endpoint.lstrip('/')}", json_body=data)
    if code not in (200, 201):
        logger.warning("POST %s failed (%s): %s", endpoint, code, body)
    return code in (200, 201)


def api_put(endpoint: str, data: Any) -> bool:
    code, body = _request_json("PUT", f"{CATALOG_URL}/{endpoint.lstrip('/')}", json_body=data)
    if code != 200:
        logger.warning("PUT %s failed (%s): %s", endpoint, code, body)
    return code == 200


def api_delete(endpoint: str) -> bool:
    code, body = _request_json("DELETE", f"{CATALOG_URL}/{endpoint.lstrip('/')}")
    if code != 200:
        logger.warning("DELETE %s failed (%s): %s", endpoint, code, body)
    return code == 200


# -------------------------
# Identity helpers
# -------------------------
def is_doctor(user_id: int) -> bool:
    user = api_get(f"users/{user_id}") or {}
    return user.get("user_type") == "doctor"


def is_admin(user_id: int) -> bool:
    if user_id in ADMINS:
        return True
    # In this app doctors also manage patients like admins.
    return is_doctor(user_id)


def get_doctor_patients(doctor_id: int) -> List[Dict[str, Any]]:
    return api_get(f"doctors/{doctor_id}") or []


# -------------------------
# Device helpers
# -------------------------
def get_device_types() -> List[str]:
    return api_get("device_types") or []


def get_user_devices(user_id: int) -> List[Dict[str, Any]]:
    return api_get(f"user_devices/{user_id}") or []


def register_new_device(device_id: str, device_type: str) -> bool:
    return api_post("devices", {"id": device_id, "type": device_type})


def assign_device_to_user(user_id: int, device_id: str) -> bool:
    return api_post(f"user_devices/{user_id}", {"device_id": device_id})


def remove_device_from_user(user_id: int, device_id: str) -> bool:
    return api_delete(f"user_devices/{user_id}/{device_id}")


# -------------------------
# Monitor service helpers
# -------------------------
def _sensor_service_url() -> Optional[str]:
    svc = api_get("services/monitor") or {}
    base = (svc.get("url") or "").rstrip("/")
    if not base:
        return None
    port = svc.get("port")
    return f"{base}:{port}" if port else base


def start_recording_for(user_id: int) -> Tuple[bool, str]:
    code, user_data = _request_json("GET", f"{CATALOG_URL}/users/{user_id}")
    if code != 200 or not isinstance(user_data, dict):
        return False, "User not found in the system."

    if user_data.get("user_type") != "patient":
        return False, "Recording is only available for patients."

    base = _sensor_service_url()
    if not base:
        return False, "Sensor service not found."

    code, _ = _request_json("GET", f"{base}/read/{user_id}")
    if code == 200:
        return True, "Recording started."
    return False, f"Failed to start recording (HTTP {code})."


def stop_recording_for(user_id: int) -> Tuple[bool, str]:
    base = _sensor_service_url()
    if not base:
        return False, "Sensor service not found."

    base = base.rstrip("/")
    if base.endswith("/read"):
        base = base[:-5].rstrip("/")

    code, _ = _request_json("GET", f"{base}/stop/{user_id}")
    if code == 200:
        return True, "Recording stopped successfully."
    return False, f"Failed to stop (HTTP {code})."


# -------------------------
# Reports
# -------------------------
def get_report_for(user_id: int, max_hours: int = 24) -> Tuple[bool, str]:
    if not DATABASE_ADAPTER_URL:
        return False, "Database adapter service not configured."

    url = f"{DATABASE_ADAPTER_URL}/read/{user_id}"
    code, raw = _request_json("GET", url, params={"hours": max_hours})
    if code != 200:
        return False, f"Failed to fetch report (HTTP {code})."

    try:
        if not raw:
            return True, "No report found."

        if isinstance(raw, dict) and raw.get("success") is False:
            return False, f"Database error: {raw.get('message', 'Unknown error')}"

        data = raw.get("data") if isinstance(raw, dict) and "data" in raw else raw

        if isinstance(data, str):
            data = json.loads(data)

        if not data:
            return True, "No report data found for this user."

        return True, format_health_report(data, user_id)
    except Exception as e:
        logger.error("Report processing error: %s", e)
        logger.error(traceback.format_exc())
        return False, "Error processing report data."


def format_health_report(data: List[Dict[str, Any]], user_id: int) -> str:
    if not data:
        return "No health data available."

    from collections import Counter, defaultdict
    from datetime import datetime

    grouped: Dict[str, Dict[str, Any]] = defaultdict(dict)

    for entry in data:
        ts = entry.get("time", "Unknown time")
        field = entry.get("field", "unknown")
        value = entry.get("value", "N/A")

        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+02:00"))
            ts_fmt = dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            ts_fmt = ts

        grouped[ts_fmt][field] = value

    times = sorted(grouped.keys(), reverse=True)

    lines: List[str] = [f"<b>Health Report - User {user_id}</b>\n"]
    for ts in times[:10]:
        r = grouped[ts]
        state = r.get("state", "N/A")
        emoji = {"healthy": "✅", "risky": "⚠️", "dangerous": "🚨"}.get(state, "❓")

        lines.append(f"<b>📅 {ts}</b>")
        lines.append(f"{emoji} Status: <b>{state}</b>")
        lines.append(f"🌡️ Temperature: {r.get('temp', 'N/A')}°C")
        lines.append(f"❤️ Heart Rate: {r.get('heart_rate', 'N/A')} BPM")
        lines.append(f"🫁 Oxygen: {r.get('oxygen', 'N/A')}%")
        lines.append("")

    if len(times) > 10:
        lines.append(f"... and {len(times) - 10} more readings")

    if times:
        latest = grouped[times[0]]
        lines.append("\n<b>📊 Summary</b>")
        lines.append(f"Latest Status: <b>{latest.get('state', 'unknown')}</b>")
        lines.append(f"Total Readings: {len(times)}")

        counts = Counter(r.get("state", "unknown") for r in grouped.values())
        lines.append("State Distribution:")
        for state, count in counts.items():
            pct = (count / len(times)) * 100
            lines.append(f"  • {state}: {count} ({pct:.1f}%)")

    return "\n".join(lines)


# -------------------------
# Charts
# -------------------------
def get_aggregated_chart_data_for(user_id: int, max_hours: int = 24) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    if not CHARTS_AVAILABLE:
        return False, "Chart functionality not available (missing matplotlib/pandas).", None
    if not DATABASE_ADAPTER_URL:
        return False, "Database adapter service not configured.", None

    url = f"{DATABASE_ADAPTER_URL}/aggregated/{user_id}"
    code, payload = _request_json("GET", url, params={"hours": max_hours})
    if code != 200:
        return False, f"Failed to fetch aggregated data (HTTP {code}).", None

    if not isinstance(payload, dict) or not payload.get("success", False):
        msg = payload.get("message", "Unknown error from database adapter") if isinstance(payload, dict) else str(payload)
        return False, f"Database error: {msg}", None

    data = payload.get("data", []) or []
    if not data:
        return True, f"No aggregated data found for the last {max_hours} hours.", None

    return True, "OK", {
        "data": data,
        "sample_info": payload.get("sample_info", "aggregated data"),
        "aggregation_frequency": payload.get("aggregation_frequency", "unknown"),
    }


def generate_chart_for(user_id: int, chart_type: str = "combined", max_hours: int = 24):
    if not CHARTS_AVAILABLE:
        return False, "Chart functionality not available - missing dependencies.", None

    ok, msg, result = get_aggregated_chart_data_for(user_id, max_hours)
    if not ok or not result:
        return False, msg, None

    try:
        aggregated_data = result["data"]
        sample_info = result.get("sample_info", "Aggregated Health Data")
        if not aggregated_data:
            return False, "No aggregated data available for chart generation.", None

        agg_df = pd.DataFrame(aggregated_data)
        agg_df["time"] = pd.to_datetime(agg_df["time"])

        fig, axes = plt.subplots(2, 2, figsize=(15, 10))

        time_range_text = f"Last {max_hours} hours" if max_hours < 48 else f"Last {max_hours//24} days"
        fig.suptitle(
            f"Health Monitoring Dashboard - User {user_id} ({time_range_text})\n{sample_info}",
            fontsize=16,
            fontweight="bold",
        )

        if "temp" in agg_df.columns:
            agg_df["temp"] = pd.to_numeric(agg_df["temp"], errors="coerce")
            temp_valid = agg_df.dropna(subset=["temp"])
            if not temp_valid.empty:
                axes[0, 0].plot(temp_valid["time"], temp_valid["temp"], "r-", linewidth=2)
                axes[0, 0].set_title("Body Temperature (°C)", fontweight="bold")
                axes[0, 0].set_ylabel("Temperature (°C)")
                axes[0, 0].grid(True, alpha=0.3)

        if "heart_rate" in agg_df.columns:
            agg_df["heart_rate"] = pd.to_numeric(agg_df["heart_rate"], errors="coerce")
            hr_valid = agg_df.dropna(subset=["heart_rate"])
            if not hr_valid.empty:
                axes[0, 1].plot(hr_valid["time"], hr_valid["heart_rate"], "g-", linewidth=2)
                axes[0, 1].set_title("Heart Rate (BPM)", fontweight="bold")
                axes[0, 1].set_ylabel("BPM")
                axes[0, 1].grid(True, alpha=0.3)

        if "oxygen" in agg_df.columns:
            agg_df["oxygen"] = pd.to_numeric(agg_df["oxygen"], errors="coerce")
            o2_valid = agg_df.dropna(subset=["oxygen"])
            if not o2_valid.empty:
                axes[1, 0].plot(o2_valid["time"], o2_valid["oxygen"], "b-", linewidth=2)
                axes[1, 0].set_title("Oxygen Saturation (%)", fontweight="bold")
                axes[1, 0].set_ylabel("SpO2 (%)")
                axes[1, 0].grid(True, alpha=0.3)

        if "state" in agg_df.columns:
            state_mapping = {"healthy": 0, "risky": 1, "dangerous": 2}
            state_colors = {"healthy": "green", "risky": "orange", "dangerous": "red"}

            agg_df["state_num"] = agg_df["state"].map(state_mapping)
            state_valid = agg_df.dropna(subset=["state_num"])
            if not state_valid.empty:
                colors = [state_colors.get(s, "gray") for s in state_valid["state"]]
                axes[1, 1].scatter(state_valid["time"], state_valid["state_num"], c=colors, s=50, alpha=0.8)
                axes[1, 1].set_title("Health State Status", fontweight="bold")
                axes[1, 1].set_ylabel("State")
                axes[1, 1].set_yticks([0, 1, 2])
                axes[1, 1].set_yticklabels(["Healthy", "Risky", "Dangerous"])
                axes[1, 1].grid(True, alpha=0.3)

        for ax in axes.flat:
            if len(ax.get_lines()) > 0 or len(ax.collections) > 0:
                if max_hours <= 24:
                    ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
                    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
                else:
                    ax.xaxis.set_major_locator(mdates.DayLocator())
                    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
                ax.tick_params(axis="x", rotation=45, labelsize=9)

        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        buf.seek(0)
        plt.close()

        return True, "Chart generated successfully.", buf

    except Exception as e:
        logger.error("Error generating chart: %s", e)
        logger.error(traceback.format_exc())
        return False, f"Chart generation failed: {str(e)}", None


async def send_chart_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, max_hours: int) -> None:
    if not CHARTS_AVAILABLE:
        await update.callback_query.edit_message_text("Charts are disabled on this server.")
        return

    ok, msg, buf = generate_chart_for(user_id, max_hours=max_hours)
    if not ok or not buf:
        await update.callback_query.edit_message_text(f"❌ {msg}")
        return

    label = {24: "24 hours", 48: "48 hours", 72: "72 hours", 168: "1 week"}.get(max_hours, f"{max_hours} hours")

    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=buf,
        caption=f"📊 Health chart for user {user_id} (Last {label})\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    )
    await update.callback_query.edit_message_text("✅ Chart sent.")


# -------------------------
# UI helpers
# -------------------------
def _menu_for(user: Dict[str, Any], user_id: int) -> Tuple[str, List[List[InlineKeyboardButton]]]:
    user_type = user.get("user_type", "patient")

    if user_type == "doctor":
        return "👨‍⚕️ Doctor Menu:", [
            [InlineKeyboardButton("👥 My Patients", callback_data="doctor_patients")],
            [InlineKeyboardButton("📊 Monitor All Patients", callback_data="doctor_monitor_all")],
            [InlineKeyboardButton("👤 My Profile", callback_data="doctor_profile")],
        ]

    if user_id in ADMINS:
        keyboard = [
            [InlineKeyboardButton("▶️ Start all", callback_data="admin_start_all")],
            [InlineKeyboardButton("⏹ Stop all", callback_data="admin_stop_all")],
            [InlineKeyboardButton("📊 Monitor all", callback_data="admin_monitor_all")],
            [InlineKeyboardButton("👥 Manage users", callback_data="admin_user_list")],
            [InlineKeyboardButton("📱 My Devices", callback_data="my_devices")],
            [InlineKeyboardButton("📄 Get my report", callback_data="get_report")],
        ]
        if CHARTS_AVAILABLE:
            keyboard.append([InlineKeyboardButton("📈 Get my chart", callback_data="get_chart")])
        keyboard.append([InlineKeyboardButton("🗑 Remove my profile", callback_data="delete_profile")])
        return "🛠 Admin Menu:", keyboard

    keyboard = [
        [InlineKeyboardButton("📱 My Devices", callback_data="my_devices")],
        [InlineKeyboardButton("▶️ Start monitoring", callback_data="start_recording")],
        [InlineKeyboardButton("📄 Get report", callback_data="get_report")],
        [InlineKeyboardButton("👨‍⚕️ Assign Doctor", callback_data="assign_doctor")],
    ]
    if CHARTS_AVAILABLE:
        keyboard.append([InlineKeyboardButton("📈 Get chart", callback_data="get_chart")])
    keyboard.extend(
        [
            [InlineKeyboardButton("⏹ Stop monitoring", callback_data="stop_recording")],
            [InlineKeyboardButton("🗑 Remove profile", callback_data="delete_profile")],
        ]
    )
    return "📋 Patient Menu:", keyboard


def _chart_period_keyboard(prefix: str, target_id: int, back_cb: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("📊 Last 24 hours", callback_data=f"{prefix}_24h_{target_id}")],
        [InlineKeyboardButton("📊 Last 48 hours", callback_data=f"{prefix}_48h_{target_id}")],
        [InlineKeyboardButton("📊 Last 72 hours", callback_data=f"{prefix}_72h_{target_id}")],
        [InlineKeyboardButton("📊 Last week", callback_data=f"{prefix}_week_{target_id}")],
        [InlineKeyboardButton("⬅️ Back", callback_data=back_cb)],
    ]
    return InlineKeyboardMarkup(rows)


def _parse_suffix_int(data: str) -> Optional[int]:
    try:
        return int(data.split("_")[-1])
    except Exception:
        return None


async def _back_to_main_menu(query, user_id: int):
    user = api_get(f"users/{user_id}")
    if not user:
        await query.edit_message_text("Register first with /register <your name>.")
        return
    text, keyboard = _menu_for(user, user_id)
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def _show_my_devices(query, user_id: int):
    devices = get_user_devices(user_id)
    if not devices:
        await query.edit_message_text(
            "📱 You don't have any devices yet.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("➕ Register New Device", callback_data="register_new_device")]]
            ),
        )
        return

    lines = ["📱 <b>Your Registered Devices:</b>\n"]
    for d in devices:
        dtype = (d.get("type", "unknown").replace("_", " ").title())
        did = d.get("id", "unknown")
        last = d.get("last_update", "Never")
        lines.append(f"• <b>{dtype}</b>\n  ID: <code>{html.escape(did)}</code>\n  Last Update: {last}\n")

    keyboard = [
        [InlineKeyboardButton("➕ Register New Device", callback_data="register_new_device")],
        [InlineKeyboardButton("🗑 Remove Device", callback_data="remove_device_menu")],
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_to_menu")],
    ]
    await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def _show_remove_device_menu(query, user_id: int):
    devices = get_user_devices(user_id)
    if not devices:
        await query.edit_message_text("You don't have any devices to remove.")
        return

    keyboard = [
        [
            InlineKeyboardButton(
                f"🗑 {d.get('type','unknown').replace('_',' ').title()} ({d.get('id','')})",
                callback_data=f"confirm_remove_device_{d.get('id','')}",
            )
        ]
        for d in devices
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="my_devices")])
    await query.edit_message_text("🗑 Select a device to remove:", reply_markup=InlineKeyboardMarkup(keyboard))


# -------------------------
# Device registration conversation
# -------------------------
async def start_device_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    types_ = get_device_types()
    if not types_:
        await query.edit_message_text("Couldn't retrieve device types. Try again later.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(t.replace("_", " ").title(), callback_data=f"devtype_{t}")] for t in types_]
    keyboard.append([InlineKeyboardButton("Cancel", callback_data="cancel_device_reg")])

    await query.edit_message_text(
        "📱 <b>Device Registration</b>\n\nSelect the type of device you want to register:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )
    return DEVICE_TYPE


async def receive_device_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import time

    query = update.callback_query
    await query.answer()

    if query.data == "cancel_device_reg":
        await query.edit_message_text("Device registration cancelled.")
        return ConversationHandler.END

    device_type = query.data.replace("devtype_", "")
    user_id = query.message.chat_id

    device_id = f"{device_type}_{user_id}_{int(time.time())}"

    if not register_new_device(device_id, device_type):
        await query.edit_message_text("Failed to register device. Please try again.\nUse /menu to continue.")
        return ConversationHandler.END

    if not assign_device_to_user(user_id, device_id):
        await query.edit_message_text("Device registered but not assigned. Please contact support.")
        return ConversationHandler.END

    await query.edit_message_text(
        "<b>Device Registered!</b>\n\n"
        f"📱 Device ID: <code>{html.escape(device_id)}</code>\n"
        f"📋 Type: {device_type.replace('_', ' ').title()}\n\n"
        "Use /menu to continue.",
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def cancel_device_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Device registration cancelled.")
    return ConversationHandler.END


# -------------------------
# Commands
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = api_get(f"users/{chat_id}")
    if user:
        await update.message.reply_text(f"Welcome back, {html.escape(user.get('full_name', ''))}! Use /menu.")
    else:
        await update.message.reply_text(
            "Welcome to Human Health Monitoring.\n\nRegister with:\n/register <your full name>"
        )


async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("Usage: /register <your full name>")
        return

    full_name = " ".join(context.args)
    ok = api_post("users", {"user_chat_id": chat_id, "full_name": full_name})
    if ok:
        await update.message.reply_text(
            f"✅ Registered: {html.escape(full_name)}\nUse /menu → My Devices to register devices."
        )
    else:
        await update.message.reply_text("❌ Registration failed. Try again.")


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = api_get(f"users/{chat_id}")
    if not user:
        await update.message.reply_text("Register first with /register <your name>.")
        return

    text, keyboard = _menu_for(user, chat_id)
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


# -------------------------
# Doctor commands
# -------------------------
async def register_doctor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if len(context.args) < 2:
        await update.message.reply_text("Usage:\n/register_doctor <Full Name> <Specialization> [Hospital]")
        return

    if len(context.args) >= 3:
        full_name = " ".join(context.args[:-2])
        specialization = context.args[-2]
        hospital = context.args[-1]
    else:
        full_name = context.args[0]
        specialization = context.args[1]
        hospital = ""

    ok = api_post(
        "doctors",
        {"user_chat_id": chat_id, "full_name": full_name, "specialization": specialization, "hospital": hospital},
    )
    if ok:
        await update.message.reply_text(
            "✅ Registered as doctor.\n"
            f"Name: {full_name}\nSpecialization: {specialization}\nHospital: {hospital}\n\nUse /menu."
        )
    else:
        await update.message.reply_text("❌ Doctor registration failed.")


async def update_doctor_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_doctor(chat_id):
        await update.message.reply_text("This command is only for doctors.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /update_doctor_name <Your Name>")
        return

    new_name = " ".join(context.args)
    if api_put(f"users/{chat_id}", {"full_name": new_name}):
        await update.message.reply_text(f"✅ Name updated to: {new_name}")
    else:
        await update.message.reply_text("❌ Failed to update name.")


async def update_doctor_specialization(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_doctor(chat_id):
        await update.message.reply_text("This command is only for doctors.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /update_doctor_specialization <Specialization>")
        return

    user = api_get(f"users/{chat_id}")
    if not user:
        await update.message.reply_text("❌ Couldn't retrieve your profile.")
        return

    user["specialization"] = " ".join(context.args)
    if api_put(f"users/{chat_id}", user):
        await update.message.reply_text("✅ Specialization updated.")
    else:
        await update.message.reply_text("❌ Failed to update specialization.")


async def update_doctor_hospital(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_doctor(chat_id):
        await update.message.reply_text("This command is only for doctors.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /update_doctor_hospital <Hospital Name>")
        return

    user = api_get(f"users/{chat_id}")
    if not user:
        await update.message.reply_text("❌ Couldn't retrieve your profile.")
        return

    user["hospital"] = " ".join(context.args)
    if api_put(f"users/{chat_id}", user):
        await update.message.reply_text("✅ Hospital updated.")
    else:
        await update.message.reply_text("❌ Failed to update hospital.")


# -------------------------
# One callback handler
# -------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.message.chat_id
    user = api_get(f"users/{user_id}")
    if not user:
        await query.edit_message_text("Register first with /register <your name>.")
        return ConversationHandler.END

    data = query.data

    try:
        # Navigation
        if data == "back_to_menu":
            await _back_to_main_menu(query, user_id)
            return

        # Devices
        if data == "my_devices":
            await _show_my_devices(query, user_id)
            return

        if data == "remove_device_menu":
            await _show_remove_device_menu(query, user_id)
            return

        if data.startswith("confirm_remove_device_"):
            device_id = data.replace("confirm_remove_device_", "")
            ok = remove_device_from_user(user_id, device_id)
            await query.edit_message_text("✅ Device removed." if ok else "❌ Failed to remove device.")
            return

        # Patient actions
        if data == "start_recording":
            ok, msg = start_recording_for(user_id)
            await query.edit_message_text(("✅ " if ok else "❌ ") + msg)
            return

        if data == "stop_recording":
            ok, msg = stop_recording_for(user_id)
            await query.edit_message_text(("✅ " if ok else "❌ ") + msg)
            return

        if data == "get_report":
            ok, text = get_report_for(user_id)
            await query.edit_message_text(text if ok else "❌ " + text, parse_mode="HTML")
            return

        if data == "get_chart":
            await query.edit_message_text(
                "📈 Select chart time period:",
                reply_markup=_chart_period_keyboard("get_chart", user_id, "back_to_menu"),
            )
            return

        if data.startswith("get_chart_"):
            parts = data.split("_")
            period = parts[2]
            target = int(parts[3])
            hours = {"24h": 24, "48h": 48, "72h": 72, "week": 168}.get(period)
            if not hours:
                await query.edit_message_text("Invalid chart period.")
                return
            await send_chart_to_user(update, context, target, max_hours=hours)
            return

        # Delete profile
        if data == "delete_profile":
            keyboard = [[
                InlineKeyboardButton("Yes, delete my data", callback_data=f"confirm_delete_{user_id}"),
                InlineKeyboardButton("Cancel", callback_data="cancel_delete"),
            ]]
            await query.edit_message_text("⚠️ Delete your profile and all data?", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data == "cancel_delete":
            await query.edit_message_text("Profile deletion cancelled.")
            return

        if data.startswith("confirm_delete_"):
            target = _parse_suffix_int(data)
            ok = api_delete(f"users/{target}") if target else False
            await query.edit_message_text("✅ Your data has been deleted." if ok else "❌ Failed to delete profile.")
            return

        # Assign doctor
        if data == "assign_doctor":
            doctors = api_get("doctors") or []
            if not doctors:
                await query.edit_message_text("No doctors are registered right now.")
                return

            current_doctor_id = (api_get(f"users/{user_id}") or {}).get("doctor_id")

            header = "Select a doctor:\n"
            if current_doctor_id:
                header = "Select a new doctor (or keep the current one):\n"

            keyboard = []
            for d in doctors:
                label = f"Dr. {d.get('full_name','')}"
                if d.get("specialization"):
                    label += f" ({d['specialization']})"
                if current_doctor_id and d.get("user_chat_id") == current_doctor_id:
                    label += " [Current]"
                keyboard.append([InlineKeyboardButton(label, callback_data=f"select_doctor_{d.get('user_chat_id')}")])
            keyboard.append([InlineKeyboardButton("Back to menu", callback_data="back_to_menu")])

            await query.edit_message_text(header, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data.startswith("select_doctor_"):
            doctor_id = _parse_suffix_int(data)
            if doctor_id is None:
                await query.edit_message_text("Invalid doctor selection.")
                return

            current_doctor_id = (api_get(f"users/{user_id}") or {}).get("doctor_id")
            if current_doctor_id == doctor_id:
                await query.edit_message_text("You are already assigned to this doctor.\nUse /menu to continue.")
                return

            ok = api_post("assign_patient", {"patient_id": user_id, "doctor_id": doctor_id})
            if not ok:
                await query.edit_message_text("Failed to assign doctor. Please try again.")
                return

            doctor = api_get(f"users/{doctor_id}") or {}
            doctor_name = doctor.get("full_name", "Unknown")
            await query.edit_message_text(f"You are now assigned to {doctor_name}.\n\nUse /menu to continue.")
            return

        # Doctor features
        if data == "doctor_menu" and is_doctor(user_id):
            await _back_to_main_menu(query, user_id)
            return

        if data == "doctor_patients" and is_doctor(user_id):
            patients = get_doctor_patients(user_id)
            if not patients:
                await query.edit_message_text("No patients assigned to you yet.")
                return
            keyboard = [
                [InlineKeyboardButton(f"{p['full_name']} (ID: {p['user_chat_id']})", callback_data=f"doctor_view_patient_{p['user_chat_id']}")]
                for p in patients
            ]
            keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="doctor_menu")])
            await query.edit_message_text(f"👥 Your Patients ({len(patients)}):", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data.startswith("doctor_view_patient_") and is_doctor(user_id):
            patient_id = _parse_suffix_int(data)
            patients = get_doctor_patients(user_id)
            if patient_id is None or not any(p["user_chat_id"] == patient_id for p in patients):
                await query.edit_message_text("Access denied.")
                return
            keyboard = [
                [InlineKeyboardButton("📄 View Report", callback_data=f"doctor_patient_report_{patient_id}")],
                [InlineKeyboardButton("📈 View Chart", callback_data=f"doctor_patient_chart_{patient_id}")],
                [InlineKeyboardButton("▶️ Start Monitoring", callback_data=f"doctor_start_patient_{patient_id}")],
                [InlineKeyboardButton("⏹ Stop Monitoring", callback_data=f"doctor_stop_patient_{patient_id}")],
                [InlineKeyboardButton("⬅️ Back to Patients", callback_data="doctor_patients")],
            ]
            await query.edit_message_text(f"Managing Patient {patient_id}", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data.startswith("doctor_patient_report_") and is_doctor(user_id):
            patient_id = _parse_suffix_int(data)
            patients = get_doctor_patients(user_id)
            if patient_id is None or not any(p["user_chat_id"] == patient_id for p in patients):
                await query.edit_message_text("Access denied.")
                return
            ok, report = get_report_for(patient_id)
            await query.edit_message_text(report if ok else "❌ " + report, parse_mode="HTML")
            return

        if data.startswith("doctor_patient_chart_") and is_doctor(user_id):
            patient_id = _parse_suffix_int(data)
            patients = get_doctor_patients(user_id)
            if patient_id is None or not any(p["user_chat_id"] == patient_id for p in patients):
                await query.edit_message_text("Access denied.")
                return
            await query.edit_message_text(
                f"📈 Select chart time period for patient {patient_id}:",
                reply_markup=_chart_period_keyboard("doctor_chart", patient_id, f"doctor_view_patient_{patient_id}"),
            )
            return

        if data.startswith("doctor_chart_") and is_doctor(user_id):
            parts = data.split("_")
            period = parts[2]
            hours = {"24h": 24, "48h": 48, "72h": 72, "week": 168}.get(period)
            patient_id = int(parts[3])
            patients = get_doctor_patients(user_id)
            if not any(p["user_chat_id"] == patient_id for p in patients):
                await query.edit_message_text("Access denied.")
                return
            if not hours:
                await query.edit_message_text("Invalid chart period.")
                return
            await send_chart_to_user(update, context, patient_id, max_hours=hours)
            return

        if data.startswith("doctor_start_patient_") and is_doctor(user_id):
            patient_id = _parse_suffix_int(data)
            patients = get_doctor_patients(user_id)
            if patient_id is None or not any(p["user_chat_id"] == patient_id for p in patients):
                await query.edit_message_text("Access denied.")
                return
            ok, msg = start_recording_for(patient_id)
            await query.edit_message_text(("✅ " if ok else "❌ ") + msg)
            return

        if data.startswith("doctor_stop_patient_") and is_doctor(user_id):
            patient_id = _parse_suffix_int(data)
            patients = get_doctor_patients(user_id)
            if patient_id is None or not any(p["user_chat_id"] == patient_id for p in patients):
                await query.edit_message_text("Access denied.")
                return
            ok, msg = stop_recording_for(patient_id)
            await query.edit_message_text(("✅ " if ok else "❌ ") + msg)
            return

        if data == "doctor_monitor_all" and is_doctor(user_id):
            patients = get_doctor_patients(user_id)
            if not patients:
                await query.edit_message_text("No patients assigned to you.")
                return

            lines = []
            for p in patients[:10]:
                pid = int(p["user_chat_id"])
                ok, snippet = get_report_for(pid)
                if ok:
                    name = html.escape(p.get("full_name", str(pid)))
                    status = next((line for line in snippet.split("\n") if "Status:" in line), "Status: Unknown")
                    lines.append(f"• <b>{name}</b> (ID {pid})\n{status}")
            if len(patients) > 10:
                lines.append("… (showing first 10 patients)")

            await query.edit_message_text("📊 Patient Status Overview:\n\n" + "\n\n".join(lines), parse_mode="HTML")
            return

        if data == "doctor_profile" and is_doctor(user_id):
            u = api_get(f"users/{user_id}") or {}
            patients = get_doctor_patients(user_id)
            profile = (
                "👨‍⚕️ <b>Doctor Profile</b>\n\n"
                f"<b>Name:</b> {html.escape(u.get('full_name', ''))}\n"
                f"<b>Specialization:</b> {html.escape(u.get('specialization', 'Not specified'))}\n"
                f"<b>Hospital:</b> {html.escape(u.get('hospital', 'Not specified'))}\n"
                f"<b>Patients:</b> {len(patients)}\n"
                f"<b>User ID:</b> {user_id}"
            )
            keyboard = [
                [InlineKeyboardButton("✏️ Edit Profile", callback_data="doctor_edit_profile")],
                [InlineKeyboardButton("⬅️ Back", callback_data="doctor_menu")],
            ]
            await query.edit_message_text(profile, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data == "doctor_edit_profile" and is_doctor(user_id):
            keyboard = [
                [InlineKeyboardButton("✏️ Edit Name", callback_data="edit_doctor_name")],
                [InlineKeyboardButton("🏥 Edit Specialization", callback_data="edit_doctor_specialization")],
                [InlineKeyboardButton("🏢 Edit Hospital", callback_data="edit_doctor_hospital")],
                [InlineKeyboardButton("⬅️ Back to Profile", callback_data="doctor_profile")],
            ]
            await query.edit_message_text("What would you like to edit?", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data == "edit_doctor_name" and is_doctor(user_id):
            await query.edit_message_text("Use:\n/update_doctor_name <Your New Name>")
            return

        if data == "edit_doctor_specialization" and is_doctor(user_id):
            await query.edit_message_text("Use:\n/update_doctor_specialization <Your Specialization>")
            return

        if data == "edit_doctor_hospital" and is_doctor(user_id):
            await query.edit_message_text("Use:\n/update_doctor_hospital <Hospital Name>")
            return

        # Admin features
        if data == "admin_start_all" and is_admin(user_id):
            users = api_get("users") or []
            patients = [u for u in users if u.get("user_type") == "patient"]
            started = sum(1 for p in patients if start_recording_for(int(p["user_chat_id"]))[0])
            await query.edit_message_text(f"▶️ Started for {started} patients. Failed: {len(patients) - started}.")
            return

        if data == "admin_stop_all" and is_admin(user_id):
            users = api_get("users") or []
            patients = [u for u in users if u.get("user_type") == "patient"]
            stopped = sum(1 for p in patients if stop_recording_for(int(p["user_chat_id"]))[0])
            await query.edit_message_text(f"⏹ Stopped for {stopped} patients. Failed: {len(patients) - stopped}.")
            return

        if data == "admin_monitor_all" and is_admin(user_id):
            users = api_get("users") or []
            patients = [u for u in users if u.get("user_type") == "patient"][:10]
            lines = []
            for p in patients:
                pid = int(p["user_chat_id"])
                ok, snippet = get_report_for(pid)
                if ok:
                    name = html.escape(p.get("full_name", str(pid)))
                    status = next((line for line in snippet.split("\n") if "Status:" in line), "Status: Unknown")
                    lines.append(f"• <b>{name}</b> (ID {pid})\n{status}")
            await query.edit_message_text("No reports found." if not lines else "\n\n".join(lines), parse_mode="HTML")
            return

        if data == "admin_user_list" and is_admin(user_id):
            users = api_get("users") or []
            if not users:
                await query.edit_message_text("No users found.")
                return
            keyboard = [
                [InlineKeyboardButton(f"{html.escape(u['full_name'])} (ID: {u['user_chat_id']})", callback_data=f"admin_user_{u['user_chat_id']}")]
                for u in users
            ]
            keyboard.append([InlineKeyboardButton("Back to Menu", callback_data="back_to_menu")])
            await query.edit_message_text(
                "👥 User list — choose one:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML",
            )
            return

        if data.startswith("admin_user_") and is_admin(user_id):
            target_id = _parse_suffix_int(data)
            user_target = api_get(f"users/{target_id}") if target_id else None
            if not user_target:
                await query.edit_message_text("User not found.")
                return

            if user_target.get("user_type") == "patient":
                keyboard = [
                    [InlineKeyboardButton("▶️ Start", callback_data=f"admin_start_user_{target_id}")],
                    [InlineKeyboardButton("⏹ Stop", callback_data=f"admin_stop_user_{target_id}")],
                    [InlineKeyboardButton("📄 Get report", callback_data=f"admin_get_report_{target_id}")],
                ]
                if CHARTS_AVAILABLE:
                    keyboard.append([InlineKeyboardButton("📈 Get chart", callback_data=f"admin_get_chart_{target_id}")])
                keyboard.append([InlineKeyboardButton("⬅️ Back to list", callback_data="admin_user_list")])
                await query.edit_message_text(
                    f"Managing: <b>{html.escape(user_target.get('full_name',''))}</b> (ID {target_id})",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="HTML",
                )
            else:
                keyboard = [
                    [InlineKeyboardButton("👥 View Doctor's Patients", callback_data=f"admin_doctor_patients_{target_id}")],
                    [InlineKeyboardButton("📊 Doctor Info", callback_data=f"admin_doctor_info_{target_id}")],
                    [InlineKeyboardButton("🗑️ Remove Doctor", callback_data=f"admin_delete_user_{target_id}")],
                    [InlineKeyboardButton("⬅️ Back to list", callback_data="admin_user_list")],
                ]
                await query.edit_message_text(
                    f"Managing Doctor: <b>{html.escape(user_target.get('full_name',''))}</b> (ID {target_id})\n"
                    f"Type: {user_target.get('user_type','unknown').title()}\n"
                    f"Specialization: {user_target.get('specialization','N/A')}\n"
                    f"Hospital: {user_target.get('hospital','N/A')}",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="HTML",
                )
            return

        if data.startswith("admin_start_user_") and is_admin(user_id):
            target_id = _parse_suffix_int(data)
            ok, msg = start_recording_for(target_id) if target_id else (False, "Invalid user.")
            await query.edit_message_text(f"User {target_id}: " + ("✅ " if ok else "❌ ") + msg)
            return

        if data.startswith("admin_stop_user_") and is_admin(user_id):
            target_id = _parse_suffix_int(data)
            ok, msg = stop_recording_for(target_id) if target_id else (False, "Invalid user.")
            await query.edit_message_text(f"User {target_id}: " + ("✅ " if ok else "❌ ") + msg)
            return

        if data.startswith("admin_get_report_") and is_admin(user_id):
            target_id = _parse_suffix_int(data)
            ok, text = get_report_for(target_id) if target_id else (False, "Invalid user.")
            await query.edit_message_text(
                (f"📄 Report for {target_id}:\n\n{text}" if ok else "❌ " + text),
                parse_mode="HTML",
            )
            return

        if data.startswith("admin_get_chart_") and is_admin(user_id):
            target_id = _parse_suffix_int(data)
            await query.edit_message_text(
                f"📈 Select chart time period for user {target_id}:",
                reply_markup=_chart_period_keyboard("admin_chart", int(target_id), f"admin_user_{target_id}"),
            )
            return

        if data.startswith("admin_chart_") and is_admin(user_id):
            parts = data.split("_")
            period = parts[2]
            hours = {"24h": 24, "48h": 48, "72h": 72, "week": 168}.get(period)
            target_id = int(parts[3])
            if not hours:
                await query.edit_message_text("Invalid chart period.")
                return
            await send_chart_to_user(update, context, target_id, max_hours=hours)
            return

        if data.startswith("admin_delete_user_") and is_admin(user_id):
            target_id = _parse_suffix_int(data)
            keyboard = [[
                InlineKeyboardButton("Yes, delete user", callback_data=f"confirm_admin_delete_{target_id}"),
                InlineKeyboardButton("Cancel", callback_data="admin_user_list"),
            ]]
            await query.edit_message_text(
                f"⚠️ Delete user {target_id} and all data?",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            return

        if data.startswith("confirm_admin_delete_") and is_admin(user_id):
            target_id = _parse_suffix_int(data)
            ok = api_delete(f"users/{target_id}") if target_id else False
            await query.edit_message_text(f"✅ User {target_id} deleted." if ok else "❌ Failed to delete user.")
            return

        if data.startswith("admin_doctor_patients_") and is_admin(user_id):
            doctor_id = _parse_suffix_int(data)
            doctor = api_get(f"users/{doctor_id}") if doctor_id else None
            if not doctor:
                await query.edit_message_text("Doctor not found.")
                return
            patients = get_doctor_patients(doctor_id)
            if not patients:
                await query.edit_message_text(f"Dr. {doctor.get('full_name','')} has no assigned patients.")
                return
            keyboard = [
                [InlineKeyboardButton(f"{p['full_name']} (ID: {p['user_chat_id']})", callback_data=f"admin_view_patient_{p['user_chat_id']}")]
                for p in patients
            ]
            keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data=f"admin_user_{doctor_id}")])
            await query.edit_message_text(
                f"👥 Dr. {doctor.get('full_name','')}'s Patients ({len(patients)}):",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            return

        if data.startswith("admin_doctor_info_") and is_admin(user_id):
            doctor_id = _parse_suffix_int(data)
            doctor = api_get(f"users/{doctor_id}") if doctor_id else None
            if not doctor:
                await query.edit_message_text("Doctor not found.")
                return
            patients = get_doctor_patients(doctor_id)
            info = (
                "👨‍⚕️ <b>Doctor Information</b>\n\n"
                f"<b>Name:</b> {html.escape(doctor.get('full_name',''))}\n"
                f"<b>ID:</b> {doctor_id}\n"
                f"<b>Specialization:</b> {html.escape(doctor.get('specialization','Not specified'))}\n"
                f"<b>Hospital:</b> {html.escape(doctor.get('hospital','Not specified'))}\n"
                f"<b>Assigned Patients:</b> {len(patients)}\n"
                f"<b>User Type:</b> {doctor.get('user_type','unknown').title()}"
            )
            keyboard = [
                [InlineKeyboardButton("👥 View Patients", callback_data=f"admin_doctor_patients_{doctor_id}")],
                [InlineKeyboardButton("🗑️ Remove Doctor", callback_data=f"admin_delete_user_{doctor_id}")],
                [InlineKeyboardButton("⬅️ Back", callback_data=f"admin_user_{doctor_id}")],
            ]
            await query.edit_message_text(info, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if data.startswith("admin_view_patient_") and is_admin(user_id):
            patient_id = _parse_suffix_int(data)
            patient = api_get(f"users/{patient_id}") if patient_id else None
            if not patient:
                await query.edit_message_text("Patient not found.")
                return
            keyboard = [
                [InlineKeyboardButton("▶️ Start Monitoring", callback_data=f"admin_start_user_{patient_id}")],
                [InlineKeyboardButton("⏹ Stop Monitoring", callback_data=f"admin_stop_user_{patient_id}")],
                [InlineKeyboardButton("📄 Get Report", callback_data=f"admin_get_report_{patient_id}")],
            ]
            if CHARTS_AVAILABLE:
                keyboard.append([InlineKeyboardButton("📈 Get Chart", callback_data=f"admin_get_chart_{patient_id}")])
            keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="admin_user_list")])
            await query.edit_message_text(
                f"Managing Patient: <b>{html.escape(patient.get('full_name',''))}</b> (ID {patient_id})",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML",
            )
            return

        await query.edit_message_text("Unknown action. Use /menu.")
        return

    except Exception as e:
        logger.error("Callback error: %s", e)
        logger.error(traceback.format_exc())
        try:
            await query.edit_message_text("❌ An error occurred. Please try again.")
        except Exception:
            pass


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Unhandled exception: %s", context.error)
    logger.error(traceback.format_exc())
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text("An error occurred. Please try again.")
    except Exception:
        pass


def build_app() -> Application:
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("menu", menu))

    app.add_handler(CommandHandler("register_doctor", register_doctor))
    app.add_handler(CommandHandler("update_doctor_name", update_doctor_name))
    app.add_handler(CommandHandler("update_doctor_specialization", update_doctor_specialization))
    app.add_handler(CommandHandler("update_doctor_hospital", update_doctor_hospital))

    # Device registration (conversation)
    device_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_device_registration, pattern="^register_new_device$")],
        states={DEVICE_TYPE: [CallbackQueryHandler(receive_device_type, pattern=r"^(devtype_|cancel_device_reg)")]},
        fallbacks=[CommandHandler("cancel", cancel_device_registration)],
    )
    app.add_handler(device_conv)

    # Single callback handler
    app.add_handler(CallbackQueryHandler(button_handler))

    app.add_error_handler(error_handler)
    return app


if __name__ == '__main__':
    # -------------------------
    # Bot configuration 
    # -------------------------
    bot_config = {
        'drop_pending_updates': True,
        'charts_enabled': CHARTS_AVAILABLE,
        'logging_level': 'INFO',
    }

    # -------------------------
    # Middleware / Tool 
    # -------------------------
    async def global_error_tool(update, context):
        import traceback
        logger.error("Unhandled exception: %s", context.error)
        logger.error(traceback.format_exc())
        try:
            if update and update.effective_message:
                await update.effective_message.reply_text("❌ An internal error occurred. Please try again.")
        except Exception:
            pass

    # -------------------------
    # Configuration dict 
    # -------------------------
    conf = {
        'commands': [
            "start",
            "register",
            "menu",
            "register_doctor",
            "update_doctor_name",
            "update_doctor_specialization",
            "update_doctor_hospital",
        ],
        'conversation_handlers': ['device_registration'],
        'callback_handler': 'button_handler',
        'error_handler': global_error_tool,
    }

    # -------------------------
    # Instantiate application 
    # -------------------------
    bot_app = build_app()

    # -------------------------
    # Start bot 
    # -------------------------
    logger.info("Telegram bot started (charts=%s)", CHARTS_AVAILABLE)
    bot_app.run_polling(drop_pending_updates=bot_config['drop_pending_updates'])

