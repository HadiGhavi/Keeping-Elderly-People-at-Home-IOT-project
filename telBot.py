import html   
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    JobQueue
)
import aiohttp
import pytz
import tzlocal
import logging
import json
import asyncio

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# REST API configuration
REST_API_URL = "http://localhost:5000"

# Conversation states
ADD_SENSOR, ADD_SITUATION, SENSOR_DETAILS, UPDATE_PROFILE = range(4)

# Helper functions for API calls
def api_get(endpoint):
    try:
        response = requests.get(f"{REST_API_URL}/{endpoint}")
        return response.json() if response.status_code == 200 else None
    except requests.exceptions.RequestException as e:
        logger.error(f"API GET error: {e}")
        return None

def api_post(endpoint, data):
    try:
        response = requests.post(f"{REST_API_URL}/{endpoint}", json=data)
        return response.status_code == 201
    except requests.exceptions.RequestException as e:
        logger.error(f"API POST error: {e}")
        return False

def api_put(endpoint, data):
    try:
        response = requests.put(f"{REST_API_URL}/{endpoint}", json=data)
        return response.status_code == 200
    except requests.exceptions.RequestException as e:
        logger.error(f"API PUT error: {e}")
        return False

def api_delete(endpoint):
    try:
        response = requests.delete(f"{REST_API_URL}/{endpoint}")
        return response.status_code == 200
    except requests.exceptions.RequestException as e:
        logger.error(f"API DELETE error: {e}")
        return False

# Telegram Bot Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user =  api_get(f"users/{chat_id}")
    print(user)
    if user:
        await update.message.reply_text(
            f"👋 Welcome back, {user['full_name']}!\n"
            "Use /menu to manage your health data."
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
    
    full_name = ' '.join(context.args)
    if  api_post("users", {"user_chat_id": chat_id, "full_name": full_name}):
        await update.message.reply_text(
            f"✅ Registration successful, {full_name}!\n"
            "Use /menu to manage your health data."
        )
    else:
        await update.message.reply_text("❌ Registration failed. Please try again.")

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not  api_get(f"users/{chat_id}"):
        await update.message.reply_text("Please register first with /register <your name>")
        return
    
    keyboard = [
        [InlineKeyboardButton("👤 My Profile", callback_data='profile')],
        [InlineKeyboardButton("📟 My Sensors", callback_data='sensors')],
        [InlineKeyboardButton("⚠️ Sensitive Situations", callback_data='situations')],
        [
         InlineKeyboardButton("📟 run Sensor", callback_data='run_sensor'),
        ],
        [
            InlineKeyboardButton("➕ Add Sensor", callback_data='add_sensor'),
            InlineKeyboardButton("➕ Add Situation", callback_data='add_situation')
        ],
        [
            InlineKeyboardButton("🔄 Update Profile", callback_data='update_profile'),
            InlineKeyboardButton("🗑️ Delete Profile", callback_data='delete_profile')
        ],
        [
            InlineKeyboardButton("➕ Get Report", callback_data='get_report')
        ]
    ]
    
    await update.message.reply_text(
        "📋 Main Menu:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    user =  api_get(f"users/{chat_id}")
    
    if not user:
        await query.edit_message_text("Please register first with /register <your name>")
        return
    
    if query.data == 'profile':
        sensors =  api_get(f"sensors/{chat_id}") or []
        situations =  api_get(f"situations/{chat_id}") or []
        
        profile_text = (
            f"👤 <b>Health Profile</b>\n\n"
            f"🆔 <b>ID:</b> {user['user_chat_id']}\n"
            f"👨‍⚕️ <b>Name:</b> {user['full_name']}\n"
            f"📊 <b>Monitoring:</b>\n"
            f"   - Sensors: {len(sensors)}\n"
            f"   - Sensitive Situations: {len(situations)}\n\n"
            f"Use /update_profile to change your name"
        )
        await query.edit_message_text(profile_text, parse_mode='HTML')
    elif query.data == 'run_sensor':
        sensor_services =  api_get(f"services/sensor")
        print(sensor_services)
        read_res = requests.get(sensor_services["url"] + str(chat_id))
        if read_res.status_code == 200:
            res = read_res.json()
            if not res:
                profile_text = "you dont have sersor"
                await query.edit_message_text(profile_text, parse_mode='HTML')
            
            profile_text = "running sensors..."
            await query.edit_message_text(profile_text, parse_mode='HTML')
        else:
            profile_text = "Failed to fetch your sensor. Please try again later"
            await query.edit_message_text(profile_text, parse_mode='HTML')

    elif query.data == 'sensors':
        sensors =  api_get(f"sensors/{chat_id}")
        if not sensors:
            await query.edit_message_text("You don't have any sensors registered.")
            return
        
        sensor_list = []
        for sensor in sensors:
            sensor_list.append(
                f"🔹 <b>{html.escape(sensor['name'])}</b> (ID: {sensor['id']})\n"
                f"   🔺 Max: {sensor['max_level_alert']} | "
                f"🔻 Min: {sensor['min_level_alert']}"
            )
        
        message = (
            "📡 <b>Your Health Sensors</b>\n\n" +
            "\n\n".join(sensor_list) +
            "\n\n"
            "Use /delete_sensor &lt;id&gt; to remove sensors"
        )
        
        await query.edit_message_text(
            text=message,
            parse_mode='HTML'
        )
    elif query.data.startswith('delete_sensor_'):
        sensor_id = query.data.split('_')[-1]
        if  api_delete(f"sensors/{chat_id}/{sensor_id}"):
            await query.edit_message_text(f"✅ Sensor with ID {sensor_id} deleted successfully!")
        else:
            await query.edit_message_text("❌ Failed to delete sensor. Please try again.")
    elif query.data.startswith('delete_sit_'):
        sit = query.data.split('_')[-1]
        if  api_delete(f"situations/{chat_id}/{sit}"):
            await query.edit_message_text(f"✅ situation {sit} deleted successfully!")
        else:
            await query.edit_message_text("❌ Failed to delete situation. Please try again.")
    elif query.data == 'situations':
        situations =  api_get(f"situations/{chat_id}")
        if not situations:
            await query.edit_message_text("No sensitive situations registered.")
            return
        
        escaped_situations = [html.escape(sit) for sit in situations]
        situation_list = "\n".join(f"⚠️ {situation}" for situation in escaped_situations)
        
        await query.edit_message_text(
            "🚨 <b>Sensitive Situations</b>\n\n" +
            situation_list + "\n\n" +
            "Use /add_situation to add new situations\n" +
            "Use /delete_situation &lt;name&gt; to remove situations",
            parse_mode='HTML'
        )
    
    elif query.data == 'add_sensor':
        context.user_data['action'] = 'add_sensor'
        await query.edit_message_text(
            "🆕 <b>Add New Sensor</b>\n\n"
            "You must have at least 3 sensors whose names contain (temp,heart_rate,oxygen).\n"
            "Please send sensor details in this format:\n"
            "<code>name id max_alert min_alert</code>\n\n"
            "Example:\n"
            "<code>heart_rate 1 100 60</code>",
            parse_mode='HTML'
        )
        return SENSOR_DETAILS
    
    elif query.data == 'add_situation':
        context.user_data['action'] = 'add_situation'
        await query.edit_message_text(
            "⚠️ <b>Add Sensitive Situation</b>\n\n"
            "Please describe the situation you want to add:",
            parse_mode='HTML'
        )
        return ADD_SITUATION
    
    elif query.data == 'update_profile':
        context.user_data['action'] = 'update_profile'
        await query.edit_message_text(
            "🔄 <b>Update Profile</b>\n\n"
            "Please enter your new full name:",
            parse_mode='HTML'
        )
        return UPDATE_PROFILE
    
    elif query.data == 'delete_profile':
        keyboard = [
            [
                InlineKeyboardButton("Yes, delete my data", callback_data=f'confirm_delete_{chat_id}'),
                InlineKeyboardButton("Cancel", callback_data='cancel_delete')
            ]
        ]
        
        await query.edit_message_text(
            "⚠️ <b>Are you sure you want to delete your profile and all associated data?</b>\n"
            "This action cannot be undone!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    
    elif query.data.startswith('confirm_delete_'):
        target_user = int(query.data.split('_')[-1])
        if  api_delete(f"users/{target_user}"):
            await query.edit_message_text("✅ Your profile and all data have been deleted.")
        else:
            await query.edit_message_text("❌ Failed to delete profile. Please try again.")
    
    elif query.data == 'cancel_delete':
        await query.edit_message_text("Profile deletion cancelled.")
    elif query.data== 'get_report':
        try:
            panel_services =  api_get(f"services/adminPanel")
            read_res = requests.get(panel_services["url"] +":"+str(panel_services["port"])+"/report/" + str(chat_id))
            json_convert = read_res.json()
            print(json_convert)

            if len(json_convert) != 0:
                await query.edit_message_text(json_convert[:4], parse_mode='HTML')
            else:
                await query.edit_message_text("not found report")
        
        except Exception as e:
            logger.error(f"Error : {e}")
            await query.edit_message_text("An error occurred while fetching your sensor.")

async def handle_sensor_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    try:
        parts = update.message.text.split()
        if len(parts) != 4:
            raise ValueError
        
        name, sensor_id, max_alert, min_alert = parts
        sensor_data = {
            "id": int(sensor_id),
            "name": name,
            "max_level_alert": float(max_alert),
            "min_level_alert": float(min_alert)
        }
        
        if  api_post(f"sensors/{chat_id}", sensor_data):
            await update.message.reply_text("✅ Sensor added successfully!")
        else:
            await update.message.reply_text("❌ Failed to add sensor. Please try again.")
    except (ValueError, IndexError):
        await update.message.reply_text(
            "Invalid format. Please use:\n"
            "<code>name id max_alert min_alert</code>\n\n"
            "Example:\n"
            "<code>heart_rate 1 100 60</code>",
            parse_mode='HTML'
        )
        return SENSOR_DETAILS
    
    return ConversationHandler.END

async def delete_sensor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if not context.args:
        sensors =  api_get(f"sensors/{chat_id}")
        if not sensors:
            await update.message.reply_text("You don't have any sensors to delete.")
            return
        
        keyboard = [
            [InlineKeyboardButton(f"{sensor['name']} (ID: {sensor['id']})", 
                                callback_data=f'delete_sensor_{sensor["id"]}')]
            for sensor in sensors
        ]
        keyboard.append([InlineKeyboardButton("Cancel", callback_data='cancel_delete')])
        
        await update.message.reply_text(
            "Select a sensor to delete:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    try:
        sensor_id = int(context.args[0])
        if  api_delete(f"sensors/{chat_id}/{sensor_id}"):
            await update.message.reply_text(f"✅ Sensor with ID {sensor_id} deleted successfully!")
        else:
            await update.message.reply_text("❌ Failed to delete sensor. Please try again.")
    except ValueError:
        await update.message.reply_text("Invalid sensor ID. Please provide a numeric ID.")

async def handle_situation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    situation = update.message.text
    
    if  api_post(f"situations/{chat_id}", {"situation": situation}):
        await update.message.reply_text("✅ Situation added successfully!")
    else:
        await update.message.reply_text("❌ Failed to add situation. Please try again.")
    
    return ConversationHandler.END

async def update_profile_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    new_name = update.message.text
    
    if  api_put(f"users/{chat_id}", {"full_name": new_name}):
        await update.message.reply_text(f"✅ Profile updated successfully! New name: {new_name}")
    else:
        await update.message.reply_text("❌ Failed to update profile. Please try again.")
    
    return ConversationHandler.END

async def delete_situation_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if not context.args:
        situations =  api_get(f"situations/{chat_id}") or []
        if not situations:
            await update.message.reply_text("You don't have any sensitive situations to delete.")
            return
        
        keyboard = [
            [InlineKeyboardButton(sit, callback_data=f'delete_sit_{sit}')]
            for sit in situations
        ]
        keyboard.append([InlineKeyboardButton("Cancel", callback_data='cancel_delete')])
        
        await update.message.reply_text(
            "⚠️ Select a situation to delete:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    situation = ' '.join(context.args)
    if  api_delete(f"situations/{chat_id}/{situation}"):
        await update.message.reply_text(f"✅ Situation '{situation}' deleted successfully!")
    else:
        await update.message.reply_text("❌ Failed to delete situation. Please try again.")

async def update_situation_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if len(context.args) < 2:
        situations =  api_get(f"situations/{chat_id}") or []
        if not situations:
            await update.message.reply_text("You don't have any sensitive situations to update.")
            return
        
        keyboard = [
            [InlineKeyboardButton(sit, callback_data=f'update_sit_{sit}')]
            for sit in situations
        ]
        keyboard.append([InlineKeyboardButton("Cancel", callback_data='cancel_update')])
        
        await update.message.reply_text(
            "Select a situation to update:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    old_situation = context.args[0]
    new_situation = ' '.join(context.args[1:])
    
    if  api_put(f"situations/{chat_id}/{old_situation}", {"new_situation": new_situation}):
        await update.message.reply_text(
            f"✅ Situation updated from '{old_situation}' to '{new_situation}'!"
        )
    else:
        await update.message.reply_text("❌ Failed to update situation. Please try again.")

async def delete_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /delete_user <user_chat_id>")
        return
    
    try:
        target_user = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID. Must be a number.")
        return
    
    if  api_delete(f"users/{target_user}"):
        await update.message.reply_text(f"✅ User {target_user} deleted successfully!")
    else:
        await update.message.reply_text("❌ Failed to delete user. Please try again.")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="Exception while handling update:", exc_info=context.error)
    if update and update.message:
        await update.message.reply_text("An error occurred. Please try again.")

async def get_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    
    try:
        panel_services =  api_get(f"services/adminPanel/{chat_id}")
        json_sensor = panel_services.json()
        print(json_sensor)

        read_res = requests.get(json_sensor["url"] +":"+str(json_sensor["port"])+"/report/" + str(chat_id))
        json_convert = read_res.json()
        if panel_services.status_code == 200:
            
            if not json_convert:
                await update.message.reply_text("You don't have any sensor yet. Use /addsensor to create one.")
                return
            print(json_convert)
            await update.message.reply_text(json_convert[:4], parse_mode='HTML')
        else:
            await update.message.reply_text("Failed to fetch your sensor. Please try again later.")
    
    except Exception as e:
        logger.error(f"Error in find sensor: {e}")
        await update.message.reply_text("An error occurred while fetching your sensor.")

def main():
    """Run the bot."""
    application = Application.builder() \
        .token("7795249101:AAHhhz9iBkBsaWZpj46dXKuVPOmN8RTls") \
        .job_queue(JobQueue()) \
        .build()
    
    # Add all your handlers here (same as before)
    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(button_handler),
            CommandHandler('add_situation', lambda u,c: button_handler(u,c, data='add_situation')),
            CommandHandler('add_sensor', lambda u,c: button_handler(u,c, data='add_sensor'))
        ],
        states={
            SENSOR_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_sensor_details)],
            ADD_SITUATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_situation)],
            UPDATE_PROFILE: [MessageHandler(filters.TEXT & ~filters.COMMAND, update_profile_handler)]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(CommandHandler("delete_situation", delete_situation_command))
    application.add_handler(CommandHandler("update_situation", update_situation_command))
    application.add_handler(CommandHandler("delete_user", delete_user_command))
    application.add_handler(CommandHandler("delete_sensor", delete_sensor))
    application.add_handler(conv_handler)
    application.add_error_handler(error_handler)

    # Run the bot until Ctrl-C is pressed

    application.run_polling()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed with error: {e}")