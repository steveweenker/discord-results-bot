import asyncio
import io
import logging
import os
import time
import aiohttp
import json
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

# Configuration - Get from environment variables
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')
URL = 'https://results.beup.ac.in/BTech1stSem2024_B2024Results.aspx'
RESULT_URL_TEMPLATE = 'https://results.beup.ac.in/ResultsBTech1stSem2024_B2024Pub.aspx?Sem=I&RegNo={reg_no}'
REG_NO_FILE = 'registration_numbers.txt'

# Validate required environment variables
if not DISCORD_WEBHOOK_URL:
    raise ValueError("DISCORD_WEBHOOK_URL environment variable is required")

# Optimization Parameters
BATCH_SIZE = 20
PARALLEL_REQUESTS = 10
MESSAGE_DELAY = 1
RETRY_MAX_ATTEMPTS = 3

# Monitoring Parameters
CHECK_INTERVAL = 1  # Check every 2 seconds
NOTIFICATION_INTERVAL = 7200  # Notify every 2 hours (7200 seconds)

# Logging Setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def clean_registration_number(reg_no):
    """Ultra-fast validation"""
    return reg_no.strip() if len(reg_no.strip()) == 11 and reg_no.strip().isdigit() else ""


async def fetch_result_html(session, reg_no):
    """Async fetch with connection reuse"""
    url = RESULT_URL_TEMPLATE.format(reg_no=reg_no)
    for attempt in range(RETRY_MAX_ATTEMPTS):
        try:
            async with session.get(url, timeout=10) as response:
                html = await response.text()
                return None if "Invalid Registration Number" in html else html
        except Exception as e:
            logger.error(f"Fetch error for {reg_no} (attempt {attempt + 1}): {e}")
            if attempt == RETRY_MAX_ATTEMPTS - 1:
                return None
            await asyncio.sleep(2 ** attempt)  # exponential backoff


async def send_discord_message(content, filename=None, file_content=None):
    """Send message to Discord webhook"""
    try:
        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            data.add_field('content', content)
            
            if filename and file_content:
                data.add_field('file', file_content, filename=filename)
            
            async with session.post(DISCORD_WEBHOOK_URL, data=data) as response:
                if response.status == 204:
                    logger.info("Message sent successfully")
                else:
                    logger.error(f"Failed to send message: {response.status}")
                await asyncio.sleep(MESSAGE_DELAY)
    except Exception as e:
        logger.error(f"Discord message failed: {e}")


async def send_html_file(reg_no, html_content):
    """Send HTML file to Discord"""
    try:
        bio = io.BytesIO(html_content.encode('utf-8'))
        bio.seek(0)
        
        await send_discord_message(
            content=f"Result for {reg_no}",
            filename=f"{reg_no}_result.html",
            file_content=bio
        )
        return True
    except Exception as e:
        logger.error(f"File send failed for {reg_no}: {e}")
        return False


async def process_batch(session, batch):
    """Parallel batch processor"""
    tasks = []
    for reg_no in batch:
        clean_reg = clean_registration_number(reg_no)
        if not clean_reg:
            await send_discord_message(f"Invalid format: {reg_no}")
            continue
        tasks.append(fetch_result_html(session, clean_reg))

    results = await asyncio.gather(*tasks)

    successful = []
    for reg_no, html_content in zip(batch, results):
        if html_content and await send_html_file(reg_no, html_content):
            successful.append(reg_no)

    return successful


async def process_registration_file():
    """Optimized file processor"""
    if not os.path.exists(REG_NO_FILE):
        await send_discord_message(f"❌ File not found: {REG_NO_FILE}")
        return

    try:
        with open(REG_NO_FILE, 'r') as f:
            reg_nos = [line.strip() for line in f if line.strip()]
    except Exception as e:
        logger.error(f"File read error: {e}")
        await send_discord_message(f"⚠️ File error: {e}")
        return

    if not reg_nos:
        await send_discord_message("❌ No registration numbers found")
        return

    total = len(reg_nos)
    await send_discord_message(f"🚀 Processing {total} numbers (batches of {BATCH_SIZE})...")

    async with aiohttp.ClientSession() as session:
        all_successful = []
        for i in range(0, total, BATCH_SIZE):
            batch = reg_nos[i:i + BATCH_SIZE]
            successful = await process_batch(session, batch)
            all_successful.extend(successful)
            await asyncio.sleep(1)  # Brief pause between batches

        await send_discord_message(
            f"📊 Final: {len(all_successful)}/{total} successful\n"
            f"Failed: {total - len(all_successful)}"
        )


async def monitor_website():
    """Monitor website for availability"""
    last_notification_time = 0
    is_first_check = True

    await send_discord_message("🔍 Monitoring started (checks every 2 seconds)...")

    async with aiohttp.ClientSession() as session:
        while True:
            current_time = time.time()
            try:
                async with session.get(URL, timeout=10) as response:
                    if response.status == 200:
                        if is_first_check or current_time - last_notification_time >= NOTIFICATION_INTERVAL:
                            await send_discord_message("🌐 Website LIVE! Processing...")
                            await process_registration_file()
                            break
                    else:
                        if current_time - last_notification_time >= NOTIFICATION_INTERVAL:
                            await send_discord_message(
                                f"⚠️ Website returned status {response.status}"
                            )
                            last_notification_time = current_time
                            is_first_check = False
            except Exception as e:
                if current_time - last_notification_time >= NOTIFICATION_INTERVAL:
                    await send_discord_message(
                        f"❌ Website DOWN - {type(e).__name__}: {str(e)}"
                    )
                    last_notification_time = current_time
                    is_first_check = False

            await asyncio.sleep(CHECK_INTERVAL)


async def main():
    """Main function"""
    await send_discord_message("🚀 Results Monitor Started!")
    
    # Start monitoring
    await monitor_website()


if __name__ == '__main__':
    asyncio.run(main())
