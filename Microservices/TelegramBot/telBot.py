import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

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
from Microservices.Common.config import Config
from Microservices.Common.utils import register_service_with_catalog, ServiceRegistry

try:
    import matplotlib
    matplotlib.use('Agg')  # Use non-GUI backend
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from datetime import datetime
    import pandas as pd
    import io
    CHARTS_AVAILABLE = True
    print("✅ Chart libraries loaded successfully")
except ImportError as e:
    CHARTS_AVAILABLE = False
    print(f"⚠️ Chart libraries not available: {e}")
    print("Charts will be disabled. Install: pip install matplotlib pandas seaborn")

# =========================
# Logging
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
catalog_service =  Config.SERVICES["catalog_url"]

registry = ServiceRegistry()
database_service_url = registry.get_service_url("databaseAdapter")
monitoring_service_url = registry.get_service_url("sensor")

TELEGRAM_TOKEN = Config.TELEGRAM_TOKEN

# Admins (Telegram user IDs)
#ADMINS = [6378242947, 650295422, 6605276431, 548805315]

ADMINS = [int(uid) for uid in Config.ADMIN_USERS.keys()]


def is_admin(user_id: int) -> bool:
    # Check if user is in global admin list
    if user_id in ADMINS:
        return True
    
    # Check if user is a doctor (has admin privileges over their patients)
    user_data = api_get(f"users/{user_id}")
    if user_data and user_data.get('user_type') == 'doctor':
        return True
    
    return False

def is_doctor(user_id: int) -> bool:
    user_data = api_get(f"users/{user_id}")
    return user_data and user_data.get('user_type') == 'doctor'

def get_doctor_patients(doctor_id: int):
    return api_get(f"doctors/{doctor_id}") or []

# ==============
# REST helpers 
# ==============
def api_get(endpoint):
    try:
        url = f"{catalog_service}/{endpoint}"
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
        url = f"{catalog_service}/{endpoint}"
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
        url = f"{catalog_service}/{endpoint}"
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
        url = f"{catalog_service}/{endpoint}"
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
    url = svc["url"].rstrip("/")
    port = svc.get("port")
    
    if port:
        full_url = f"{url}:{port}"
    else:
        full_url = url
    
    logger.info(f"DEBUG: Sensor service full URL: {full_url}")
    return full_url


def start_recording_for(user_id: int):
    """
    Returns (ok: bool, message: str)
    """
    # First, check if user exists and is a patient
    try:
        user_response = requests.get(f"{catalog_service}/users/{user_id}", timeout=5)
        if user_response.status_code != 200:
            logger.warning(f"User {user_id} not found in catalog")
            return False, "User not found in the system."
        
        user_data = user_response.json()
        user_type = user_data.get('user_type', '')
        
        # Check if user is a patient
        if user_type != 'patient':
            logger.warning(f"Recording denied for user {user_id}: user type is '{user_type}', not 'patient'")
            return False, "Recording is only available for patients."
        
        logger.info(f"User {user_id} verified as patient: {user_data.get('full_name', 'Unknown')}")
        
    except Exception as e:
        logger.error(f"Error checking user type for {user_id}: {e}")
        return False, "Failed to verify user type."
    
    # Now, try to start recording
    base_url = _sensor_service_url()
    if not base_url:
        return False, "Sensor service not found."

    try:
        url = f"{base_url}/read/{user_id}"
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

def get_report_for(user_id: int, max_hours: int = 24):
    """Fetch user report through the database adapter service"""
    try:
        params = {"hours": max_hours}
        full_url = f"{database_service_url}/read/{user_id}"
        
        logger.info(f"Fetching report from database adapter: {full_url} (last {max_hours} hours)")
        
        response = requests.get(full_url, params=params, timeout=15)
        
        if response.status_code == 200:
            try:
                raw_data = response.json()
                
                if not raw_data:
                    return True, "No report found."
                
                # Check if the adapter returned an error
                if isinstance(raw_data, dict) and not raw_data.get("success", True):
                    error_message = raw_data.get("message", "Unknown error from database adapter")
                    logger.error(f"Database adapter error: {error_message}")
                    return False, f"Database error: {error_message}"
                
                # Extract the actual data
                if isinstance(raw_data, dict) and "data" in raw_data:
                    data = raw_data["data"]
                else:
                    data = raw_data
                
                # Parse double-encoded JSON if needed (from your original logic)
                if isinstance(data, str):
                    data = json.loads(data)
                
                if not data:
                    return True, "No report data found for this user."
                
                # Format the data into a readable report
                formatted_report = format_health_report(data, user_id)
                return True, formatted_report
                
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing report JSON: {e}")
                return False, "Error parsing report data."
            except Exception as e:
                logger.error(f"Error processing report data: {e}")
                logger.error(f"Raw response content: {response.text}")
                return False, "Error processing report data."
        else:
            logger.warning(f"Report fetch failed: {response.status_code} - {response.text}")
            return False, f"Failed to fetch report (HTTP {response.status_code})."
            
    except Exception as e:
        logger.error(f"Unexpected error fetching report: {e}")
        return False, "Unexpected error while fetching report."

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


def get_aggregated_chart_data_for(user_id: int, max_hours: int = 24):
    """Get aggregated sensor data for chart generation through database adapter"""
    if not CHARTS_AVAILABLE:
        return False, "Chart functionality not available - missing dependencies.", None
        
    try:
        params = {"hours": max_hours}
        full_url = f"{database_service_url}/aggregated/{user_id}"
        logger.info(f"Fetching aggregated chart data: {full_url} (last {max_hours} hours)")
        
        response = requests.get(full_url, params=params, timeout=15)
        
        if response.status_code == 200:
            try:
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
                    "aggregation_frequency": result.get("aggregation_frequency", "unknown")
                }
                
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing aggregated data JSON: {e}")
                return False, "Error parsing aggregated data.", None
            except Exception as e:
                logger.error(f"Error processing aggregated data: {e}")
                return False, "Error processing aggregated data.", None
        else:
            logger.warning(f"Aggregated data fetch failed: {response.status_code} - {response.text}")
            return False, f"Failed to fetch aggregated data (HTTP {response.status_code}).", None
            
    except requests.RequestException as e:
        logger.error(f"Request error fetching aggregated data: {e}")
        return False, "Error connecting to database adapter service.", None
    except Exception as e:
        logger.error(f"Unexpected error fetching aggregated data: {e}")
        return False, "Unexpected error while fetching aggregated data.", None

def generate_chart_for(user_id: int, chart_type: str = "combined", max_hours: int = 24):
    """Generate chart using server-side aggregated data"""
    if not CHARTS_AVAILABLE:
        return False, "Chart functionality not available - missing dependencies.", None
        
    # Get aggregated data from database adapter service
    ok, msg, result = get_aggregated_chart_data_for(user_id, max_hours)
    if not ok or not result:
        return False, msg, None
    
    try:
        aggregated_data = result["data"]
        sample_info = result["sample_info"]
        
        if not aggregated_data:
            return False, "No aggregated data available for chart generation.", None
        
        # Convert to DataFrame for plotting
        agg_df = pd.DataFrame(aggregated_data)
        
        # Convert time strings back to datetime for plotting
        agg_df['time'] = pd.to_datetime(agg_df['time'])
        
        print(f"Final aggregated data shape: {agg_df.shape}")
        print(f"Sample info: {sample_info}")
        
        # Set up the plot
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        
        time_range_text = f"Last {max_hours} hours" if max_hours < 48 else f"Last {max_hours//24} days"
        fig.suptitle(f'Health Monitoring Dashboard - User {user_id} ({time_range_text})\n{sample_info}', 
                    fontsize=16, fontweight='bold')
        
        # Temperature chart
        temp_data = agg_df[agg_df['field'] == 'temp'].copy()
        if not temp_data.empty:
            # Convert to numeric and handle any non-numeric values
            temp_data['value'] = pd.to_numeric(temp_data['value'], errors='coerce')
            temp_data['min_value'] = pd.to_numeric(temp_data['min_value'], errors='coerce')
            temp_data['max_value'] = pd.to_numeric(temp_data['max_value'], errors='coerce')
            temp_data = temp_data.dropna()
            
            if not temp_data.empty:
                axes[0, 0].plot(temp_data['time'], temp_data['value'], 'r-', linewidth=2, label='Average')
                axes[0, 0].fill_between(temp_data['time'], temp_data['min_value'], temp_data['max_value'], 
                                       alpha=0.2, color='red', label='Range')
                axes[0, 0].set_title('Body Temperature (°C)', fontweight='bold')
                axes[0, 0].set_ylabel('Temperature (°C)')
                axes[0, 0].grid(True, alpha=0.3)
                axes[0, 0].legend()
        
        # Heart Rate chart
        hr_data = agg_df[agg_df['field'] == 'heart_rate'].copy()
        if not hr_data.empty:
            # Convert to numeric and handle any non-numeric values
            hr_data['value'] = pd.to_numeric(hr_data['value'], errors='coerce')
            hr_data['min_value'] = pd.to_numeric(hr_data['min_value'], errors='coerce')
            hr_data['max_value'] = pd.to_numeric(hr_data['max_value'], errors='coerce')
            hr_data = hr_data.dropna()
            
            if not hr_data.empty:
                axes[0, 1].plot(hr_data['time'], hr_data['value'], 'g-', linewidth=2, label='Average')
                axes[0, 1].fill_between(hr_data['time'], hr_data['min_value'], hr_data['max_value'], 
                                       alpha=0.2, color='green', label='Range')
                axes[0, 1].set_title('Heart Rate (BPM)', fontweight='bold')
                axes[0, 1].set_ylabel('BPM')
                axes[0, 1].grid(True, alpha=0.3)
                axes[0, 1].legend()
        
        # Oxygen Level chart
        oxygen_data = agg_df[agg_df['field'] == 'oxygen'].copy()
        if not oxygen_data.empty:
            # Convert to numeric and handle any non-numeric values
            oxygen_data['value'] = pd.to_numeric(oxygen_data['value'], errors='coerce')
            oxygen_data['min_value'] = pd.to_numeric(oxygen_data['min_value'], errors='coerce')
            oxygen_data['max_value'] = pd.to_numeric(oxygen_data['max_value'], errors='coerce')
            oxygen_data = oxygen_data.dropna()
            
            if not oxygen_data.empty:
                axes[1, 0].plot(oxygen_data['time'], oxygen_data['value'], 'b-', linewidth=2, label='Average')
                axes[1, 0].fill_between(oxygen_data['time'], oxygen_data['min_value'], oxygen_data['max_value'], 
                                       alpha=0.2, color='blue', label='Range')
                axes[1, 0].set_title('Oxygen Saturation (%)', fontweight='bold')
                axes[1, 0].set_ylabel('SpO2 (%)')
                axes[1, 0].grid(True, alpha=0.3)
                axes[1, 0].legend()
        
        # Health State chart - now using weighted priority aggregation
        state_data = agg_df[agg_df['field'] == 'state'].copy()
        if not state_data.empty:
            state_mapping = {'normal': 0, 'risky': 1, 'dangerous': 2}
            state_colors = {'normal': 'green', 'risky': 'orange', 'dangerous': 'red'}
            
            # Convert states to numbers and colors for plotting
            state_data['state_num'] = state_data['value'].map(state_mapping)
            colors = [state_colors.get(state, 'gray') for state in state_data['value']]
            
            state_data = state_data.dropna(subset=['state_num'])
            
            if not state_data.empty:
                axes[1, 1].scatter(state_data['time'], state_data['state_num'], c=colors, s=50, alpha=0.8)
                axes[1, 1].set_title('Health State (Weighted Priority)', fontweight='bold')
                axes[1, 1].set_ylabel('State')
                axes[1, 1].set_yticks([0, 1, 2])
                axes[1, 1].set_yticklabels(['Normal', 'Risky', 'Dangerous'])
                axes[1, 1].grid(True, alpha=0.3)
                
        
        # Time formatting
        for ax in axes.flat:
            if len(ax.get_lines()) > 0 or len(ax.collections) > 0:
                if max_hours <= 24:
                    ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
                    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
                elif max_hours <= 48:
                    ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
                    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
                elif max_hours <= 72:
                    ax.xaxis.set_major_locator(mdates.HourLocator(interval=4))
                    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
                else:
                    ax.xaxis.set_major_locator(mdates.HourLocator(interval=12))
                    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))

                ax.tick_params(axis='x', rotation=45, labelsize=9)
        
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        return True, "Chart generated successfully using server-side aggregation.", buf
        
    except Exception as e:
        logger.error(f"Error generating chart from aggregated data: {e}")
        logger.error(traceback.format_exc())
        return False, f"Chart generation failed: {str(e)}", None
    
def get_chart_data_for(user_id: int, max_hours: int = 24):
    """Legacy function - redirects to aggregated data endpoint"""
    return get_aggregated_chart_data_for(user_id, max_hours)

async def send_chart_to_user(update, context, user_id: int, max_hours: int = 24):
    """Send chart image to user via Telegram with specified time period"""
    if not CHARTS_AVAILABLE:
        await update.callback_query.edit_message_text("Chart functionality disabled - missing matplotlib/pandas dependencies")
        return
        
    try:
        # Show typing action
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
        
        # Generate chart with specified time period
        ok, msg, chart_buffer = generate_chart_for(user_id, max_hours=max_hours)
        if not ok or not chart_buffer:
            await update.callback_query.edit_message_text(f"❌ {msg}")
            return
        
        # Determine time period text for caption
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
        
        # Send the chart as photo
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=chart_buffer,
            caption=f"📊 Health monitoring chart for user {user_id} (Last {period_text})\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
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
        user_data = api_get(f"users/{chat_id}")
        
        if not user_data:
            await update.message.reply_text("Please register first with /register <your name>")
            return

        if user_data.get('user_type') == 'doctor':
        # Doctor menu
            keyboard = [
                [InlineKeyboardButton("👥 My Patients", callback_data="doctor_patients")],
                [InlineKeyboardButton("📊 Monitor All Patients", callback_data="doctor_monitor_all")],
                [InlineKeyboardButton("👤 My Profile", callback_data="doctor_profile")]
            ]
            text = "👨‍⚕️ Doctor Menu:"

        elif chat_id in ADMINS:
            keyboard = [
                [InlineKeyboardButton("▶️ Start all", callback_data="admin_start_all")],
                [InlineKeyboardButton("⏹ Stop all", callback_data="admin_stop_all")],
                [InlineKeyboardButton("📊 Monitor all", callback_data="admin_monitor_all")],
                [InlineKeyboardButton("👥 Manage users", callback_data="admin_user_list")],
                [InlineKeyboardButton("📄 Get my report", callback_data="get_report")],
            ]
            if CHARTS_AVAILABLE:
                keyboard.append([InlineKeyboardButton("📈 Get my chart", callback_data="get_chart")])
            keyboard.extend([
                [InlineKeyboardButton("🗑 Remove my profile", callback_data="delete_profile")]
            ])
            text = "🛠 Admin Menu:"
        else:
            # Patient menu
            keyboard = [
                [InlineKeyboardButton("▶️ Start monitoring", callback_data="start_recording")],
                [InlineKeyboardButton("📄 Get report", callback_data="get_report")],
                [InlineKeyboardButton("👨‍⚕️ Assign Doctor", callback_data="assign_doctor")]
            ]
            if CHARTS_AVAILABLE:
                keyboard.append([InlineKeyboardButton("📈 Get chart", callback_data="get_chart")])
            keyboard.extend([
                [InlineKeyboardButton("⏹ Stop monitoring", callback_data="stop_recording")],
                [InlineKeyboardButton("🗑 Remove profile", callback_data="delete_profile")]
            ])
            text = "📋 Patient Menu:"

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
            # Show time period selection instead of immediately generating chart
            keyboard = [
                [InlineKeyboardButton("📊 Last 24 hours", callback_data=f"get_chart_24h_{chat_id}")],
                [InlineKeyboardButton("📊 Last 48 hours", callback_data=f"get_chart_48h_{chat_id}")],
                [InlineKeyboardButton("📊 Last 72 hours", callback_data=f"get_chart_72h_{chat_id}")],
                [InlineKeyboardButton("📊 Last week", callback_data=f"get_chart_week_{chat_id}")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
            ]
            await query.edit_message_text(
                "📈 Select chart time period:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        # Add new handlers for different time periods
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
            await send_chart_to_user(update, context, user_id, max_hours=168)  # 7 days * 24 hours

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

        elif query.data == "assign_doctor":
            # Get list of available doctors
            doctors = api_get("doctors") or []
            if not doctors:
                await query.edit_message_text("No doctors are currently registered in the system. Please contact system administrator.")
                return
            
            keyboard = []
            for doctor in doctors:
                doctor_info = f"Dr. {doctor['full_name']}"
                if 'specialization' in doctor:
                    doctor_info += f" ({doctor['specialization']})"
                keyboard.append([InlineKeyboardButton(
                    doctor_info, 
                    callback_data=f"select_doctor_{doctor['user_chat_id']}"
                )])
            
            keyboard.append([InlineKeyboardButton("Cancel", callback_data="cancel")])
            
            await query.edit_message_text(
                "Select your doctor:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        elif query.data.startswith("select_doctor_"):
            doctor_id = int(query.data.split("_")[-1])
            
            # Assign patient to doctor
            assignment_data = {
                "patient_id": chat_id,
                "doctor_id": doctor_id
            }
            
            if api_post("assign_patient", assignment_data):
                doctor = api_get(f"users/{doctor_id}")
                doctor_name = doctor.get('full_name', 'Unknown') if doctor else 'Unknown'
                
                await query.edit_message_text(
                    f"✅ You have been assigned to {doctor_name}.\n\n"
                    f"Your doctor will now receive alerts when your health status becomes risky or dangerous, "
                    f"and can monitor your health data.\n\n"
                    f"Use /menu to continue."
                )
            else:
                await query.edit_message_text("Failed to assign doctor. Please try again.")

        # ===== Doctor buttons =====
        elif query.data == "doctor_patients" and is_doctor(chat_id):
            patients = get_doctor_patients(chat_id)
            if not patients:
                await query.edit_message_text("No patients assigned to you yet.")
                return
            
            keyboard = []
            for patient in patients:
                keyboard.append([InlineKeyboardButton(
                    f"{patient['full_name']} (ID: {patient['user_chat_id']})",
                    callback_data=f"doctor_view_patient_{patient['user_chat_id']}"
                )])
            keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="doctor_menu")])
            
            await query.edit_message_text(
                f"👥 Your Patients ({len(patients)}):",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        elif query.data.startswith("doctor_view_patient_") and is_doctor(chat_id):
            try:
                patient_id = int(query.data.split("_")[-1])
                
                # Verify this patient belongs to this doctor
                doctor_patients = get_doctor_patients(chat_id)
                patient = None
                for p in doctor_patients:
                    if p['user_chat_id'] == patient_id:
                        patient = p
                        break
                
                if not patient:
                    await query.edit_message_text("Access denied - patient not assigned to you.")
                    return
                
                keyboard = [
                    [InlineKeyboardButton("📄 View Report", callback_data=f"doctor_patient_report_{patient_id}")],
                    [InlineKeyboardButton("📈 View Chart", callback_data=f"doctor_patient_chart_{patient_id}")],
                    [InlineKeyboardButton("▶️ Start Monitoring", callback_data=f"doctor_start_patient_{patient_id}")],
                    [InlineKeyboardButton("⏹ Stop Monitoring", callback_data=f"doctor_stop_patient_{patient_id}")],
                    [InlineKeyboardButton("⬅️ Back to Patients", callback_data="doctor_patients")]
                ]
                
                await query.edit_message_text(
                    f"Managing Patient: {patient['full_name']}",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
            except (ValueError, IndexError) as e:
                logger.error(f"Error parsing patient ID from callback data: {e}")
                await query.edit_message_text("Invalid patient selection.")

        elif query.data.startswith("doctor_patient_report_") and is_doctor(chat_id):
            try:
                patient_id = int(query.data.split("_")[-1])
                
                # Verify patient belongs to this doctor
                doctor_patients = get_doctor_patients(chat_id)
                if not any(p['user_chat_id'] == patient_id for p in doctor_patients):
                    await query.edit_message_text("Access denied - patient not assigned to you.")
                    return
                
                ok, report = get_report_for(patient_id)
                if ok:
                    await query.edit_message_text(
                        f"📄 Patient Report (ID: {patient_id}):\n\n{report}",
                        parse_mode="HTML"
                    )
                else:
                    await query.edit_message_text(f"❌ Failed to get report: {report}")
                    
            except (ValueError, IndexError) as e:
                logger.error(f"Error parsing patient ID for report: {e}")
                await query.edit_message_text("Invalid patient selection.")

        elif query.data.startswith("doctor_patient_chart_") and is_doctor(chat_id):
            try:
                patient_id = int(query.data.split("_")[-1])
                
                # Verify patient belongs to this doctor
                doctor_patients = get_doctor_patients(chat_id)
                if not any(p['user_chat_id'] == patient_id for p in doctor_patients):
                    await query.edit_message_text("Access denied - patient not assigned to you.")
                    return
                
                # Show time period selection for doctor
                keyboard = [
                    [InlineKeyboardButton("📊 Last 24 hours", callback_data=f"doctor_chart_24h_{patient_id}")],
                    [InlineKeyboardButton("📊 Last 48 hours", callback_data=f"doctor_chart_48h_{patient_id}")],
                    [InlineKeyboardButton("📊 Last 72 hours", callback_data=f"doctor_chart_72h_{patient_id}")],
                    [InlineKeyboardButton("📊 Last week", callback_data=f"doctor_chart_week_{patient_id}")],
                    [InlineKeyboardButton("❌ Back", callback_data=f"doctor_view_patient_{patient_id}")]
                ]
                await query.edit_message_text(
                    f"📈 Select chart time period for patient {patient_id}:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
            except (ValueError, IndexError) as e:
                logger.error(f"Error parsing patient ID for chart: {e}")
                await query.edit_message_text("Invalid patient selection.")

        # Add doctor chart time period handlers
        elif query.data.startswith("doctor_chart_24h_") and is_doctor(chat_id):
            patient_id = int(query.data.split("_")[-1])
            doctor_patients = get_doctor_patients(chat_id)
            if any(p['user_chat_id'] == patient_id for p in doctor_patients):
                await send_chart_to_user(update, context, patient_id, max_hours=24)
            else:
                await query.edit_message_text("Access denied.")

        elif query.data.startswith("doctor_chart_48h_") and is_doctor(chat_id):
            patient_id = int(query.data.split("_")[-1])
            doctor_patients = get_doctor_patients(chat_id)
            if any(p['user_chat_id'] == patient_id for p in doctor_patients):
                await send_chart_to_user(update, context, patient_id, max_hours=48)
            else:
                await query.edit_message_text("Access denied.")

        elif query.data.startswith("doctor_chart_72h_") and is_doctor(chat_id):
            patient_id = int(query.data.split("_")[-1])
            doctor_patients = get_doctor_patients(chat_id)
            if any(p['user_chat_id'] == patient_id for p in doctor_patients):
                await send_chart_to_user(update, context, patient_id, max_hours=72)
            else:
                await query.edit_message_text("Access denied.")

        elif query.data.startswith("doctor_chart_week_") and is_doctor(chat_id):
            patient_id = int(query.data.split("_")[-1])
            doctor_patients = get_doctor_patients(chat_id)
            if any(p['user_chat_id'] == patient_id for p in doctor_patients):
                await send_chart_to_user(update, context, patient_id, max_hours=168)
            else:
                await query.edit_message_text("Access denied.")

        elif query.data.startswith("doctor_start_patient_") and is_doctor(chat_id):
            try:
                patient_id = int(query.data.split("_")[-1])
                
                # Verify patient belongs to this doctor
                doctor_patients = get_doctor_patients(chat_id)
                if not any(p['user_chat_id'] == patient_id for p in doctor_patients):
                    await query.edit_message_text("Access denied - patient not assigned to you.")
                    return
                
                ok, msg = start_recording_for(patient_id)
                await query.edit_message_text(
                    f"Patient {patient_id}: " + ("✅ " + msg if ok else "❌ " + msg)
                )
                
            except (ValueError, IndexError) as e:
                logger.error(f"Error parsing patient ID for start: {e}")
                await query.edit_message_text("Invalid patient selection.")

        elif query.data.startswith("doctor_stop_patient_") and is_doctor(chat_id):
            try:
                patient_id = int(query.data.split("_")[-1])
                
                # Verify patient belongs to this doctor
                doctor_patients = get_doctor_patients(chat_id)
                if not any(p['user_chat_id'] == patient_id for p in doctor_patients):
                    await query.edit_message_text("Access denied - patient not assigned to you.")
                    return
                
                ok, msg = stop_recording_for(patient_id)
                await query.edit_message_text(
                    f"Patient {patient_id}: " + ("✅ " + msg if ok else "❌ " + msg)
                )
                
            except (ValueError, IndexError) as e:
                logger.error(f"Error parsing patient ID for stop: {e}")
                await query.edit_message_text("Invalid patient selection.")

        elif query.data == "doctor_monitor_all" and is_doctor(chat_id):
            patients = get_doctor_patients(chat_id)
            if not patients:
                await query.edit_message_text("No patients assigned to you.")
                return
            
            lines = []
            shown = 0
            for patient in patients:
                patient_id = patient['user_chat_id']
                ok, snippet = get_report_for(patient_id)
                if ok:
                    name = html.escape(patient.get("full_name", str(patient_id)))
                    status_lines = snippet.split('\n')
                    status = next((line for line in status_lines if 'Status:' in line), 'Status: Unknown')
                    #lines.append(f"• <b>{name}</b> (ID {patient_id})\n<code>{status}</code>")
                    lines.append(f"• <b>{name}</b> (ID {patient_id})\n{status}")
                    shown += 1
                if shown >= 10:  # Limit for message size
                    lines.append("… (showing first 10 patients)")
                    break
            
            if not lines:
                await query.edit_message_text("No reports found for your patients.")
            else:
                await query.edit_message_text(
                    f"📊 Patient Status Overview:\n\n" + "\n\n".join(lines),
                    parse_mode="HTML"
                )

        elif query.data == "doctor_profile" and is_doctor(chat_id):
            user_data = api_get(f"users/{chat_id}")
            if user_data:
                patients = get_doctor_patients(chat_id)
                patient_count = len(patients) if patients else 0
                
                profile_text = f"""
👨‍⚕️ <b>Doctor Profile</b>

<b>Name:</b> {html.escape(user_data['full_name'])}
<b>Specialization:</b> {html.escape(user_data.get('specialization', 'Not specified'))}
<b>Hospital:</b> {html.escape(user_data.get('hospital', 'Not specified'))}
<b>Patients:</b> {patient_count}
<b>User ID:</b> {chat_id}
                """
                
                keyboard = [
                    [InlineKeyboardButton("✏️ Edit Profile", callback_data="doctor_edit_profile")],
                    [InlineKeyboardButton("⬅️ Back", callback_data="doctor_menu")]
                ]
                
                await query.edit_message_text(
                    profile_text,
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await query.edit_message_text("Profile not found.")

        elif query.data == "doctor_menu" and is_doctor(chat_id):
            keyboard = [
                [InlineKeyboardButton("👥 My Patients", callback_data="doctor_patients")],
                [InlineKeyboardButton("📊 Monitor All Patients", callback_data="doctor_monitor_all")],
                [InlineKeyboardButton("👤 My Profile", callback_data="doctor_profile")]
            ]
            
            await query.edit_message_text(
                "👨‍⚕️ Doctor Dashboard:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        elif query.data == "doctor_edit_profile" and is_doctor(chat_id):
            keyboard = [
                [InlineKeyboardButton("✏️ Edit Name", callback_data="edit_doctor_name")],
                [InlineKeyboardButton("🏥 Edit Specialization", callback_data="edit_doctor_specialization")],
                [InlineKeyboardButton("🏢 Edit Hospital", callback_data="edit_doctor_hospital")],
                [InlineKeyboardButton("⬅️ Back to Profile", callback_data="doctor_profile")]
            ]
            
            await query.edit_message_text(
                "What would you like to edit?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        elif query.data == "edit_doctor_name" and is_doctor(chat_id):
            await query.edit_message_text(
                "Please send your new name using the command:\n"
                "/update_doctor_name <Your New Name>\n\n"
                "Example: /update_doctor_name Dr. John Smith"
            )

        elif query.data == "edit_doctor_specialization" and is_doctor(chat_id):
            await query.edit_message_text(
                "Please send your new specialization using the command:\n"
                "/update_doctor_specialization <Your Specialization>\n\n"
                "Example: /update_doctor_specialization Cardiology"
            )

        elif query.data == "edit_doctor_hospital" and is_doctor(chat_id):
            await query.edit_message_text(
                "Please send your new hospital using the command:\n"
                "/update_doctor_hospital <Hospital Name>\n\n"
                "Example: /update_doctor_hospital General Hospital"
            )

        # ===== Admin buttons =====
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
            lines = []
            shown = 0
            for patient in patients:
                user_id = int(patient["user_chat_id"])
                ok, snippet = get_report_for(user_id)
                if ok:
                    name = html.escape(patient.get("full_name", str(user_id)))
                    status_lines = snippet.split('\n')
                    status = next((line for line in status_lines if 'Status:' in line), 'Status: Unknown')
                    #lines.append(f"• <b>{name}</b> (ID {user_id})\n<code>{status}</code>")
                    lines.append(f"• <b>{name}</b> (ID {user_id})\n{status}")
                    shown += 1
                if shown >= 10:  # keep message size safe
                    lines.append("… (showing first 10 patients)")
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
            if user_target.get("user_type") == "patient":
                keyboard = [
                    [InlineKeyboardButton("▶️ Start", callback_data=f"admin_start_user_{target_id}")],
                    [InlineKeyboardButton("⏹ Stop", callback_data=f"admin_stop_user_{target_id}")],
                    [InlineKeyboardButton("📄 Get report", callback_data=f"admin_get_report_{target_id}")],
                ]
                if CHARTS_AVAILABLE:
                    keyboard.append([InlineKeyboardButton("📈 Get chart", callback_data=f"admin_get_chart_{target_id}")])
                keyboard.extend([
                    [InlineKeyboardButton("⬅️ Back to list", callback_data="admin_user_list")],
                ])
                await query.edit_message_text(
                    f"Managing: <b>{html.escape(user_target['full_name'])}</b> (ID {target_id})",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="HTML",
                )
            else:
                # show doctor-specific admin options
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
            try:
                doctor_id = int(query.data.split("_")[-1])
                
                # Get doctor info
                doctor_data = api_get(f"users/{doctor_id}")
                if not doctor_data:
                    await query.edit_message_text("Doctor not found.")
                    return
                
                # Get doctor's patients
                patients = get_doctor_patients(doctor_id)
                
                if not patients:
                    await query.edit_message_text(
                        f"Dr. {doctor_data['full_name']} has no assigned patients.\n\n"
                        f"Use /menu to return to main menu."
                    )
                    return
        
                keyboard = []
                for patient in patients:
                    keyboard.append([InlineKeyboardButton(
                        f"{patient['full_name']} (ID: {patient['user_chat_id']})",
                        callback_data=f"admin_view_patient_{patient['user_chat_id']}"
                    )])
                keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data=f"admin_user_{doctor_id}")])
                
                await query.edit_message_text(
                    f"👥 Dr. {doctor_data['full_name']}'s Patients ({len(patients)}):",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
            except (ValueError, IndexError) as e:
                logger.error(f"Error parsing doctor ID: {e}")
                await query.edit_message_text("Invalid doctor selection.")

        elif query.data.startswith("admin_doctor_info_") and admin_mode:
            try:
                doctor_id = int(query.data.split("_")[-1])
                
                # Get doctor info
                doctor_data = api_get(f"users/{doctor_id}")
                if not doctor_data:
                    await query.edit_message_text("Doctor not found.")
                    return
                
                # Get patient count
                patients = get_doctor_patients(doctor_id)
                patient_count = len(patients) if patients else 0
                
                info_text = f"""
        👨‍⚕️ <b>Doctor Information</b>

        <b>Name:</b> {html.escape(doctor_data['full_name'])}
        <b>ID:</b> {doctor_id}
        <b>Specialization:</b> {html.escape(doctor_data.get('specialization', 'Not specified'))}
        <b>Hospital:</b> {html.escape(doctor_data.get('hospital', 'Not specified'))}
        <b>Assigned Patients:</b> {patient_count}
        <b>User Type:</b> {doctor_data.get('user_type', 'unknown').title()}
                """
                
                keyboard = [
                    [InlineKeyboardButton("👥 View Patients", callback_data=f"admin_doctor_patients_{doctor_id}")],
                    [InlineKeyboardButton("🗑️ Remove Doctor", callback_data=f"admin_delete_user_{doctor_id}")],
                    [InlineKeyboardButton("⬅️ Back", callback_data=f"admin_user_{doctor_id}")]
                ]
                
                await query.edit_message_text(
                    info_text,
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
            except (ValueError, IndexError) as e:
                logger.error(f"Error parsing doctor ID: {e}")
                await query.edit_message_text("Invalid doctor selection.")

        elif query.data.startswith("admin_view_patient_") and admin_mode:
            try:
                patient_id = int(query.data.split("_")[-1])
                
                # Get patient info
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
                    parse_mode="HTML"
                )
                
            except (ValueError, IndexError) as e:
                logger.error(f"Error parsing patient ID: {e}")
                await query.edit_message_text("Invalid patient selection.")

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
            # Show time period selection for admin
            keyboard = [
                [InlineKeyboardButton("📊 Last 24 hours", callback_data=f"admin_chart_24h_{target_id}")],
                [InlineKeyboardButton("📊 Last 48 hours", callback_data=f"admin_chart_48h_{target_id}")],
                [InlineKeyboardButton("📊 Last 72 hours", callback_data=f"admin_chart_72h_{target_id}")],
                [InlineKeyboardButton("📊 Last week", callback_data=f"admin_chart_week_{target_id}")],
                [InlineKeyboardButton("❌ Back", callback_data=f"admin_user_{target_id}")]
            ]
            await query.edit_message_text(
                f"📈 Select chart time period for user {target_id}:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        # Add admin chart time period handlers
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

    except Exception as e:
        logger.error(f"Error in button handler: {e}")
        logger.error(traceback.format_exc())
        try:
            await query.edit_message_text("❌ An error occurred. Please try again.")
        except:
            pass


async def register_doctor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id
        
        if len(context.args) < 2:
            await update.message.reply_text(
                "Register as doctor:\n"
                "/register_doctor <Full Name> <Specialization> [Hospital]\n\n"
                "Example: /register_doctor Dr. Sarah Johnson Cardiology General Hospital"
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
        
        doctor_data = {
            "user_chat_id": chat_id,
            "full_name": full_name,
            "specialization": specialization,
            "hospital": hospital
        }
        
        if api_post("doctors", doctor_data):
            await update.message.reply_text(
                f"✅ Successfully registered as doctor!\n\n"
                f"Name: {full_name}\n"
                f"Specialization: {specialization}\n"
                f"Hospital: {hospital}\n\n"
                f"Use /menu to access doctor functions."
            )
        else:
            await update.message.reply_text(
                "❌ Registration failed. You may already be registered or there was an error."
            )
            
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
            await update.message.reply_text("Please provide your new name: /update_doctor_name <Your Name>")
            return
        
        new_name = " ".join(context.args)
        update_data = {"full_name": new_name}
        
        if api_put(f"users/{chat_id}", update_data):
            await update.message.reply_text(f"✅ Name updated to: {new_name}")
        else:
            await update.message.reply_text("❌ Failed to update name. Please try again.")
            
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
            await update.message.reply_text("Please provide your specialization: /update_doctor_specialization <Specialization>")
            return
        
        new_specialization = " ".join(context.args)
        
        # Get current user data
        user_data = api_get(f"users/{chat_id}")
        if not user_data:
            await update.message.reply_text("❌ Could not retrieve your profile.")
            return
        
        # Update specialization
        user_data["specialization"] = new_specialization
        
        if api_put(f"users/{chat_id}", user_data):
            await update.message.reply_text(f"✅ Specialization updated to: {new_specialization}")
        else:
            await update.message.reply_text("❌ Failed to update specialization. Please try again.")
            
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
            await update.message.reply_text("Please provide your hospital: /update_doctor_hospital <Hospital Name>")
            return
        
        new_hospital = " ".join(context.args)
        
        # Get current user data
        user_data = api_get(f"users/{chat_id}")
        if not user_data:
            await update.message.reply_text("❌ Could not retrieve your profile.")
            return
        
        # Update hospital
        user_data["hospital"] = new_hospital
        
        if api_put(f"users/{chat_id}", user_data):
            await update.message.reply_text(f"✅ Hospital updated to: {new_hospital}")
        else:
            await update.message.reply_text("❌ Failed to update hospital. Please try again.")
            
    except Exception as e:
        logger.error(f"Error updating doctor hospital: {e}")
        await update.message.reply_text("Update failed. Please try again.")

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

        # Core commands
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("register", register))
        application.add_handler(CommandHandler("menu", menu))
        application.add_handler(CommandHandler("register_doctor", register_doctor))
        application.add_handler(CommandHandler("update_doctor_name", update_doctor_name))
        application.add_handler(CommandHandler("update_doctor_specialization", update_doctor_specialization))
        application.add_handler(CommandHandler("update_doctor_hospital", update_doctor_hospital))

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
    