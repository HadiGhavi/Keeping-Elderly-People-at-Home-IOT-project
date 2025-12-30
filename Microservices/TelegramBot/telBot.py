import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import html
import json
import requests
import logging
import traceback
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
)

from Microservices.Common.config import Config
from Microservices.Common.utils import ServiceRegistry

# =========================
# Charts 
# =========================
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import pandas as pd
    import io
    CHARTS_AVAILABLE = True
    print("✅ Chart libraries loaded successfully")
except ImportError as e:
    CHARTS_AVAILABLE = False
    print(f"⚠️ Chart libraries not available: {e}")
    print("Charts will be disabled. Install: pip install matplotlib pandas")

# =========================
# Logging
# =========================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("telegram_bot.log", mode="a")],
)
logger = logging.getLogger(__name__)

print("🤖 Starting Telegram Bot Service...")
print(f"Python version: {sys.version}")
print(f"Charts enabled: {CHARTS_AVAILABLE}")

# =========================
# Config / Services
# =========================
catalog_service = Config.SERVICES["catalog_url"]
TELEGRAM_TOKEN = Config.TELEGRAM_TOKEN
ADMINS = [int(uid) for uid in Config.ADMIN_USERS.keys()]

registry = ServiceRegistry()
database_service_url = registry.get_service_url("databaseAdapter")
monitoring_service_url = registry.get_service_url("monitor")  # kept for compatibility

# conversation states
DEVICE_TYPE = range(1)

# =========================
# REST helpers (same behavior, one place)
# =========================
def api_get(endpoint: str):
    try:
        url = f"{catalog_service}/{endpoint}"
        logger.info(f"API GET: {url}")
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json()
        logger.warning(f"API GET failed: {r.status_code} - {r.text}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"API GET error: {e}")
        return None

def api_post(endpoint: str, data: dict) -> bool:
    try:
        url = f"{catalog_service}/{endpoint}"
        logger.info(f"API POST: {url}")
        r = requests.post(url, json=data, timeout=10)
        ok = r.status_code in (200, 201)
        if not ok:
            logger.warning(f"API POST failed: {r.status_code} - {r.text}")
        return ok
    except requests.exceptions.RequestException as e:
        logger.error(f"API POST error: {e}")
        return False

def api_put(endpoint: str, data: dict) -> bool:
    try:
        url = f"{catalog_service}/{endpoint}"
        logger.info(f"API PUT: {url}")
        r = requests.put(url, json=data, timeout=10)
        ok = r.status_code == 200
        if not ok:
            logger.warning(f"API PUT failed: {r.status_code} - {r.text}")
        return ok
    except requests.exceptions.RequestException as e:
        logger.error(f"API PUT error: {e}")
        return False

def api_delete(endpoint: str) -> bool:
    try:
        url = f"{catalog_service}/{endpoint}"
        logger.info(f"API DELETE: {url}")
        r = requests.delete(url, timeout=10)
        ok = r.status_code == 200
        if not ok:
            logger.warning(f"API DELETE failed: {r.status_code} - {r.text}")
        return ok
    except requests.exceptions.RequestException as e:
        logger.error(f"API DELETE error: {e}")
        return False

# =========================
# Roles / helpers 
# =========================
def is_doctor(user_id: int) -> bool:
    user_data = api_get(f"users/{user_id}")
    return bool(user_data and user_data.get("user_type") == "doctor")

def is_admin(user_id: int) -> bool:
    if user_id in ADMINS:
        return True
    user_data = api_get(f"users/{user_id}")
    return bool(user_data and user_data.get("user_type") == "doctor")

def get_doctor_patients(doctor_id: int):
    return api_get(f"doctors/{doctor_id}") or []

# =========================
# Device management
# =========================
def get_device_types():
    return api_get("device_types") or []

def get_user_devices(user_id: int):
    return api_get(f"user_devices/{user_id}") or []

def register_new_device(device_id: str, device_type: str) -> bool:
    return api_post("devices", {"id": device_id, "type": device_type})

def assign_device_to_user(user_id: int, device_id: str) -> bool:
    return api_post(f"user_devices/{user_id}", {"device_id": device_id})

def remove_device_from_user(user_id: int, device_id: str) -> bool:
    return api_delete(f"user_devices/{user_id}/{device_id}")

# =========================
# Monitor service URL 
# =========================
def _sensor_service_url():
    svc = api_get("services/monitor")
    if not svc or "url" not in svc:
        logger.warning("Sensor service not found in catalog")
        return None

    url = svc["url"].rstrip("/")
    port = svc.get("port")
    full_url = f"{url}:{port}" if port else url
    logger.info(f"DEBUG: Sensor service full URL: {full_url}")
    return full_url

def start_recording_for(user_id: int):
    # unchanged: verify patient type using catalog direct
    try:
        user_response = requests.get(f"{catalog_service}/users/{user_id}", timeout=5)
        if user_response.status_code != 200:
            logger.warning(f"User {user_id} not found in catalog")
            return False, "User not found in the system."

        user_data = user_response.json()
        user_type = user_data.get("user_type", "")
        if user_type != "patient":
            logger.warning(f"Recording denied for user {user_id}: user type is '{user_type}', not 'patient'")
            return False, "Recording is only available for patients."
    except Exception as e:
        logger.error(f"Error checking user type for {user_id}: {e}")
        return False, "Failed to verify user type."

    base_url = _sensor_service_url()
    if not base_url:
        return False, "Sensor service not found."

    try:
        url = f"{base_url}/read/{user_id}"
        logger.info(f"Starting recording for user {user_id} at {url}")
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return True, "Recording started."
        logger.warning(f"Start recording failed: {r.status_code} - {r.text}")
    except Exception as e:
        logger.error(f"Start recording error: {e}")

    return False, "Failed to start recording."

def stop_recording_for(user_id: int):
    base = _sensor_service_url()
    if not base:
        return False, "Sensor service not found."

    try:
        # same normalization as your file
        if base.endswith("/read/"):
            base_url = base[:-6]
        elif base.endswith("/read"):
            base_url = base[:-5]
        else:
            base_url = base

        url = f"{base_url}/stop/{user_id}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return True, "Recording stopped successfully."
        return False, f"Failed to stop (HTTP {r.status_code}): {r.text[:100]}"
    except Exception as e:
        return False, f"Error while stopping: {str(e)}"

# =========================
# Reports
# =========================
def get_report_for(user_id: int, max_hours: int = 24):
    try:
        params = {"hours": max_hours}
        full_url = f"{database_service_url}/read/{user_id}"
        logger.info(f"Fetching report from database adapter: {full_url} (last {max_hours} hours)")
        response = requests.get(full_url, params=params, timeout=15)

        if response.status_code != 200:
            logger.warning(f"Report fetch failed: {response.status_code} - {response.text}")
            return False, f"Failed to fetch report (HTTP {response.status_code})."

        raw_data = response.json()
        if not raw_data:
            return True, "No report found."

        if isinstance(raw_data, dict) and not raw_data.get("success", True):
            error_message = raw_data.get("message", "Unknown error from database adapter")
            logger.error(f"Database adapter error: {error_message}")
            return False, f"Database error: {error_message}"

        data = raw_data["data"] if isinstance(raw_data, dict) and "data" in raw_data else raw_data
        if isinstance(data, str):
            data = json.loads(data)

        if not data:
            return True, "No report data found for this user."

        return True, format_health_report(data, user_id)

    except json.JSONDecodeError as e:
        logger.error(f"Error parsing report JSON: {e}")
        return False, "Error parsing report data."
    except Exception as e:
        logger.error(f"Unexpected error fetching report: {e}")
        return False, "Unexpected error while fetching report."

def format_health_report(data, user_id):
    if not data:
        return "No health data available."

    from collections import defaultdict
    grouped_data = defaultdict(dict)

    for entry in data:
        timestamp = entry.get("time", "Unknown time")
        field = entry.get("field", "unknown")
        value = entry.get("value", "N/A")

        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+02:00"))
            formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            formatted_time = timestamp

        grouped_data[formatted_time][field] = value

    report_lines = [f"<b>Health Report - User {user_id}</b>\n"]
    sorted_times = sorted(grouped_data.keys(), reverse=True)

    for time_key in sorted_times[:10]:
        reading = grouped_data[time_key]
        temp = reading.get("temp", "N/A")
        hr = reading.get("heart_rate", "N/A")
        oxygen = reading.get("oxygen", "N/A")
        state = reading.get("state", "N/A")

        status_emoji = {"healthy": "✅", "risky": "⚠️", "dangerous": "🚨"}.get(state, "❓")

        report_lines += [
            f"<b>📅 {time_key}</b>",
            f"{status_emoji} Status: <b>{state}</b>",
            f"🌡️ Temperature: {temp}°C",
            f"❤️ Heart Rate: {hr} BPM",
            f"🫁 Oxygen: {oxygen}%",
            "",
        ]

    if len(sorted_times) > 10:
        report_lines.append(f"... and {len(sorted_times) - 10} more readings")

    return "\n".join(report_lines)

# =========================
# Charts 
# =========================
def get_aggregated_chart_data_for(user_id: int, max_hours: int = 24):
    if not CHARTS_AVAILABLE:
        return False, "Chart functionality not available - missing dependencies.", None

    try:
        params = {"hours": max_hours}
        full_url = f"{database_service_url}/aggregated/{user_id}"
        logger.info(f"Fetching aggregated chart data: {full_url} (last {max_hours} hours)")

        response = requests.get(full_url, params=params, timeout=15)
        if response.status_code != 200:
            logger.warning(f"Aggregated data fetch failed: {response.status_code} - {response.text}")
            return False, f"Failed to fetch aggregated data (HTTP {response.status_code}).", None

        result = response.json()
        if not result.get("success", False):
            error_message = result.get("message", "Unknown error from database adapter")
            logger.error(f"Database adapter error: {error_message}")
            return False, f"Database error: {error_message}", None

        data = result.get("data", [])
        if not data:
            return True, f"No aggregated data found for the last {max_hours} hours.", None

        return True, "Aggregated data retrieved successfully.", {
            "data": data,
            "sample_info": result.get("sample_info", "aggregated data"),
            "aggregation_frequency": result.get("aggregation_frequency", "unknown"),
        }
    except Exception as e:
        logger.error(f"Unexpected error fetching aggregated data: {e}")
        return False, "Unexpected error while fetching aggregated data.", None

def generate_chart_for(user_id: int, chart_type: str = "combined", max_hours: int = 24):
    if not CHARTS_AVAILABLE:
        return False, "Chart functionality not available - missing dependencies.", None

    ok, msg, result = get_aggregated_chart_data_for(user_id, max_hours)
    if not ok or not result:
        return False, msg, None

    try:
        aggregated_data = result["data"]
        sample_info = result["sample_info"]

        agg_df = pd.DataFrame(aggregated_data)
        agg_df["time"] = pd.to_datetime(agg_df["time"])

        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        time_range_text = f"Last {max_hours} hours" if max_hours < 48 else f"Last {max_hours//24} days"
        fig.suptitle(
            f"Health Monitoring Dashboard - User {user_id} ({time_range_text})\n{sample_info}",
            fontsize=16,
            fontweight="bold",
        )

        # temp
        temp_data = agg_df[agg_df["field"] == "temp"].copy()
        if not temp_data.empty:
            temp_data["value"] = pd.to_numeric(temp_data["value"], errors="coerce")
            temp_data["min_value"] = pd.to_numeric(temp_data["min_value"], errors="coerce")
            temp_data["max_value"] = pd.to_numeric(temp_data["max_value"], errors="coerce")
            temp_data = temp_data.dropna()
            if not temp_data.empty:
                axes[0, 0].plot(temp_data["time"], temp_data["value"], "r-", linewidth=2, label="Average")
                axes[0, 0].fill_between(temp_data["time"], temp_data["min_value"], temp_data["max_value"], alpha=0.2, color="red", label="Range")
                axes[0, 0].set_title("Body Temperature (°C)", fontweight="bold")
                axes[0, 0].set_ylabel("Temperature (°C)")
                axes[0, 0].grid(True, alpha=0.3)
                axes[0, 0].legend()

        # heart rate
        hr_data = agg_df[agg_df["field"] == "heart_rate"].copy()
        if not hr_data.empty:
            hr_data["value"] = pd.to_numeric(hr_data["value"], errors="coerce")
            hr_data["min_value"] = pd.to_numeric(hr_data["min_value"], errors="coerce")
            hr_data["max_value"] = pd.to_numeric(hr_data["max_value"], errors="coerce")
            hr_data = hr_data.dropna()
            if not hr_data.empty:
                axes[0, 1].plot(hr_data["time"], hr_data["value"], "g-", linewidth=2, label="Average")
                axes[0, 1].fill_between(hr_data["time"], hr_data["min_value"], hr_data["max_value"], alpha=0.2, color="green", label="Range")
                axes[0, 1].set_title("Heart Rate (BPM)", fontweight="bold")
                axes[0, 1].set_ylabel("BPM")
                axes[0, 1].grid(True, alpha=0.3)
                axes[0, 1].legend()

        # oxygen
        oxygen_data = agg_df[agg_df["field"] == "oxygen"].copy()
        if not oxygen_data.empty:
            oxygen_data["value"] = pd.to_numeric(oxygen_data["value"], errors="coerce")
            oxygen_data["min_value"] = pd.to_numeric(oxygen_data["min_value"], errors="coerce")
            oxygen_data["max_value"] = pd.to_numeric(oxygen_data["max_value"], errors="coerce")
            oxygen_data = oxygen_data.dropna()
            if not oxygen_data.empty:
                axes[1, 0].plot(oxygen_data["time"], oxygen_data["value"], "b-", linewidth=2, label="Average")
                axes[1, 0].fill_between(oxygen_data["time"], oxygen_data["min_value"], oxygen_data["max_value"], alpha=0.2, color="blue", label="Range")
                axes[1, 0].set_title("Oxygen Saturation (%)", fontweight="bold")
                axes[1, 0].set_ylabel("SpO2 (%)")
                axes[1, 0].grid(True, alpha=0.3)
                axes[1, 0].legend()

        # state
        state_data = agg_df[agg_df["field"] == "state"].copy()
        if not state_data.empty:
            state_mapping = {"healthy": 0, "risky": 1, "dangerous": 2}
            state_colors = {"healthy": "green", "risky": "orange", "dangerous": "red"}
            state_data["state_num"] = state_data["value"].map(state_mapping)
            state_data = state_data.dropna(subset=["state_num"])
            if not state_data.empty:
                colors = [state_colors.get(s, "gray") for s in state_data["value"]]
                axes[1, 1].scatter(state_data["time"], state_data["state_num"], c=colors, s=50, alpha=0.8)
                axes[1, 1].set_title("Health State (Weighted Priority)", fontweight="bold")
                axes[1, 1].set_ylabel("State")
                axes[1, 1].set_yticks([0, 1, 2])
                axes[1, 1].set_yticklabels(["Healthy", "Risky", "Dangerous"])
                axes[1, 1].grid(True, alpha=0.3)

        for ax in axes.flat:
            if len(ax.get_lines()) > 0 or len(ax.collections) > 0:
                if max_hours <= 24:
                    ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
                    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
                elif max_hours <= 48:
                    ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
                    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d %H:%M"))
                elif max_hours <= 72:
                    ax.xaxis.set_major_locator(mdates.HourLocator(interval=4))
                    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d %H:%M"))
                else:
                    ax.xaxis.set_major_locator(mdates.HourLocator(interval=12))
                    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d %H:%M"))

                ax.tick_params(axis="x", rotation=45, labelsize=9)

        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        buf.seek(0)
        plt.close()
        return True, "Chart generated successfully using server-side aggregation.", buf
    except Exception as e:
        logger.error(f"Error generating chart from aggregated data: {e}")
        logger.error(traceback.format_exc())
        return False, f"Chart generation failed: {str(e)}", None

async def send_chart_to_user(update, context, user_id: int, max_hours: int = 24):
    if not CHARTS_AVAILABLE:
        await update.callback_query.edit_message_text("Chart functionality disabled - missing matplotlib/pandas dependencies")
        return

    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
        ok, msg, chart_buffer = generate_chart_for(user_id, max_hours=max_hours)
        if not ok or not chart_buffer:
            await update.callback_query.edit_message_text(f"❌ {msg}")
            return

        if max_hours == 24:
            period_text = "24 hours"
        elif max_hours == 48:
            period_text = "48 hours"
        elif max_hours == 72:
            period_text = "72 hours"
        elif max_hours == 168:
            period_text = "1 week"
        else:
            period_text = f"{max_hours} hours"

        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=chart_buffer,
            caption=(
                f"📊 Health monitoring chart for user {user_id} (Last {period_text})\n"
                f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            ),
        )

        await update.callback_query.edit_message_text("✅ Chart sent successfully!")
    except Exception as e:
        logger.error(f"Error sending chart: {e}")
        logger.error(traceback.format_exc())
        await update.callback_query.edit_message_text(f"❌ Failed to send chart: {str(e)}")

# =========================
# UI helpers 
# =========================
def build_menu_keyboard(user_data: dict, chat_id: int) -> tuple[str, InlineKeyboardMarkup]:
    if user_data.get("user_type") == "doctor":
        keyboard = [
            [InlineKeyboardButton("👥 My Patients", callback_data="doctor_patients")],
            [InlineKeyboardButton("📊 Monitor All Patients", callback_data="doctor_monitor_all")],
            [InlineKeyboardButton("👤 My Profile", callback_data="doctor_profile")],
        ]
        return "👨‍⚕️ Doctor Menu:", InlineKeyboardMarkup(keyboard)

    if chat_id in ADMINS:
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
        return "🛠 Admin Menu:", InlineKeyboardMarkup(keyboard)

    keyboard = [
        [InlineKeyboardButton("📱 My Devices", callback_data="my_devices")],
        [InlineKeyboardButton("▶️ Start monitoring", callback_data="start_recording")],
        [InlineKeyboardButton("📄 Get report", callback_data="get_report")],
        [InlineKeyboardButton("👨‍⚕️ Assign Doctor", callback_data="assign_doctor")],
    ]
    if CHARTS_AVAILABLE:
        keyboard.append([InlineKeyboardButton("📈 Get chart", callback_data="get_chart")])
    keyboard.extend([
        [InlineKeyboardButton("⏹ Stop monitoring", callback_data="stop_recording")],
        [InlineKeyboardButton("🗑 Remove profile", callback_data="delete_profile")],
    ])
    return "📋 Patient Menu:", InlineKeyboardMarkup(keyboard)

def build_chart_period_keyboard(prefix: str, target_id: int, back_cb: str) -> InlineKeyboardMarkup:
    # IMPORTANT: preserves your callback formats exactly
    # get_chart_24h_{id} / doctor_chart_24h_{id} / admin_chart_24h_{id}
    if prefix == "get_chart":
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Last 24 hours", callback_data=f"get_chart_24h_{target_id}")],
            [InlineKeyboardButton("📊 Last 48 hours", callback_data=f"get_chart_48h_{target_id}")],
            [InlineKeyboardButton("📊 Last 72 hours", callback_data=f"get_chart_72h_{target_id}")],
            [InlineKeyboardButton("📊 Last week", callback_data=f"get_chart_week_{target_id}")],
            [InlineKeyboardButton("❌ Back to Menu", callback_data=back_cb)],
        ])
    if prefix == "doctor_chart":
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Last 24 hours", callback_data=f"doctor_chart_24h_{target_id}")],
            [InlineKeyboardButton("📊 Last 48 hours", callback_data=f"doctor_chart_48h_{target_id}")],
            [InlineKeyboardButton("📊 Last 72 hours", callback_data=f"doctor_chart_72h_{target_id}")],
            [InlineKeyboardButton("📊 Last week", callback_data=f"doctor_chart_week_{target_id}")],
            [InlineKeyboardButton("❌ Back", callback_data=back_cb)],
        ])
    if prefix == "admin_chart":
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Last 24 hours", callback_data=f"admin_chart_24h_{target_id}")],
            [InlineKeyboardButton("📊 Last 48 hours", callback_data=f"admin_chart_48h_{target_id}")],
            [InlineKeyboardButton("📊 Last 72 hours", callback_data=f"admin_chart_72h_{target_id}")],
            [InlineKeyboardButton("📊 Last week", callback_data=f"admin_chart_week_{target_id}")],
            [InlineKeyboardButton("❌ Back", callback_data=back_cb)],
        ])
    # fallback
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=back_cb)]])

async def render_menu_to_query(query, user_data: dict, chat_id: int):
    text, markup = build_menu_keyboard(user_data, chat_id)
    await query.edit_message_text(text, reply_markup=markup)

# =========================
# Device registration conversation 
# =========================
async def start_device_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    device_types = get_device_types()
    if not device_types:
        await query.edit_message_text("Error: Could not retrieve device types. Please try again later.")
        return ConversationHandler.END

    keyboard = []
    for dtype in device_types:
        display_name = dtype.replace("_", " ").title()
        keyboard.append([InlineKeyboardButton(display_name, callback_data=f"devtype_{dtype}")])
    keyboard.append([InlineKeyboardButton("Cancel", callback_data="cancel_device_reg")])

    await query.edit_message_text(
        "📱 <b>Device Registration</b>\n\n"
        "Select the type of device you want to register:\n\n"
        "<i>The device ID will be automatically generated.</i>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )
    return DEVICE_TYPE

async def receive_device_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel_device_reg":
        await query.edit_message_text("Device registration cancelled.")
        return ConversationHandler.END

    device_type = query.data.replace("devtype_", "")
    chat_id = query.message.chat_id

    import time
    device_id = f"{device_type}_{chat_id}_{int(time.time())}"

    if not register_new_device(device_id, device_type):
        await query.edit_message_text("Failed to register device. Please try again.\n\nUse /menu to continue.")
        return ConversationHandler.END

    if not assign_device_to_user(chat_id, device_id):
        await query.edit_message_text("Device registered but failed to assign to your account.\n\nPlease contact support.")
        return ConversationHandler.END

    device_type_display = device_type.replace("_", " ").title()
    await query.edit_message_text(
        f"<b>Device Registered Successfully!</b>\n\n"
        f"📱 Device ID: <code>{html.escape(device_id)}</code>\n"
        f"📋 Type: {device_type_display}\n\n"
        f"Your device is now active and will be monitored.\n"
        f"Use /menu to continue.",
        parse_mode="HTML",
    )
    return ConversationHandler.END

async def cancel_device_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Device registration cancelled.")
    return ConversationHandler.END

# =========================
# Commands 
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id
        user = api_get(f"users/{chat_id}")
        if user:
            await update.message.reply_text(f"👋 Welcome back, {html.escape(user['full_name'])}!\nUse /menu.")
        else:
            await update.message.reply_text(
                "🏥 Welcome to Human Health Monitoring!\n\n"
                "Please register with your full name using:\n"
                "/register <your full name>"
            )
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        logger.error(traceback.format_exc())

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id
        if len(context.args) < 1:
            await update.message.reply_text("Please provide your full name: /register <your name>")
            return

        full_name = " ".join(context.args)
        if api_post("users", {"user_chat_id": chat_id, "full_name": full_name}):
            await update.message.reply_text(
                f"✅ Registered, {html.escape(full_name)}.\n\n"
                "Next step: Register your health monitoring devices using /menu → My Devices."
            )
        else:
            await update.message.reply_text("❌ Registration failed. Try again.")
    except Exception as e:
        logger.error(f"Error in register command: {e}")
        logger.error(traceback.format_exc())

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id
        user_data = api_get(f"users/{chat_id}")
        if not user_data:
            await update.message.reply_text("Please register first with /register <your name>")
            return
        text, markup = build_menu_keyboard(user_data, chat_id)
        await update.message.reply_text(text, reply_markup=markup)
    except Exception as e:
        logger.error(f"Error in menu command: {e}")
        logger.error(traceback.format_exc())

# =========================
# Doctor registration/update commands 
# =========================
async def register_doctor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id

        if len(context.args) < 2:
            await update.message.reply_text(
                "Register as doctor:\n/register_doctor <Full Name> <Specialization> [Hospital]"
            )
            return

        if len(context.args) >= 3:
            full_name = " ".join(context.args[:-2])
            specialization = context.args[-2]
            hospital = context.args[-1]
        else:
            full_name = context.args[0]
            specialization = context.args[1]
            hospital = ""

        doctor_data = {"user_chat_id": chat_id, "full_name": full_name, "specialization": specialization, "hospital": hospital}
        if api_post("doctors", doctor_data):
            await update.message.reply_text("✅ Successfully registered as doctor!\nUse /menu to access doctor functions.")
        else:
            await update.message.reply_text("❌ Registration failed.")
    except Exception as e:
        logger.error(f"Error in doctor registration: {e}")
        await update.message.reply_text("Registration failed. Please try again.")

async def update_doctor_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id
        if not is_doctor(chat_id):
            await update.message.reply_text("This command is only available for doctors.")
            return
        if len(context.args) < 1:
            await update.message.reply_text("Usage: /update_doctor_name <Your New Name>")
            return

        user_data = api_get(f"users/{chat_id}")
        if not user_data:
            await update.message.reply_text("❌ Could not retrieve your profile.")
            return
        user_data["full_name"] = " ".join(context.args)

        await update.message.reply_text("✅ Name updated." if api_put(f"users/{chat_id}", user_data) else "❌ Update failed.")
    except Exception as e:
        logger.error(f"Error updating doctor name: {e}")
        await update.message.reply_text("Update failed. Please try again.")

async def update_doctor_specialization(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id
        if not is_doctor(chat_id):
            await update.message.reply_text("This command is only available for doctors.")
            return
        if len(context.args) < 1:
            await update.message.reply_text("Usage: /update_doctor_specialization <Specialization>")
            return

        user_data = api_get(f"users/{chat_id}")
        if not user_data:
            await update.message.reply_text("❌ Could not retrieve your profile.")
            return
        user_data["specialization"] = " ".join(context.args)

        await update.message.reply_text("✅ Specialization updated." if api_put(f"users/{chat_id}", user_data) else "❌ Update failed.")
    except Exception as e:
        logger.error(f"Error updating doctor specialization: {e}")
        await update.message.reply_text("Update failed. Please try again.")

async def update_doctor_hospital(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id
        if not is_doctor(chat_id):
            await update.message.reply_text("This command is only available for doctors.")
            return
        if len(context.args) < 1:
            await update.message.reply_text("Usage: /update_doctor_hospital <Hospital Name>")
            return

        user_data = api_get(f"users/{chat_id}")
        if not user_data:
            await update.message.reply_text("❌ Could not retrieve your profile.")
            return
        user_data["hospital"] = " ".join(context.args)

        await update.message.reply_text("✅ Hospital updated." if api_put(f"users/{chat_id}", user_data) else "❌ Update failed.")
    except Exception as e:
        logger.error(f"Error updating doctor hospital: {e}")
        await update.message.reply_text("Update failed. Please try again.")

# =========================
# Callback handler 
# =========================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
        chat_id = query.message.chat_id
        logger.info(f"Button pressed: {query.data} by user {chat_id}")

        user = api_get(f"users/{chat_id}")
        if not user:
            await query.edit_message_text("Please register first with /register <your name>")
            return ConversationHandler.END

        admin_mode = is_admin(chat_id)

        # ---- Device Management ----
        if query.data == "register_new_device":
            await start_device_registration(update, context)
            return

        elif query.data == "my_devices":
            devices = get_user_devices(chat_id)
            if not devices:
                keyboard = [[InlineKeyboardButton("➕ Register New Device", callback_data="register_new_device")]]
                await query.edit_message_text(
                    "📱 You don't have any devices registered yet.\n\nRegister your first device to start monitoring your health!",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
                return

            device_lines = ["📱 <b>Your Registered Devices:</b>\n"]
            for device in devices:
                device_type = device.get("type", "unknown").replace("_", " ").title()
                device_id = device.get("id", "unknown")
                last_update = device.get("last_update", "Never")
                device_lines.append(
                    f"• <b>{device_type}</b>\n"
                    f"  ID: <code>{html.escape(device_id)}</code>\n"
                    f"  Last Update: {last_update}\n"
                )

            keyboard = [
                [InlineKeyboardButton("➕ Register New Device", callback_data="register_new_device")],
                [InlineKeyboardButton("🗑 Remove Device", callback_data="remove_device_menu")],
                [InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_to_menu")],
            ]
            await query.edit_message_text("\n".join(device_lines), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

        elif query.data == "remove_device_menu":
            devices = get_user_devices(chat_id)
            if not devices:
                await query.edit_message_text("You don't have any devices to remove.")
                return

            keyboard = []
            for device in devices:
                device_type = device.get("type", "unknown").replace("_", " ").title()
                device_id = device.get("id", "unknown")
                keyboard.append([InlineKeyboardButton(f"🗑 {device_type} ({device_id})", callback_data=f"confirm_remove_device_{device_id}")])
            keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="my_devices")])

            await query.edit_message_text("🗑 Select a device to remove:", reply_markup=InlineKeyboardMarkup(keyboard))

        elif query.data.startswith("confirm_remove_device_"):
            device_id = query.data.replace("confirm_remove_device_", "")
            if remove_device_from_user(chat_id, device_id):
                await query.edit_message_text(f"✅ Device removed successfully!\n\nDevice ID: {device_id}\n\nUse /menu to continue.")
            else:
                await query.edit_message_text("❌ Failed to remove device. Please try again.")

        elif query.data == "back_to_menu":
            await render_menu_to_query(query, user, chat_id)
            return

        # ---- Patient controls ----
        if query.data == "start_recording":
            ok, msg = start_recording_for(chat_id)
            await query.edit_message_text(("✅ " if ok else "❌ ") + msg)

        elif query.data == "stop_recording":
            ok, msg = stop_recording_for(chat_id)
            await query.edit_message_text(("✅ " if ok else "❌ ") + msg)

        elif query.data == "get_report":
            ok, text = get_report_for(chat_id)
            await query.edit_message_text(text if ok else "❌ " + text, parse_mode="HTML")

        elif query.data == "get_chart":
            await query.edit_message_text("📈 Select chart time period:", reply_markup=build_chart_period_keyboard("get_chart", chat_id, "back_to_menu"))

        elif query.data.startswith("get_chart_24h_"):
            user_id = int(query.data.split("_")[-1])
            await send_chart_to_user(update, context, user_id, max_hours=24)

        elif query.data.startswith("get_chart_48h_"):
            user_id = int(query.data.split("_")[-1])
            await send_chart_to_user(update, context, user_id, max_hours=48)

        elif query.data.startswith("get_chart_72h_"):
            user_id = int(query.data.split("_")[-1])
            await send_chart_to_user(update, context, user_id, max_hours=72)

        elif query.data.startswith("get_chart_week_"):
            user_id = int(query.data.split("_")[-1])
            await send_chart_to_user(update, context, user_id, max_hours=168)

        elif query.data == "delete_profile":
            keyboard = [[
                InlineKeyboardButton("Yes, delete my data", callback_data=f"confirm_delete_{chat_id}"),
                InlineKeyboardButton("Cancel", callback_data="cancel_delete"),
            ]]
            await query.edit_message_text("⚠️ Are you sure you want to delete your profile and all data?", reply_markup=InlineKeyboardMarkup(keyboard))

        elif query.data.startswith("confirm_delete_"):
            target_user = int(query.data.split("_")[-1])
            await query.edit_message_text("✅ Your profile and all data have been deleted." if api_delete(f"users/{target_user}") else "❌ Failed to delete profile.")

        elif query.data == "cancel_delete":
            await query.edit_message_text("Profile deletion cancelled.")

        # ---- Assign doctor ----
        elif query.data == "assign_doctor":
            user_data = api_get(f"users/{chat_id}")
            current_doctor_id = user_data.get("doctor_id") if user_data else None
            doctors = api_get("doctors") or []
            if not doctors:
                await query.edit_message_text("No doctors are currently registered in the system. Please contact system administrator.")
                return

            header_text = "You don't have a doctor assigned yet.\n\nSelect a doctor:\n"
            if current_doctor_id:
                current_doctor = next((d for d in doctors if d["user_chat_id"] == current_doctor_id), None)
                if current_doctor:
                    header_text = (
                        f"Currently assigned to: <b>Dr. {html.escape(current_doctor['full_name'])}</b>\n"
                        f"Specialization: {html.escape(current_doctor.get('specialization', 'Not specified'))}\n\n"
                        "Select a new doctor to change, or cancel to keep current doctor:\n"
                    )
                else:
                    header_text = (
                        f"You have a doctor assigned (ID: {current_doctor_id}), but their profile is not available.\n\n"
                        "Select a new doctor:\n"
                    )

            keyboard = []
            for doctor in doctors:
                doctor_info = f"Dr. {doctor['full_name']}"
                if "specialization" in doctor:
                    doctor_info += f" ({doctor['specialization']})"
                if current_doctor_id and doctor["user_chat_id"] == current_doctor_id:
                    doctor_info += " [Current]"
                keyboard.append([InlineKeyboardButton(doctor_info, callback_data=f"select_doctor_{doctor['user_chat_id']}")])
            keyboard.append([InlineKeyboardButton("Back to menu", callback_data="back_to_menu")])

            await query.edit_message_text(header_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

        elif query.data.startswith("select_doctor_"):
            doctor_id = int(query.data.split("_")[-1])
            user_data = api_get(f"users/{chat_id}")
            current_doctor_id = user_data.get("doctor_id") if user_data else None

            if current_doctor_id == doctor_id:
                await query.edit_message_text("You are already assigned to this doctor.\n\nUse /menu to continue.")
                return

            assignment_data = {"patient_id": chat_id, "doctor_id": doctor_id}
            if api_post("assign_patient", assignment_data):
                doctor = api_get(f"users/{doctor_id}")
                doctor_name = doctor.get("full_name", "Unknown") if doctor else "Unknown"
                if current_doctor_id:
                    msg = (
                        "Doctor changed successfully!\n\n"
                        f"You are now assigned to {doctor_name}.\n\n"
                        "Use /menu to continue."
                    )
                else:
                    msg = (
                        f"You have been assigned to {doctor_name}.\n\n"
                        "Use /menu to continue."
                    )
                await query.edit_message_text(msg)
            else:
                await query.edit_message_text("Failed to assign doctor. Please try again.")

        # ---- Doctor flows ----
        elif query.data == "doctor_patients" and is_doctor(chat_id):
            patients = get_doctor_patients(chat_id)
            if not patients:
                await query.edit_message_text("No patients assigned to you yet.")
                return

            keyboard = [[InlineKeyboardButton(f"{p['full_name']} (ID: {p['user_chat_id']})", callback_data=f"doctor_view_patient_{p['user_chat_id']}")] for p in patients]
            keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="doctor_menu")])
            await query.edit_message_text(f"👥 Your Patients ({len(patients)}):", reply_markup=InlineKeyboardMarkup(keyboard))

        elif query.data.startswith("doctor_view_patient_") and is_doctor(chat_id):
            patient_id = int(query.data.split("_")[-1])
            doctor_patients = get_doctor_patients(chat_id)
            patient = next((p for p in doctor_patients if p["user_chat_id"] == patient_id), None)
            if not patient:
                await query.edit_message_text("Access denied - patient not assigned to you.")
                return

            keyboard = [
                [InlineKeyboardButton("📄 View Report", callback_data=f"doctor_patient_report_{patient_id}")],
                [InlineKeyboardButton("📈 View Chart", callback_data=f"doctor_patient_chart_{patient_id}")],
                [InlineKeyboardButton("▶️ Start Monitoring", callback_data=f"doctor_start_patient_{patient_id}")],
                [InlineKeyboardButton("⏹ Stop Monitoring", callback_data=f"doctor_stop_patient_{patient_id}")],
                [InlineKeyboardButton("⬅️ Back to Patients", callback_data="doctor_patients")],
            ]
            await query.edit_message_text(f"Managing Patient: {patient['full_name']}", reply_markup=InlineKeyboardMarkup(keyboard))

        elif query.data.startswith("doctor_patient_report_") and is_doctor(chat_id):
            patient_id = int(query.data.split("_")[-1])
            if not any(p["user_chat_id"] == patient_id for p in get_doctor_patients(chat_id)):
                await query.edit_message_text("Access denied - patient not assigned to you.")
                return
            ok, report = get_report_for(patient_id)
            await query.edit_message_text((f"📄 Patient Report (ID: {patient_id}):\n\n{report}" if ok else f"❌ Failed to get report: {report}"), parse_mode="HTML")

        elif query.data.startswith("doctor_patient_chart_") and is_doctor(chat_id):
            patient_id = int(query.data.split("_")[-1])
            if not any(p["user_chat_id"] == patient_id for p in get_doctor_patients(chat_id)):
                await query.edit_message_text("Access denied - patient not assigned to you.")
                return
            await query.edit_message_text(
                f"📈 Select chart time period for patient {patient_id}:",
                reply_markup=build_chart_period_keyboard("doctor_chart", patient_id, f"doctor_view_patient_{patient_id}"),
            )

        elif query.data.startswith("doctor_chart_24h_") and is_doctor(chat_id):
            patient_id = int(query.data.split("_")[-1])
            if any(p["user_chat_id"] == patient_id for p in get_doctor_patients(chat_id)):
                await send_chart_to_user(update, context, patient_id, max_hours=24)
            else:
                await query.edit_message_text("Access denied.")

        elif query.data.startswith("doctor_chart_48h_") and is_doctor(chat_id):
            patient_id = int(query.data.split("_")[-1])
            if any(p["user_chat_id"] == patient_id for p in get_doctor_patients(chat_id)):
                await send_chart_to_user(update, context, patient_id, max_hours=48)
            else:
                await query.edit_message_text("Access denied.")

        elif query.data.startswith("doctor_chart_72h_") and is_doctor(chat_id):
            patient_id = int(query.data.split("_")[-1])
            if any(p["user_chat_id"] == patient_id for p in get_doctor_patients(chat_id)):
                await send_chart_to_user(update, context, patient_id, max_hours=72)
            else:
                await query.edit_message_text("Access denied.")

        elif query.data.startswith("doctor_chart_week_") and is_doctor(chat_id):
            patient_id = int(query.data.split("_")[-1])
            if any(p["user_chat_id"] == patient_id for p in get_doctor_patients(chat_id)):
                await send_chart_to_user(update, context, patient_id, max_hours=168)
            else:
                await query.edit_message_text("Access denied.")

        elif query.data.startswith("doctor_start_patient_") and is_doctor(chat_id):
            patient_id = int(query.data.split("_")[-1])
            if not any(p["user_chat_id"] == patient_id for p in get_doctor_patients(chat_id)):
                await query.edit_message_text("Access denied - patient not assigned to you.")
                return
            ok, msg = start_recording_for(patient_id)
            await query.edit_message_text(f"Patient {patient_id}: " + (("✅ " if ok else "❌ ") + msg))

        elif query.data.startswith("doctor_stop_patient_") and is_doctor(chat_id):
            patient_id = int(query.data.split("_")[-1])
            if not any(p["user_chat_id"] == patient_id for p in get_doctor_patients(chat_id)):
                await query.edit_message_text("Access denied - patient not assigned to you.")
                return
            ok, msg = stop_recording_for(patient_id)
            await query.edit_message_text(f"Patient {patient_id}: " + (("✅ " if ok else "❌ ") + msg))

        elif query.data == "doctor_monitor_all" and is_doctor(chat_id):
            patients = get_doctor_patients(chat_id)
            if not patients:
                await query.edit_message_text("No patients assigned to you.")
                return

            lines, shown = [], 0
            for patient in patients:
                patient_id = patient["user_chat_id"]
                ok, snippet = get_report_for(patient_id)
                if ok:
                    name = html.escape(patient.get("full_name", str(patient_id)))
                    status_lines = snippet.split("\n")
                    status = next((line for line in status_lines if "Status:" in line), "Status: Unknown")
                    lines.append(f"• <b>{name}</b> (ID {patient_id})\n{status}")
                    shown += 1
                if shown >= 10:
                    lines.append("… (showing first 10 patients)")
                    break

            await query.edit_message_text(("No reports found for your patients." if not lines else "📊 Patient Status Overview:\n\n" + "\n\n".join(lines)), parse_mode="HTML")

        elif query.data == "doctor_profile" and is_doctor(chat_id):
            user_data = api_get(f"users/{chat_id}")
            if not user_data:
                await query.edit_message_text("Profile not found.")
                return
            patients = get_doctor_patients(chat_id)
            patient_count = len(patients) if patients else 0
            profile_text = (
                "👨‍⚕️ <b>Doctor Profile</b>\n\n"
                f"<b>Name:</b> {html.escape(user_data['full_name'])}\n"
                f"<b>Specialization:</b> {html.escape(user_data.get('specialization', 'Not specified'))}\n"
                f"<b>Hospital:</b> {html.escape(user_data.get('hospital', 'Not specified'))}\n"
                f"<b>Patients:</b> {patient_count}\n"
                f"<b>User ID:</b> {chat_id}"
            )
            keyboard = [
                [InlineKeyboardButton("✏️ Edit Profile", callback_data="doctor_edit_profile")],
                [InlineKeyboardButton("⬅️ Back", callback_data="doctor_menu")],
            ]
            await query.edit_message_text(profile_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

        elif query.data == "doctor_menu" and is_doctor(chat_id):
            await render_menu_to_query(query, {"user_type": "doctor"}, chat_id)

        elif query.data == "doctor_edit_profile" and is_doctor(chat_id):
            keyboard = [
                [InlineKeyboardButton("✏️ Edit Name", callback_data="edit_doctor_name")],
                [InlineKeyboardButton("🏥 Edit Specialization", callback_data="edit_doctor_specialization")],
                [InlineKeyboardButton("🏢 Edit Hospital", callback_data="edit_doctor_hospital")],
                [InlineKeyboardButton("⬅️ Back to Profile", callback_data="doctor_profile")],
            ]
            await query.edit_message_text("What would you like to edit?", reply_markup=InlineKeyboardMarkup(keyboard))

        elif query.data == "edit_doctor_name" and is_doctor(chat_id):
            await query.edit_message_text("Please send your new name using:\n/update_doctor_name <Your New Name>")

        elif query.data == "edit_doctor_specialization" and is_doctor(chat_id):
            await query.edit_message_text("Please send your new specialization using:\n/update_doctor_specialization <Specialization>")

        elif query.data == "edit_doctor_hospital" and is_doctor(chat_id):
            await query.edit_message_text("Please send your new hospital using:\n/update_doctor_hospital <Hospital Name>")

        # ---- Admin flows ----
        elif query.data == "admin_start_all" and admin_mode:
            users = api_get("users") or []
            patients = [u for u in users if u.get("user_type") == "patient"]
            started, failed = 0, 0
            for patient in patients:
                ok, _ = start_recording_for(int(patient["user_chat_id"]))
                started += 1 if ok else 0
                failed += 0 if ok else 1
            await query.edit_message_text(f"▶️ Started for {started} users. Failed: {failed}.")

        elif query.data == "admin_stop_all" and admin_mode:
            users = api_get("users") or []
            patients = [u for u in users if u.get("user_type") == "patient"]
            stopped, failed = 0, 0
            for patient in patients:
                ok, _ = stop_recording_for(int(patient["user_chat_id"]))
                stopped += 1 if ok else 0
                failed += 0 if ok else 1
            await query.edit_message_text(f"⏹ Stopped for {stopped} users. Failed: {failed}.")

        elif query.data == "admin_monitor_all" and admin_mode:
            users = api_get("users") or []
            patients = [u for u in users if u.get("user_type") == "patient"]
            lines, shown = [], 0
            for patient in patients:
                user_id = int(patient["user_chat_id"])
                ok, snippet = get_report_for(user_id)
                if ok:
                    name = html.escape(patient.get("full_name", str(user_id)))
                    status_lines = snippet.split("\n")
                    status = next((line for line in status_lines if "Status:" in line), "Status: Unknown")
                    lines.append(f"• <b>{name}</b> (ID {user_id})\n{status}")
                    shown += 1
                if shown >= 10:
                    lines.append("… (showing first 10 patients)")
                    break
            await query.edit_message_text(("No reports found." if not lines else "\n\n".join(lines)), parse_mode="HTML")

        elif query.data == "admin_user_list" and admin_mode:
            users = api_get("users") or []
            if not users:
                await query.edit_message_text("No users found.")
                return ConversationHandler.END

            keyboard = [[InlineKeyboardButton(f"{html.escape(u['full_name'])} (ID: {u['user_chat_id']})", callback_data=f"admin_user_{u['user_chat_id']}")] for u in users]
            keyboard.append([InlineKeyboardButton("Back to Menu", callback_data="back_to_menu")])
            await query.edit_message_text("👥 User list — choose one:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

        elif query.data.startswith("admin_user_") and admin_mode:
            target_id = int(query.data.split("_")[-1])
            user_target = api_get(f"users/{target_id}")
            if not user_target:
                await query.edit_message_text("User not found.")
                return ConversationHandler.END

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
                    f"Managing: <b>{html.escape(user_target['full_name'])}</b> (ID {target_id})",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="HTML",
                )
            else:
                user_type = user_target.get("user_type", "unknown")
                keyboard = [
                    [InlineKeyboardButton("👥 View Doctor's Patients", callback_data=f"admin_doctor_patients_{target_id}")],
                    [InlineKeyboardButton("📊 Doctor Info", callback_data=f"admin_doctor_info_{target_id}")],
                    [InlineKeyboardButton("🗑️ Remove Doctor", callback_data=f"admin_delete_user_{target_id}")],
                    [InlineKeyboardButton("⬅️ Back to list", callback_data="admin_user_list")],
                ]
                await query.edit_message_text(
                    f"Managing Doctor: <b>{html.escape(user_target['full_name'])}</b> (ID {target_id})\n"
                    f"Type: {user_type.title()}\n"
                    f"Specialization: {user_target.get('specialization', 'N/A')}\n"
                    f"Hospital: {user_target.get('hospital', 'N/A')}",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="HTML",
                )

        elif query.data.startswith("admin_doctor_patients_") and admin_mode:
            doctor_id = int(query.data.split("_")[-1])
            doctor_data = api_get(f"users/{doctor_id}")
            if not doctor_data:
                await query.edit_message_text("Doctor not found.")
                return

            patients = get_doctor_patients(doctor_id)
            if not patients:
                await query.edit_message_text(f"Dr. {doctor_data['full_name']} has no assigned patients.\n\nUse /menu to return.")
                return

            keyboard = [[InlineKeyboardButton(f"{p['full_name']} (ID: {p['user_chat_id']})", callback_data=f"admin_view_patient_{p['user_chat_id']}")] for p in patients]
            keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data=f"admin_user_{doctor_id}")])
            await query.edit_message_text(f"👥 Dr. {doctor_data['full_name']}'s Patients ({len(patients)}):", reply_markup=InlineKeyboardMarkup(keyboard))

        elif query.data.startswith("admin_doctor_info_") and admin_mode:
            doctor_id = int(query.data.split("_")[-1])
            doctor_data = api_get(f"users/{doctor_id}")
            if not doctor_data:
                await query.edit_message_text("Doctor not found.")
                return

            patients = get_doctor_patients(doctor_id)
            patient_count = len(patients) if patients else 0
            info_text = (
                "👨‍⚕️ <b>Doctor Information</b>\n\n"
                f"<b>Name:</b> {html.escape(doctor_data['full_name'])}\n"
                f"<b>ID:</b> {doctor_id}\n"
                f"<b>Specialization:</b> {html.escape(doctor_data.get('specialization', 'Not specified'))}\n"
                f"<b>Hospital:</b> {html.escape(doctor_data.get('hospital', 'Not specified'))}\n"
                f"<b>Assigned Patients:</b> {patient_count}\n"
                f"<b>User Type:</b> {doctor_data.get('user_type', 'unknown').title()}"
            )
            keyboard = [
                [InlineKeyboardButton("👥 View Patients", callback_data=f"admin_doctor_patients_{doctor_id}")],
                [InlineKeyboardButton("🗑️ Remove Doctor", callback_data=f"admin_delete_user_{doctor_id}")],
                [InlineKeyboardButton("⬅️ Back", callback_data=f"admin_user_{doctor_id}")],
            ]
            await query.edit_message_text(info_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

        elif query.data.startswith("admin_view_patient_") and admin_mode:
            patient_id = int(query.data.split("_")[-1])
            patient_data = api_get(f"users/{patient_id}")
            if not patient_data:
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
                f"Managing Patient: <b>{html.escape(patient_data['full_name'])}</b> (ID {patient_id})",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML",
            )

        elif query.data.startswith("admin_start_user_") and admin_mode:
            target_id = int(query.data.split("_")[-1])
            ok, msg = start_recording_for(target_id)
            await query.edit_message_text(f"User {target_id}: " + (("✅ " if ok else "❌ ") + msg))

        elif query.data.startswith("admin_stop_user_") and admin_mode:
            target_id = int(query.data.split("_")[-1])
            ok, msg = stop_recording_for(target_id)
            await query.edit_message_text(f"User {target_id}: " + (("✅ " if ok else "❌ ") + msg))

        elif query.data.startswith("admin_get_report_") and admin_mode:
            target_id = int(query.data.split("_")[-1])
            ok, text = get_report_for(target_id)
            await query.edit_message_text((f"📄 Report for {target_id}:\n\n{text}" if ok else "❌ " + text), parse_mode="HTML")

        elif query.data.startswith("admin_get_chart_") and admin_mode:
            target_id = int(query.data.split("_")[-1])
            await query.edit_message_text(
                f"📈 Select chart time period for user {target_id}:",
                reply_markup=build_chart_period_keyboard("admin_chart", target_id, f"admin_user_{target_id}"),
            )

        elif query.data.startswith("admin_chart_24h_") and admin_mode:
            target_id = int(query.data.split("_")[-1])
            await send_chart_to_user(update, context, target_id, max_hours=24)

        elif query.data.startswith("admin_chart_48h_") and admin_mode:
            target_id = int(query.data.split("_")[-1])
            await send_chart_to_user(update, context, target_id, max_hours=48)

        elif query.data.startswith("admin_chart_72h_") and admin_mode:
            target_id = int(query.data.split("_")[-1])
            await send_chart_to_user(update, context, target_id, max_hours=72)

        elif query.data.startswith("admin_chart_week_") and admin_mode:
            target_id = int(query.data.split("_")[-1])
            await send_chart_to_user(update, context, target_id, max_hours=168)

        elif query.data.startswith("admin_delete_user_") and admin_mode:
            target_id = int(query.data.split("_")[-1])
            keyboard = [[
                InlineKeyboardButton("Yes, delete user", callback_data=f"confirm_admin_delete_{target_id}"),
                InlineKeyboardButton("Cancel", callback_data="admin_user_list"),
            ]]
            await query.edit_message_text(f"⚠️ Delete user {target_id} and all data?", reply_markup=InlineKeyboardMarkup(keyboard))

        elif query.data.startswith("confirm_admin_delete_") and admin_mode:
            target_id = int(query.data.split("_")[-1])
            await query.edit_message_text(f"✅ User {target_id} deleted." if api_delete(f"users/{target_id}") else "❌ Failed to delete user.")

    except Exception as e:
        logger.error(f"Error in button handler: {e}")
        logger.error(traceback.format_exc())
        try:
            await query.edit_message_text("❌ An error occurred. Please try again.")
        except Exception:
            pass

# =========================
# Error handler + main
# =========================
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception while handling update:", exc_info=context.error)
    logger.error(f"Update: {update}")
    logger.error(traceback.format_exc())
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text("An error occurred. Please try again.")
    except Exception:
        pass

def main():
    try:
        print("🚀 Initializing Telegram Bot...")
        application = Application.builder().token(TELEGRAM_TOKEN).build()

        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("register", register))
        application.add_handler(CommandHandler("menu", menu))

        application.add_handler(CommandHandler("register_doctor", register_doctor))
        application.add_handler(CommandHandler("update_doctor_name", update_doctor_name))
        application.add_handler(CommandHandler("update_doctor_specialization", update_doctor_specialization))
        application.add_handler(CommandHandler("update_doctor_hospital", update_doctor_hospital))

        device_conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(start_device_registration, pattern="^register_new_device$")],
            states={DEVICE_TYPE: [CallbackQueryHandler(receive_device_type, pattern="^(devtype_|cancel_device_reg)")]},
            fallbacks=[CommandHandler("cancel", cancel_device_registration)],
        )
        application.add_handler(device_conv_handler)

        application.add_handler(CallbackQueryHandler(button_handler))
        application.add_error_handler(error_handler)

        print("✅ Bot configured successfully!")
        print("🔄 Starting polling...")
        application.run_polling(drop_pending_updates=True)

    except KeyboardInterrupt:
        print("🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error in main: {e}")
        logger.error(traceback.format_exc())
        print(f"💥 Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
