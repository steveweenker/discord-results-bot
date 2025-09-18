# Discord Webhook Results Bot
import asyncio
import io
import logging
import os
import signal
import sys
import time
from typing import List
from datetime import datetime
import json

import aiohttp
import requests
from dotenv import load_dotenv

# ----------- ENVIRONMENT & CONFIGURATION -----------
load_dotenv()
DISCORD_WEBHOOK = os.getenv('DISCORD_WEBHOOK')
URL = 'https://results.beup.ac.in/BTech1stSem2024_B2024Results.aspx'
RESULT_URL_TEMPLATE = 'https://results.beup.ac.in/ResultsBTech1stSem2024_B2024Pub.aspx?Sem=I&RegNo={reg_no}'
REG_NO_FILE = 'registration_numbers.txt'

if not DISCORD_WEBHOOK:
    raise ValueError("DISCORD_WEBHOOK environment variable is required")

BATCH_SIZE = 20
PARALLEL_REQUESTS = 10
MESSAGE_DELAY = 1
RETRY_MAX_ATTEMPTS = 3
CHECK_INTERVAL = 1  # seconds
ERROR_NOTIFICATION_INTERVAL = 3600  # 1 hour in seconds

# ----------- LOGGING SETUP -----------
logging.basicConfig(
    format='%(asctime)s %(levelname)s: %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ----------- DISCORD WEBHOOK FUNCTIONS -----------
async def send_discord_message(message: str):
    """Send a simple text message to Discord"""
    try:
        payload = {
            "content": message,
            "username": "Result Monitor Bot",
            "avatar_url": "https://cdn.discordapp.com/embed/avatars/0.png"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(DISCORD_WEBHOOK, json=payload) as response:
                if response.status == 204:
                    logger.info("Discord message sent successfully")
                else:
                    logger.error(f"Discord error: {response.status}")
                    
        await asyncio.sleep(MESSAGE_DELAY)
    except Exception as e:
        logger.error(f"Discord send error: {e}")

async def send_discord_embed(title: str, description: str, color: int = 0x00ff00, fields: List[dict] = None):
    """Send a rich embed message to Discord"""
    try:
        embed = {
            "title": title,
            "description": description,
            "color": color,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {
                "text": "Result Monitor Bot",
                "icon_url": "https://cdn.discordapp.com/embed/avatars/0.png"
            }
        }
        
        if fields:
            embed["fields"] = fields
            
        payload = {
            "username": "Result Monitor Bot",
            "embeds": [embed]
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(DISCORD_WEBHOOK, json=payload) as response:
                if response.status == 204:
                    logger.info("Discord embed sent successfully")
                else:
                    logger.error(f"Discord error: {response.status}")
                    
        await asyncio.sleep(MESSAGE_DELAY)
    except Exception as e:
        logger.error(f"Discord embed error: {e}")

async def send_discord_file(reg_no: str, html_content: str):
    """Send HTML file to Discord as attachment"""
    try:
        # Create file-like object
        files = {
            'file': (f"{reg_no}_result.html", html_content, 'text/html')
        }
        
        data = {
            "content": f"📄 **Result file for {reg_no}**"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(DISCORD_WEBHOOK, data=data, data=files) as response:
                if response.status == 204:
                    logger.info(f"Discord file sent for {reg_no}")
                    return True
                else:
                    logger.error(f"Discord file error: {response.status}")
                    return False
    except Exception as e:
        logger.error(f"Failed to send file for {reg_no}: {e}")
        return False

# ----------- UTILITY FUNCTIONS -----------
def clean_registration_number(reg_no: str) -> str:
    reg_no = reg_no.strip()
    return reg_no if reg_no.isdigit() and len(reg_no) == 11 else ""

def is_result_html(html: str) -> bool:
    return ("Student Name:" in html or "Registration No:" in html)

def is_website_down_html(html: str) -> bool:
    down_keywords = ["HTTP Error 503", "Service Unavailable"]
    return any(kw in html for kw in down_keywords)

# ----------- ASYNC OPERATIONS -----------
async def fetch_result_html(session: aiohttp.ClientSession, reg_no: str) -> str:
    url = RESULT_URL_TEMPLATE.format(reg_no=reg_no)
    for attempt in range(RETRY_MAX_ATTEMPTS):
        try:
            async with session.get(url, timeout=10) as response:
                html = await response.text()
                if is_website_down_html(html):
                    logger.warning(f"Website overloaded for {reg_no}. Retrying...")
                    await asyncio.sleep(2 ** attempt)
                    continue
                if "Invalid Registration Number" in html:
                    return None
                return html if is_result_html(html) else None
        except Exception as e:
            logger.error(f"Fetch error for {reg_no} (attempt {attempt + 1}): {e}")
            await asyncio.sleep(2 ** attempt)
    return None

async def process_batch(session: aiohttp.ClientSession, batch: List[str]):
    semaphore = asyncio.Semaphore(PARALLEL_REQUESTS)

    async def process_single(reg_no: str):
        clean_reg = clean_registration_number(reg_no)
        if not clean_reg:
            await send_discord_message(f"❌ **Invalid format:** {reg_no}")
            return None, None
        async with semaphore:
            html_content = await fetch_result_html(session, clean_reg)
            return reg_no, html_content

    tasks = [process_single(reg_no) for reg_no in batch]
    results = await asyncio.gather(*tasks)
    successful = []
    
    for reg_no, html_content in results:
        if html_content:
            # Send rich embed notification
            await send_discord_embed(
                title="🎯 Result Found!",
                description=f"Successfully found result for registration number: **{reg_no}**",
                color=0x00ff00,  # Green
                fields=[
                    {"name": "Registration Number", "value": reg_no, "inline": True},
                    {"name": "Status", "value": "✅ Available", "inline": True},
                    {"name": "Time", "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "inline": True}
                ]
            )
            
            # Send file attachment
            sent = await send_discord_file(reg_no, html_content)
            if sent:
                successful.append(reg_no)
            else:
                await send_discord_message(f"⚠️ **File send failed for:** {reg_no}")
        else:
            await send_discord_message(f"❌ **No result found for:** {reg_no}")
    
    return successful

async def process_registration_file():
    if not os.path.exists(REG_NO_FILE):
        await send_discord_message(f"❌ **File not found:** `{REG_NO_FILE}`")
        return
    
    try:
        with open(REG_NO_FILE, 'r') as f:
            reg_nos = list(dict.fromkeys(line.strip() for line in f if line.strip()))
    except Exception as e:
        logger.error(f"Error reading file: {e}")
        await send_discord_message(f"⚠️ **File error:** {e}")
        return
    
    if not reg_nos:
        await send_discord_message("❌ **No registration numbers found**")
        return
    
    total = len(reg_nos)
    await send_discord_embed(
        title="🚀 Processing Started",
        description=f"Processing **{total}** registration numbers in batches of **{BATCH_SIZE}**",
        color=0x0099ff,  # Blue
        fields=[
            {"name": "Total Numbers", "value": str(total), "inline": True},
            {"name": "Batch Size", "value": str(BATCH_SIZE), "inline": True},
            {"name": "Started At", "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "inline": True}
        ]
    )
    
    async with aiohttp.ClientSession() as session:
        all_successful = []
        for i in range(0, total, BATCH_SIZE):
            batch = reg_nos[i:i + BATCH_SIZE]
            batch_num = (i // BATCH_SIZE) + 1
            total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
            
            await send_discord_message(f"🔄 **Processing batch {batch_num}/{total_batches}** ({len(batch)} numbers)")
            
            successful = await process_batch(session, batch)
            all_successful.extend(successful)
            await asyncio.sleep(1)
        
        # Final summary with rich embed
        success_rate = (len(all_successful) / total * 100) if total > 0 else 0
        embed_color = 0x00ff00 if success_rate > 50 else 0xff9900 if success_rate > 0 else 0xff0000
        
        await send_discord_embed(
            title="📊 Processing Complete!",
            description="Result monitoring has finished processing all registration numbers.",
            color=embed_color,
            fields=[
                {"name": "✅ Successful", "value": str(len(all_successful)), "inline": True},
                {"name": "❌ Failed", "value": str(total - len(all_successful)), "inline": True},
                {"name": "📈 Success Rate", "value": f"{success_rate:.1f}%", "inline": True},
                {"name": "📋 Total Processed", "value": str(total), "inline": True},
                {"name": "⏱️ Completed At", "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "inline": True}
            ]
        )

async def monitor_website(shutdown_event: asyncio.Event):
    last_error_notification = 0
    is_first_check = True
    
    print("🔍 Discord monitoring started (checks every second)...")
    logger.info("🔍 Discord monitoring started (checks every second)...")
    
    await send_discord_embed(
        title="🔍 Monitoring Started",
        description="Result monitoring bot is now active and checking for updates every second.",
        color=0x0099ff,  # Blue
        fields=[
            {"name": "Check Interval", "value": f"{CHECK_INTERVAL} second(s)", "inline": True},
            {"name": "Target URL", "value": URL, "inline": False},
            {"name": "Started At", "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "inline": True}
        ]
    )

    async with aiohttp.ClientSession() as session:
        while not shutdown_event.is_set():
            current_time = time.time()
            try:
                async with session.get(URL, timeout=10) as response:
                    html = await response.text()
                    if response.status == 200 and is_result_html(html):
                        # RESULTS ARE LIVE!
                        print("🌐 Website LIVE! Results published! Starting processing...")
                        logger.info("🌐 Website LIVE! Results published! Starting processing...")
                        
                        await send_discord_embed(
                            title="🌐 RESULTS LIVE!",
                            description="**The exam results are now published!** Starting automatic processing...",
                            color=0x00ff00,  # Bright green
                            fields=[
                                {"name": "Status", "value": "✅ Results Available", "inline": True},
                                {"name": "Action", "value": "🚀 Auto-processing started", "inline": True},
                                {"name": "Detected At", "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "inline": True}
                            ]
                        )
                        
                        await process_registration_file()
                        break
                        
                    elif is_website_down_html(html):
                        if current_time - last_error_notification >= ERROR_NOTIFICATION_INTERVAL or is_first_check:
                            print("⚠️ Website overload: Service Unavailable (HTTP 503)")
                            logger.warning("⚠️ Website overload: Service Unavailable (HTTP 503)")
                            await send_discord_message("⚠️ **Website overloaded:** Service Unavailable (HTTP 503)")
                            last_error_notification = current_time
                            is_first_check = False
                    else:
                        print("✓ Website checked; result not yet live.")
                        logger.info("Website checked; result not yet live.")
                        
            except Exception as e:
                if current_time - last_error_notification >= ERROR_NOTIFICATION_INTERVAL or is_first_check:
                    error_msg = f"❌ **Website DOWN** - {type(e).__name__}: {str(e)}"
                    print(error_msg)
                    logger.error(error_msg)
                    await send_discord_message(error_msg)
                    last_error_notification = current_time
                    is_first_check = False
                    
            await asyncio.sleep(CHECK_INTERVAL)

# Graceful shutdown event
shutdown_event = asyncio.Event()

def shutdown_handler():
    print("\n🛑 Received shutdown signal (Ctrl+C). Stopping tasks...")
    logger.info("Received shutdown signal. Stopping tasks...")
    shutdown_event.set()

def setup_signal_handlers():
    if sys.platform == "win32":
        signal.signal(signal.SIGINT, lambda s, f: shutdown_handler())
        signal.signal(signal.SIGTERM, lambda s, f: shutdown_handler())
    else:
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, shutdown_handler)

async def main():
    print("🚀 Starting Discord Results Bot...")
    print("📁 Make sure 'registration_numbers.txt' file exists in the same directory")
    print("⚙️ Configure DISCORD_WEBHOOK in .env file or environment variable")
    print("🔄 Press Ctrl+C to stop the bot gracefully\n")

    # Setup signal handlers
    setup_signal_handlers()

    # Start monitoring
    monitor_task = asyncio.create_task(monitor_website(shutdown_event))

    print("✅ Bot is now running and monitoring!")
    
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass
    finally:
        print("🛑 Shutting down bot...")
        await send_discord_message("🛑 **Result monitoring stopped**")
        print("✅ Bot shutdown complete!")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user (Ctrl+C)")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        logger.error(f"Fatal error: {e}")