# Discord Webhook Results Bot - Complete Code with Fixed File Upload

import asyncio
import logging
import os
import signal
import sys
import time
from typing import List
from datetime import datetime

import aiohttp
from dotenv import load_dotenv

# ----------- CONFIGURATION -----------
load_dotenv()
DISCORD_WEBHOOK = os.getenv('DISCORD_WEBHOOK')
URL = 'https://results.beup.ac.in/BTech1stSem2024_B2024Results.aspx'
RESULT_URL_TEMPLATE = 'https://results.beup.ac.in/ResultsBTech1stSem2024_B2024Pub.aspx?Sem=I&RegNo={reg_no}'
REG_NO_FILE = 'registration_numbers.txt'

if not DISCORD_WEBHOOK:
    raise ValueError("DISCORD_WEBHOOK environment variable is required")

# Settings
BATCH_SIZE = 20
PARALLEL_REQUESTS = 10
MESSAGE_DELAY = 1
RETRY_MAX_ATTEMPTS = 3
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '60'))  # Default 60 seconds
ERROR_NOTIFICATION_INTERVAL = 1800  # 30 minutes

# Logging setup
logging.basicConfig(
    format='%(asctime)s %(levelname)s: %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ----------- DISCORD FUNCTIONS -----------
async def send_discord_message(message: str):
    """Send simple text message to Discord"""
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
    """Send rich embed message to Discord"""
    try:
        embed = {
            "title": title,
            "description": description,
            "color": color,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {
                "text": "Result Monitor Bot • GitHub Actions",
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
        form = aiohttp.FormData()
        form.add_field('content', f'📄 **Result file for {reg_no}**')
        form.add_field('file', html_content,
                       filename=f'{reg_no}_result.html',
                       content_type='text/html')

        async with aiohttp.ClientSession() as session:
            async with session.post(DISCORD_WEBHOOK, data=form) as response:
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
    """Clean and validate registration number"""
    reg_no = reg_no.strip()
    return reg_no if reg_no.isdigit() and len(reg_no) == 11 else ""

def is_result_html(html: str) -> bool:
    """Check if HTML contains actual results"""
    return ("Student Name:" in html or "Registration No:" in html)

def is_website_down_html(html: str) -> bool:
    """Check if website is down/overloaded"""
    down_keywords = ["HTTP Error 503", "Service Unavailable", "Server Error"]
    return any(kw in html for kw in down_keywords)

# ----------- RESULT CHECKING -----------
async def fetch_result_html(session: aiohttp.ClientSession, reg_no: str) -> str:
    """Fetch result HTML for registration number"""
    url = RESULT_URL_TEMPLATE.format(reg_no=reg_no)
    for attempt in range(RETRY_MAX_ATTEMPTS):
        try:
            async with session.get(url, timeout=15) as response:
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
    """Process batch of registration numbers"""
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
            await send_discord_embed(
                title="🎯 Result Found!",
                description=f"Successfully found result for registration number: **{reg_no}**",
                color=0x00ff00,
                fields=[
                    {"name": "Registration Number", "value": reg_no, "inline": True},
                    {"name": "Status", "value": "✅ Available", "inline": True},
                    {"name": "Found At", "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "inline": True}
                ]
            )
            sent = await send_discord_file(reg_no, html_content)
            if sent:
                successful.append(reg_no)
            else:
                await send_discord_message(f"⚠️ **File send failed for:** {reg_no}")
        else:
            await send_discord_message(f"❌ **No result found for:** {reg_no}")
    return successful

async def process_registration_file():
    """Process all registration numbers from file"""
    if not os.path.exists(REG_NO_FILE):
        await send_discord_message(f"❌ **File not found:** `{REG_NO_FILE}`")
        return
    try:
        with open(REG_NO_FILE, 'r') as f:
            reg_nos = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            reg_nos = list(dict.fromkeys(reg_nos))
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
        color=0x0099ff,
        fields=[
            {"name": "Total Numbers", "value": str(total), "inline": True},
            {"name": "Batch Size", "value": str(BATCH_SIZE), "inline": True},
            {"name": "Started At", "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "inline": True}
        ]
    )
    async with aiohttp.ClientSession() as session:
        all_successful = []
        total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
        for i in range(0, total, BATCH_SIZE):
            batch = reg_nos[i:i + BATCH_SIZE]
            batch_num = (i // BATCH_SIZE) + 1
            await send_discord_message(f"🔄 **Processing batch {batch_num}/{total_batches}** ({len(batch)} numbers)")
            successful = await process_batch(session, batch)
            all_successful.extend(successful)
            await asyncio.sleep(2)
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

# ----------- MAIN MONITORING -----------
async def monitor_website(shutdown_event: asyncio.Event):
    last_error_notification = 0
    is_first_check = True
    print("🔍 Discord monitoring started...")
    logger.info("Discord monitoring started...")
    await send_discord_embed(
        title="🔍 Monitoring Started",
        description="Result monitoring bot is now active and checking for updates.",
        color=0x0099ff,
        fields=[
            {"name": "Check Interval", "value": f"{CHECK_INTERVAL} seconds", "inline": True},
            {"name": "Target URL", "value": URL, "inline": False},
            {"name": "Started At", "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "inline": True}
        ]
    )
    async with aiohttp.ClientSession() as session:
        while not shutdown_event.is_set():
            current_time = time.time()
            try:
                async with session.get(URL, timeout=15) as response:
                    html = await response.text()
                    if response.status == 200 and is_result_html(html):
                        print("🌐 RESULTS PUBLISHED! Starting processing...")
                        logger.info("Results are now live! Starting processing...")
                        await send_discord_embed(
                            title="🌐 RESULTS LIVE!",
                            description="**The exam results are now published!** Starting automatic processing...",
                            color=0x00ff00,
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
                            await send_discord_message("⚠️ **Website overloaded:** Service Unavailable (HTTP 503)")
                            last_error_notification = current_time
                            is_first_check = False
                    else:
                        print("✓ Website checked; results not yet published.")
            except Exception as e:
                if current_time - last_error_notification >= ERROR_NOTIFICATION_INTERVAL or is_first_check:
                    error_msg = f"❌ **Website check failed** - {type(e).__name__}: {e}"
                    print(error_msg)
                    logger.error(error_msg)
                    await send_discord_message(error_msg)
                    last_error_notification = current_time
                    is_first_check = False
            await asyncio.sleep(CHECK_INTERVAL)

# ----------- SHUTDOWN HANDLING -----------
shutdown_event = asyncio.Event()

def shutdown_handler():
    print("\n🛑 Received shutdown signal. Stopping...")
    logger.info("Received shutdown signal.")
    shutdown_event.set()

def setup_signal_handlers():
    if sys.platform == "win32":
        signal.signal(signal.SIGINT, lambda s, f: shutdown_handler())
        signal.signal(signal.SIGTERM, lambda s, f: shutdown_handler())
    else:
        try:
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, shutdown_handler)
        except:
            signal.signal(signal.SIGINT, lambda s, f: shutdown_handler())
            signal.signal(signal.SIGTERM, lambda s, f: shutdown_handler())

# ----------- MAIN ENTRY POINT -----------
async def main():
    print("🚀 Starting Discord Results Bot...")
    print(f"⏱️ Check interval: {CHECK_INTERVAL} seconds")
    print("📁 Make sure 'registration_numbers.txt' exists")
    print("🔄 Press Ctrl+C to stop gracefully\n")
    setup_signal_handlers()
    try:
        await monitor_website(shutdown_event)
    except asyncio.CancelledError:
        pass
    finally:
        print("🛑 Shutting down...")
        await send_discord_message("🛑 **Result monitoring stopped**")
        print("✅ Shutdown complete!")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        logger.error(f"Fatal error: {e}")
