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
import sys
import traceback

# Try importing chart libraries, handle gracefully if missing
try:
    import matplotlib
    matplotlib.use('Agg')  # Use non-GUI backend
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from datetime import datetime, timedelta
    import pandas as pd
    import io
    CHARTS_AVAILABLE = True
    print("✅ Chart libraries loaded successfully")
except ImportError as e:
    CHARTS_AVAILABLE = False
    print(f"⚠️ Chart libraries not available: {e}")
    print("Charts will be disabled. Install: pip install matplotlib pandas seaborn")

# =========================
# Enhanced Logging
# =========================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('telegram_bot.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

print("🤖 Starting Telegram Bot Service...")
print(f"Python version: {sys.version}")
print(f"Charts enabled: {CHARTS_AVAILABLE}")

# =========================
# Config
# =========================
REST_API_URL = "http://catalog:5001"

# keep END symbol available even if we don't use states now
ADD_SENSOR, ADD_SITUATION, SENSOR_DETAILS, UPDATE_PROFILE = range(4)

# Your requested token (hard-coded, per your instruction)
TELEGRAM_TOKEN = "6605276431:AAHoPhbbqSSPR7z1VS56c7Cddp34xzvT2Og"

# Admins (Telegram user IDs)
ADMINS = [6378242947, 650295422, 6605276431, 548805315]

print(f"🔧 Configuration loaded. REST API: {REST_API_URL}")


def is_admin(user_id: int) -> bool:
    return user_id in ADMINS


# =========================
# REST helpers with better error handling
# =========================
def api_get(endpoint):
    try:
        url = f"{REST_API_URL}/{endpoint}"
        logger.info(f"API GET: {url}")
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json()
        else:
            logger.warning(f"API GET failed: {r.status_code} - {r.text}")
        return None
    except requests.exceptions.ConnectionError as e:
        logger.error(f"API Connection error: {e}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"API GET error: {e}")
        return None


def api_post(endpoint, data):
    try:
        url = f"{REST_API_URL}/{endpoint}"
        logger.info(f"API POST: {url}")
        r = requests.post(url, json=data, timeout=10)
        success = r.status_code in (200, 201)
        if not success:
            logger.warning(f"API POST failed: {r.status_code} - {r.text}")
        return success
    except requests.exceptions.RequestException as e:
        logger.error(f"API POST error: {e}")
        return False


def api_put(endpoint, data):
    try:
        url = f"{REST_API_URL}/{endpoint}"
        logger.info(f"API PUT: {url}")
        r = requests.put(url, json=data, timeout=10)
        success = r.status_code == 200
        if not success:
            logger.warning(f"API PUT failed: {r.status_code} - {r.text}")
        return success
    except requests.exceptions.RequestException as e:
        logger.error(f"API PUT error: {e}")
        return False


def api_delete(endpoint):
    try:
        url = f"{REST_API_URL}/{endpoint}"
        logger.info(f"API DELETE: {url}")
        r = requests.delete(url, timeout=10)
        success = r.status_code == 200
        if not success:
            logger.warning(f"API DELETE failed: {r.status_code} - {r.text}")
        return success
    except requests.exceptions.RequestException as e:
        logger.error(f"API DELETE error: {e}")
        return False


# =========================
# Service helpers
# =========================
def _sensor_service_url():
    svc = api_get("services/sensor")
    if not svc or "url" not in svc:
        logger.warning("Sensor service not found in catalog")
        return None
    # normalize trailing slash
    return svc["url"].rstrip("/")


def _panel_service():
    svc = api_get("services/adminPanel")
    if not svc or "url" not in svc:
        logger.warning("Admin panel service not found in catalog")
        return None
    return {"url": svc["url"].rstrip("/"), "port": svc.get("port")}


def _data_service():
    svc = api_get("services/dataIngestion")
    if not svc or "url" not in svc:
        logger.warning("Data ingestion service not found in catalog")
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

    # For your system, use the monitor service pattern
    try:
        # Based on monitor.py, the correct endpoint is /read/{chat_id}
        url = f"{base}/{user_id}"
        logger.info(f"Starting recording for user {user_id} at {url}")
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return True, "Recording started."
        else:
            logger.warning(f"Start recording failed: {r.status_code} - {r.text}")
    except Exception as e:
        logger.error(f"Start recording error: {e}")

    return False, "Failed to start recording."

def stop_recording_for(user_id: int):
    base = _sensor_service_url()
    print(f"DEBUG: _sensor_service_url() returned: {base}")
    
    if not base:
        return False, "Sensor service not found."

    try:
        # Fix URL construction
        if base.endswith("/read/"):
            base_url = base[:-6]  # Remove "/read/" from the end
        elif base.endswith("/read"):
            base_url = base[:-5]  # Remove "/read" from the end  
        else:
            base_url = base
            
        url = f"{base_url}/stop/{user_id}"
        
        print(f"DEBUG: Final stop URL: {url}")
        
        r = requests.get(url, timeout=10)
        print(f"DEBUG: Response status: {r.status_code}")
        print(f"DEBUG: Response text: {r.text[:200]}...")
        
        if r.status_code == 200:
            return True, "Recording stopped successfully."
        else:
            return False, f"Failed to stop (HTTP {r.status_code}): {r.text[:100]}"
    except Exception as e:
        print(f"DEBUG: Exception: {e}")
        return False, f"Error while stopping: {str(e)}"

def get_report_for_old(user_id: int):
    panel = _panel_service()
    if not panel:
        return False, "Report service not found."
    
    url = panel["url"]
    port = panel.get("port")
    full = f"{url}:{port}/report/{user_id}" if port else f"{url}/report/{user_id}"
    
    try:
        logger.info(f"Fetching report from {full}")
        r = requests.get(full, timeout=15)
        if r.status_code == 200:
            try:
                data = r.json()
                if not data:
                    return True, "No report found."
                # keep it short to avoid Telegram 4096 char limit
                text = html.escape(json.dumps(data, ensure_ascii=False)[:1200])
                return True, text
            except Exception as e:
                logger.error(f"Error parsing report data: {e}")
                return False, "Error parsing report data."
        else:
            logger.warning(f"Report fetch failed: {r.status_code} - {r.text}")
            return False, f"Failed to fetch report (HTTP {r.status_code})."
    except Exception as e:
        logger.error(f"Error fetching report {full}: {e}")
        return False, "Error while fetching report."


def get_report_for(user_id: int):
    panel = _panel_service()
    if not panel:
        return False, "Report service not found."
    
    url = panel["url"]
    port = panel.get("port")
    full = f"{url}:{port}/report/{user_id}" if port else f"{url}/report/{user_id}"
    
    try:
        logger.info(f"Fetching report from {full}")
        r = requests.get(full, timeout=15)
        if r.status_code == 200:
            try:
                raw_data = r.json()
                if not raw_data:
                    return True, "No report found."
                
                # Parse the double-encoded JSON
                if isinstance(raw_data, str):
                    data = json.loads(raw_data)
                else:
                    data = raw_data
                
                # Format the data into a readable report
                formatted_report = format_health_report(data, user_id)
                return True, formatted_report
                
            except Exception as e:
                logger.error(f"Error parsing report data: {e}")
                return False, "Error parsing report data."
        else:
            logger.warning(f"Report fetch failed: {r.status_code} - {r.text}")
            return False, f"Failed to fetch report (HTTP {r.status_code})."
    except Exception as e:
        logger.error(f"Error fetching report {full}: {e}")
        return False, "Error while fetching report."


def format_health_report(data, user_id):
    """Format raw health data into a readable report"""
    if not data:
        return "No health data available."
    
    # Group data by timestamp
    from collections import defaultdict
    grouped_data = defaultdict(dict)
    
    for entry in data:
        timestamp = entry.get('time', 'Unknown time')
        field = entry.get('field', 'unknown')
        value = entry.get('value', 'N/A')
        
        # Parse timestamp for better formatting
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            formatted_time = timestamp
        
        grouped_data[formatted_time][field] = value
    
    # Build the formatted report
    report_lines = []
    report_lines.append(f"<b>Health Report - User {user_id}</b>\n")
    
    # Sort by time (most recent first)
    sorted_times = sorted(grouped_data.keys(), reverse=True)
    
    # Show last 10 readings to stay within Telegram limits
    for i, time in enumerate(sorted_times[:10]):
        reading = grouped_data[time]
        
        report_lines.append(f"<b>📅 {time}</b>")
        
        # Format vital signs
        temp = reading.get('temp', 'N/A')
        hr = reading.get('heart_rate', 'N/A')
        oxygen = reading.get('oxygen', 'N/A')
        state = reading.get('state', 'N/A')
        
        # Add status emoji based on health state
        if state == 'normal':
            status_emoji = "✅"
        elif state == 'risky':
            status_emoji = "⚠️"
        elif state == 'dangerous':
            status_emoji = "🚨"
        else:
            status_emoji = "❓"
        
        report_lines.append(f"{status_emoji} Status: <b>{state}</b>")
        report_lines.append(f"🌡️ Temperature: {temp}°C")
        report_lines.append(f"❤️ Heart Rate: {hr} BPM")
        report_lines.append(f"🫁 Oxygen: {oxygen}%")
        report_lines.append("")  # Empty line for spacing
    
    if len(sorted_times) > 10:
        report_lines.append(f"... and {len(sorted_times) - 10} more readings")
    
    # Add summary
    if sorted_times:
        latest_reading = grouped_data[sorted_times[0]]
        latest_state = latest_reading.get('state', 'unknown')
        
        report_lines.append(f"\n<b>📊 Summary</b>")
        report_lines.append(f"Latest Status: <b>{latest_state}</b>")
        report_lines.append(f"Total Readings: {len(sorted_times)}")
        
        # Count states
        state_counts = defaultdict(int)
        for reading in grouped_data.values():
            state = reading.get('state', 'unknown')
            state_counts[state] += 1
        
        if state_counts:
            report_lines.append(f"State Distribution:")
            for state, count in state_counts.items():
                percentage = (count / len(sorted_times)) * 100
                report_lines.append(f"  • {state}: {count} ({percentage:.1f}%)")
    
    return "\n".join(report_lines)

def get_chart_data_for(user_id: int):
    """Get raw sensor data for chart generation"""
    if not CHARTS_AVAILABLE:
        return False, "Chart functionality not available - missing dependencies.", None
        
    data_svc = _data_service()
    if not data_svc:
        return False, "Data service not found.", None
    
    url = data_svc["url"]
    port = data_svc.get("port")
    full = f"{url}:{port}/getUserData/{user_id}" if port else f"{url}/getUserData/{user_id}"
    
    try:
        logger.info(f"Fetching chart data from {full}")
        r = requests.get(full, timeout=15)
        if r.status_code == 200:
            try:
                data = json.loads(r.json())  # Double parsing as per your existing code
                if not data:
                    return True, "No data found for charts.", None
                return True, "Data retrieved successfully.", data
            except Exception as e:
                logger.error(f"Error parsing chart data: {e}")
                return False, "Error parsing chart data.", None
        else:
            logger.warning(f"Chart data fetch failed: {r.status_code} - {r.text}")
            return False, f"Failed to fetch data (HTTP {r.status_code}).", None
    except Exception as e:
        logger.error(f"Error fetching chart data {full}: {e}")
        return False, "Error while fetching chart data.", None


def generate_chart_for(user_id: int, chart_type: str = "combined"):
    """Generate chart from user sensor data"""
    if not CHARTS_AVAILABLE:
        return False, "Chart functionality not available - missing dependencies.", None
        
    ok, msg, data = get_chart_data_for(user_id)
    if not ok or not data:
        return False, msg, None
    
    try:
        # Convert to DataFrame for easier manipulation
        df = pd.DataFrame(data)
        if df.empty:
            return False, "No data available for chart generation.", None
        
        # Convert time column to datetime
        df['time'] = pd.to_datetime(df['time'])
        df = df.sort_values('time')
        
        # Set up the plot with basic style
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        fig.suptitle(f'Health Monitoring Dashboard - User {user_id}', fontsize=16, fontweight='bold')
        
        # Temperature chart
        temp_data = df[df['field'] == 'temp']
        if not temp_data.empty:
            axes[0, 0].plot(temp_data['time'], temp_data['value'], 'r-', linewidth=2, marker='o', markersize=4)
            axes[0, 0].set_title('Body Temperature (°C)', fontweight='bold')
            axes[0, 0].set_ylabel('Temperature (°C)')
            axes[0, 0].grid(True, alpha=0.3)
            axes[0, 0].axhline(y=37, color='orange', linestyle='--', alpha=0.7, label='Normal limit')
            axes[0, 0].axhline(y=39, color='red', linestyle='--', alpha=0.7, label='Danger limit')
            axes[0, 0].legend()
            
        # Heart Rate chart
        hr_data = df[df['field'] == 'heart_rate']
        if not hr_data.empty:
            axes[0, 1].plot(hr_data['time'], hr_data['value'], 'g-', linewidth=2, marker='o', markersize=4)
            axes[0, 1].set_title('Heart Rate (BPM)', fontweight='bold')
            axes[0, 1].set_ylabel('BPM')
            axes[0, 1].grid(True, alpha=0.3)
            axes[0, 1].axhline(y=60, color='blue', linestyle='--', alpha=0.7, label='Lower normal')
            axes[0, 1].axhline(y=100, color='orange', linestyle='--', alpha=0.7, label='Upper normal')
            axes[0, 1].legend()
            
        # Oxygen Level chart
        oxygen_data = df[df['field'] == 'oxygen']
        if not oxygen_data.empty:
            axes[1, 0].plot(oxygen_data['time'], oxygen_data['value'], 'b-', linewidth=2, marker='o', markersize=4)
            axes[1, 0].set_title('Oxygen Saturation (%)', fontweight='bold')
            axes[1, 0].set_ylabel('SpO2 (%)')
            axes[1, 0].grid(True, alpha=0.3)
            axes[1, 0].axhline(y=95, color='orange', linestyle='--', alpha=0.7, label='Normal limit')
            axes[1, 0].axhline(y=90, color='red', linestyle='--', alpha=0.7, label='Danger limit')
            axes[1, 0].legend()
            
        # Health State chart (categorical)
        state_data = df[df['field'] == 'state']
        if not state_data.empty:
            # Map states to numbers for plotting
            state_mapping = {'normal': 0, 'risky': 1, 'dangerous': 2}
            state_data = state_data.copy()
            state_data['state_num'] = state_data['value'].map(state_mapping)
            
            colors = ['green' if x == 0 else 'orange' if x == 1 else 'red' for x in state_data['state_num']]
            axes[1, 1].scatter(state_data['time'], state_data['state_num'], c=colors, s=50, alpha=0.7)
            axes[1, 1].set_title('Health State', fontweight='bold')
            axes[1, 1].set_ylabel('State')
            axes[1, 1].set_yticks([0, 1, 2])
            axes[1, 1].set_yticklabels(['Normal', 'Risky', 'Dangerous'])
            axes[1, 1].grid(True, alpha=0.3)
            
        # Format x-axis for all subplots
        for ax in axes.flat:
            ax.tick_params(axis='x', rotation=45)
            if len(ax.get_lines()) > 0 or len(ax.collections) > 0:  # Only format if there's data
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
                ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=10))
        
            # Show more frequent time labels
            ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=5))  # Every 5 minutes instead of 10
            ax.xaxis.set_minor_locator(mdates.MinuteLocator(interval=1))  # Every minute as minor ticks
            
            # Ensure all labels are shown
            ax.tick_params(axis='x', which='major', labelsize=8)
            ax.tick_params(axis='x', which='minor', labelsize=6)
            
            # Auto-format to prevent label overlap
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        plt.tight_layout()
        
        # Save plot to bytes buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close()  # Important: close the figure to free memory
        
        return True, "Chart generated successfully.", buf
        
    except Exception as e:
        logger.error(f"Error generating chart: {e}")
        logger.error(traceback.format_exc())
        return False, f"Chart generation failed: {str(e)}", None


async def send_chart_to_user(update, context, user_id: int):
    """Send chart image to user via Telegram"""
    if not CHARTS_AVAILABLE:
        await update.callback_query.edit_message_text("Chart functionality disabled - missing matplotlib/pandas dependencies")
        return
        
    try:
        # Show typing action
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
        
        ok, msg, chart_buffer = generate_chart_for(user_id)
        if not ok or not chart_buffer:
            await update.callback_query.edit_message_text(f"❌ {msg}")
            return
        
        # Send the chart as photo
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=chart_buffer,
            caption=f"📊 Health monitoring chart for user {user_id}\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        # Edit the original message
        await update.callback_query.edit_message_text("✅ Chart sent successfully!")
        
    except Exception as e:
        logger.error(f"Error sending chart: {e}")
        logger.error(traceback.format_exc())
        await update.callback_query.edit_message_text(f"❌ Failed to send chart: {str(e)}")


# =========================
# Telegram Handlers
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id
        logger.info(f"Start command from user {chat_id}")
        
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
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        logger.error(traceback.format_exc())


async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id
        logger.info(f"Register command from user {chat_id}")
        
        if len(context.args) < 1:
            await update.message.reply_text("Please provide your full name: /register <your name>")
            return
        full_name = " ".join(context.args)
        if api_post("users", {"user_chat_id": chat_id, "full_name": full_name}):
            await update.message.reply_text(f"✅ Registered, {html.escape(full_name)}.\nUse /menu.")
        else:
            await update.message.reply_text("❌ Registration failed. Try again.")
    except Exception as e:
        logger.error(f"Error in register command: {e}")
        logger.error(traceback.format_exc())


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id
        logger.info(f"Menu command from user {chat_id}")
        
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
            ]
            if CHARTS_AVAILABLE:
                keyboard.append([InlineKeyboardButton("📈 Get my chart", callback_data="get_chart")])
            keyboard.append([InlineKeyboardButton("🗑 Remove my profile", callback_data="delete_profile")])
            text = "🛠 Admin menu:"
        else:
            keyboard = [
                [InlineKeyboardButton("▶️ Start", callback_data="start_recording")],
                [InlineKeyboardButton("📄 Get report", callback_data="get_report")],
            ]
            if CHARTS_AVAILABLE:
                keyboard.append([InlineKeyboardButton("📈 Get chart", callback_data="get_chart")])
            keyboard.extend([
                [InlineKeyboardButton("⏹ Stop", callback_data="stop_recording")],
                [InlineKeyboardButton("🗑 Remove profile", callback_data="delete_profile")],
            ])
            text = "📋 Main menu:"

        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.error(f"Error in menu command: {e}")
        logger.error(traceback.format_exc())


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        chat_id = query.message.chat_id
        
        logger.info(f"Button pressed: {query.data} by user {chat_id}")

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

        elif query.data == "get_chart":
            await send_chart_to_user(update, context, chat_id)

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
            ]
            if CHARTS_AVAILABLE:
                keyboard.append([InlineKeyboardButton("📈 Get chart", callback_data=f"admin_get_chart_{target_id}")])
            keyboard.extend([
                [InlineKeyboardButton("🗑️ Remove user", callback_data=f"admin_delete_user_{target_id}")],
                [InlineKeyboardButton("⬅️ Back to list", callback_data="admin_user_list")],
            ])
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

        elif query.data.startswith("admin_get_chart_") and admin_mode:
            target_id = int(query.data.split("_")[-1])
            await send_chart_to_user(update, context, target_id)

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

        elif query.data.startswith("chart_user_") and admin_mode:
            target_id = int(query.data.split("_")[-1])
            user_target = api_get(f"users/{target_id}")
            if not user_target:
                await query.edit_message_text("User not found.")
                return ConversationHandler.END
            
            # Send chart for the selected user
            await send_chart_to_user(update, context, target_id)

        elif query.data == "cancel":
            await query.edit_message_text("Operation cancelled.")

        else:
            await query.edit_message_text(f"Handler for '{query.data}' not implemented yet.")

        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error in button handler: {e}")
        logger.error(traceback.format_exc())
        try:
            await query.edit_message_text("❌ An error occurred. Please try again.")
        except:
            pass


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception while handling update:", exc_info=context.error)
    logger.error(f"Update: {update}")
    logger.error(traceback.format_exc())
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text("An error occurred. Please try again.")
    except Exception:
        pass


def test_connectivity():
    """Test basic connectivity before starting bot"""
    print("🔍 Testing connectivity...")
    
    # Test catalog service
    try:
        response = requests.get(f"{REST_API_URL}/", timeout=5)
        print(f"✅ Catalog service reachable: {response.status_code}")
    except Exception as e:
        print(f"❌ Cannot reach catalog service: {e}")
        return False
    
    # Test Telegram API
    try:
        test_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getMe"
        response = requests.get(test_url, timeout=5)
        if response.status_code == 200:
            bot_info = response.json()
            print(f"✅ Telegram bot authenticated: {bot_info.get('result', {}).get('username')}")
        else:
            print(f"❌ Telegram authentication failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Cannot reach Telegram API: {e}")
        return False
    
    return True


def main():
    try:
        print("🚀 Initializing Telegram Bot...")
        
        # Test connectivity first
        if not test_connectivity():
            print("❌ Connectivity tests failed. Exiting.")
            sys.exit(1)
        
        application = Application.builder().token(TELEGRAM_TOKEN).build()

        # Core commands
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("register", register))
        application.add_handler(CommandHandler("menu", menu))

        # Single callback handler drives the whole UI
        application.add_handler(CallbackQueryHandler(button_handler))

        # Error handler
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
    