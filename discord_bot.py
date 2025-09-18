# Updated discord_bot.py with 5s polling and hourly 'not live' notifications

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
CHECK_INTERVAL = 5  # Poll every 5 seconds
ERROR_NOTIFICATION_INTERVAL = 3600  # 1 hour for overload/errors
NOT_YET_NOTIFICATION_INTERVAL = 3600  # 1 hour for 'not yet live'

# Logging setup
logging.basicConfig(
    format='%(asctime)s %(levelname)s: %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ----------- DISCORD FUNCTIONS -----------
async def send_discord_message(message: str):
    try:
        payload = {"content": message, "username": "Result Monitor Bot"}
        async with aiohttp.ClientSession() as session:
            async with session.post(DISCORD_WEBHOOK, json=payload) as resp:
                if resp.status != 204:
                    logger.error(f"Discord error: {resp.status}")
        await asyncio.sleep(MESSAGE_DELAY)
    except Exception as e:
        logger.error(f"Discord send error: {e}")

async def send_discord_embed(title: str, description: str, color: int = 0x00ff00, fields: List[dict] = None):
    try:
        embed = {"title": title, "description": description, "color": color,
                 "timestamp": datetime.utcnow().isoformat()}
        if fields:
            embed["fields"] = fields
        payload = {"username": "Result Monitor Bot", "embeds": [embed]}
        async with aiohttp.ClientSession() as session:
            async with session.post(DISCORD_WEBHOOK, json=payload) as resp:
                if resp.status != 204:
                    logger.error(f"Discord error: {resp.status}")
        await asyncio.sleep(MESSAGE_DELAY)
    except Exception as e:
        logger.error(f"Discord embed error: {e}")

async def send_discord_file(reg_no: str, html_content: str):
    try:
        form = aiohttp.FormData()
        form.add_field('content', f'📄 **Result file for {reg_no}**')
        form.add_field('file', html_content,
                       filename=f'{reg_no}_result.html',
                       content_type='text/html')
        async with aiohttp.ClientSession() as session:
            async with session.post(DISCORD_WEBHOOK, data=form) as resp:
                if resp.status == 204:
                    return True
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
    return any(kw in html for kw in ["HTTP Error 503", "Service Unavailable", "Server Error"])

# ----------- FETCH & PROCESS ----------
async def fetch_result_html(session: aiohttp.ClientSession, reg_no: str) -> str:
    url = RESULT_URL_TEMPLATE.format(reg_no=reg_no)
    for attempt in range(RETRY_MAX_ATTEMPTS):
        try:
            async with session.get(url, timeout=10) as resp:
                html = await resp.text()
                if is_website_down_html(html):
                    await asyncio.sleep(2 ** attempt)
                    continue
                if "Invalid Registration Number" in html:
                    return None
                return html if is_result_html(html) else None
        except Exception:
            await asyncio.sleep(2 ** attempt)
    return None

async def process_batch(session: aiohttp.ClientSession, batch: List[str]):
    sem = asyncio.Semaphore(PARALLEL_REQUESTS)
    results = []
    async def single(r):
        clean = clean_registration_number(r)
        if not clean:
            await send_discord_message(f"❌ Invalid: {r}")
            return None, None
        async with sem:
            return r, await fetch_result_html(session, clean)
    for r, html in await asyncio.gather(*(single(x) for x in batch)):
        if html:
            await send_discord_embed("🎯 Result Found!", f"**{r}** result available.")
            await send_discord_file(r, html)
            results.append(r)
        else:
            await send_discord_message(f"❌ No result for {r}")
    return results

async def process_registration_file():
    if not os.path.exists(REG_NO_FILE):
        await send_discord_message(f"❌ Missing {REG_NO_FILE}")
        return
    with open(REG_NO_FILE) as f:
        nums = [l.strip() for l in f if l.strip() and not l.startswith('#')]
    total = len(nums)
    await send_discord_embed("🚀 Starting batches", f"{total} numbers")
    async with aiohttp.ClientSession() as session:
        for i in range(0, total, BATCH_SIZE):
            batch = nums[i:i+BATCH_SIZE]
            await send_discord_message(f"🔄 Batch {i//BATCH_SIZE+1}")
            await process_batch(session, batch)
            await asyncio.sleep(1)

# ----------- MONITOR LOOP -----------
async def monitor_website(shutdown: asyncio.Event):
    last_error = 0
    last_not_yet = 0
    await send_discord_embed("🔍 Monitoring Started", f"Every {CHECK_INTERVAL}s")
    async with aiohttp.ClientSession() as session:
        while not shutdown.is_set():
            now = time.time()
            try:
                async with session.get(URL, timeout=10) as resp:
                    html = await resp.text()
                    if resp.status == 200 and is_result_html(html):
                        await send_discord_embed("🌐 RESULTS LIVE!", "Processing...")
                        await process_registration_file()
                        break
                    if now - last_not_yet >= NOT_YET_NOTIFICATION_INTERVAL:
                        await send_discord_message("⏳ Results not yet published.")
                        last_not_yet = now
            except Exception as e:
                if now - last_error >= ERROR_NOTIFICATION_INTERVAL:
                    await send_discord_message(f"❌ Error checking site: {e}")
                    last_error = now
            await asyncio.sleep(CHECK_INTERVAL)

# ----------- SHUTDOWN HANDLING -----------
shutdown_evt = asyncio.Event()
def _shutdown(*_): shutdown_evt.set()
signal.signal(signal.SIGINT, _shutdown)
signal.signal(signal.SIGTERM, _shutdown)

# ----------- MAIN -----------
async def main():
    await monitor_website(shutdown_evt)
    await send_discord_message("🛑 Monitoring stopped")

if __name__ == '__main__':
    asyncio.run(main())
