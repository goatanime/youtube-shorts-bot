from keep_alive import keep_alive
import os
import re
import logging
import sqlite3
import requests
import validators
import yt_dlp
from datetime import datetime, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# Configuration
BOT_TOKEN = "7200682052:AAEqqGkBhoQJ4_l4ukQbzSM-4AssyPRLFIA"
SHORTENER_TOKEN = "0f40e7c1f77af23bfabbd4f2afcbeb59bc3b3636"
SHORTENER_API = "https://shrinkearn.com/api"
DOWNLOAD_DIR = "downloads"

# Create download directory if not exists
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Database setup
conn = sqlite3.connect('users.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users
             (user_id INTEGER PRIMARY KEY, access_time TEXT)''')
conn.commit()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def generate_short_url(bot_username: str) -> str:
    """Generate monetized short URL using ShrinkEarn API"""
    deep_link = f"https://t.me/{bot_username}?start=shorte"
    params = {
        'api': SHORTENER_TOKEN,
        'url': deep_link
    }
    try:
        response = requests.get(SHORTENER_API, params=params, timeout=10)
        data = response.json()
        if data.get('status') == 'success':
            return data['shortenedUrl']
        logger.error(f"Shortener API error: {data}")
    except Exception as e:
        logger.error(f"Shortener request failed: {e}")
    return deep_link  # Fallback to direct link

def has_valid_access(user_id: int) -> bool:
    """Check if user has valid 24-hour access"""
    c.execute("SELECT access_time FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    if result:
        try:
            # Parse stored time as UTC
            access_time = datetime.fromisoformat(result[0]).replace(tzinfo=timezone.utc)
            now_utc = datetime.now(timezone.utc)
            return (now_utc - access_time) < timedelta(hours=24)
        except Exception as e:
            logger.error(f"Access time error: {e}")
    return False

def is_valid_shorts_url(url: str) -> bool:
    """Check if URL is a valid YouTube Shorts URL"""
    patterns = [
        r'https?://(?:www\.)?youtube\.com/shorts/[a-zA-Z0-9_-]+',
        r'https?://youtu\.be/[a-zA-Z0-9_-]+',
        r'https?://(?:www\.)?youtube\.com/watch\?v=[a-zA-Z0-9_-]+'
    ]
    return any(re.search(pattern, url) for pattern in patterns)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bot_username = (await context.bot.get_me()).username
    
    # Check for deep link parameter
    if context.args and context.args[0] == "shorte":
        # Grant 24-hour access (timezone-aware UTC)
        now_utc = datetime.now(timezone.utc)
        c.execute("REPLACE INTO users (user_id, access_time) VALUES (?, ?)",
                  (user_id, now_utc.isoformat()))
        conn.commit()
        await update.message.reply_text(
            "🎉 Premium Access Activated for 24 Hours!\n"
            "Send me any YouTube Shorts URL to download."
        )
    else:
        if has_valid_access(user_id):
            await update.message.reply_text(
                "🌟 Welcome back!\n"
                "Send me a YouTube Shorts URL to download"
            )
        else:
            short_url = generate_short_url(bot_username)
            keyboard = [[InlineKeyboardButton("🔥 GET FREE ACCESS", url=short_url)]]
            await update.message.reply_text(
                "🔒 Premium Access Required!\n\n"
                "👉 You must use our sponsor link to activate 24-hour free access:\n\n"
                f"{short_url}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

async def download_youtube_shorts(url: str, user_id: int) -> str:
    """Download YouTube Shorts using yt-dlp with simplified approach"""
    # Generate a unique filename
    timestamp = int(datetime.now().timestamp())
    filename = f"shorts_{user_id}_{timestamp}"
    file_path = os.path.join(DOWNLOAD_DIR, f"{filename}.mp4")
    
    # Simple and reliable download options
    ydl_opts = {
        'outtmpl': file_path.replace('.mp4', '.%(ext)s'),
        'format': 'best',
        'merge_output_format': 'mp4',
        'retries': 5,
        'fragment_retries': 5,
        'ignoreerrors': False,
        'no_warnings': True,
        'quiet': True,
        'noplaylist': True,
        'restrictfilenames': True,
        'windowsfilenames': True,
        'nooverwrites': True,
        'continuedl': True,
        'noprogress': True,
        'consoletitle': False,
        'prefer_insecure': False,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Download directly without intermediate steps
            info = ydl.extract_info(url, download=True)
            
            # Get the actual filename generated
            actual_filename = ydl.prepare_filename(info)
            
            # Ensure we have an mp4 file
            if not actual_filename.endswith('.mp4'):
                actual_filename = f"{os.path.splitext(actual_filename)[0]}.mp4"
            
            return actual_filename
            
    except yt_dlp.utils.DownloadError as e:
        logger.error(f"Download failed: {e}")
        raise Exception("YouTube download error") from e
    except Exception as e:
        logger.error(f"Unexpected download error: {e}")
        raise Exception("Video download failed") from e

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bot_username = (await context.bot.get_me()).username
    url = update.message.text.strip()
    
    # Validate URL
    if not is_valid_shorts_url(url):
        await update.message.reply_text("❌ Please send a valid YouTube Shorts URL\n\n"
                                       "Examples:\n"
                                       "• https://youtube.com/shorts/VIDEO_ID\n"
                                       "• https://youtu.be/VIDEO_ID")
        return
    
    # Check access
    if not has_valid_access(user_id):
        short_url = generate_short_url(bot_username)
        keyboard = [[InlineKeyboardButton("🔥 RENEW ACCESS", url=short_url)]]
        await update.message.reply_text(
            "⏱️ Your access has expired!\n\n"
            "Renew your 24-hour access by visiting our sponsor link:\n\n"
            f"{short_url}",
            reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    try:
        # Download YouTube Shorts
        msg = await update.message.reply_text("⏬ Downloading your video...")
        
        # Download video using yt-dlp
        video_path = await download_youtube_shorts(url, user_id)
        
        # Check if file exists
        if not os.path.exists(video_path):
            # Try with .mp4 extension if not found
            if not video_path.endswith('.mp4'):
                mp4_path = f"{os.path.splitext(video_path)[0]}.mp4"
                if os.path.exists(mp4_path):
                    video_path = mp4_path
                else:
                    raise FileNotFoundError("Downloaded file not found")
        
        # Edit message to show success
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=msg.message_id,
            text="✅ Video downloaded! Sending now..."
        )
        
        # Send video
        with open(video_path, 'rb') as video_file:
            await update.message.reply_video(
                video=video_file,
                caption=f"Downloaded via @{bot_username}",
                supports_streaming=True,
                read_timeout=120,
                write_timeout=120,
                connect_timeout=120
            )
        
        # Clean up
        if os.path.exists(video_path):
            os.remove(video_path)
        
    except Exception as e:
        logger.error(f"Download error: {e}", exc_info=True)
        await update.message.reply_text("❌ Failed to download video. Please try again later or use a different URL.")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update caused error: {context.error}", exc_info=True)
    if isinstance(update, Update) and update.message:
        await update.message.reply_text("⚠️ An internal error occurred. Please try again later.")

def main() -> None:
    """Run the bot."""
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    
    logger.info("Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    keep_alive()
    main()
