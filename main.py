import asyncio
import io
import logging
import os
import time
import aiohttp
from dotenv import load_dotenv

load_dotenv()

# Configuration
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')
URL = 'https://results.beup.ac.in/BTech1stSem2024_B2024Results.aspx'
RESULT_URL_TEMPLATE = 'https://results.beup.ac.in/ResultsBTech1stSem2024_B2024Pub.aspx?Sem=I&RegNo={reg_no}'
REG_NO_FILE = 'registration_numbers.txt'

# Validate configuration
if not DISCORD_WEBHOOK_URL:
    raise ValueError("DISCORD_WEBHOOK_URL environment variable is required")

# Parameters
BATCH_SIZE = 20
CHECK_INTERVAL = 2
NOTIFICATION_INTERVAL = 7200

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ResultsMonitor:
    def __init__(self):
        self.session = None
        self.last_notification_time = 0
        self.is_first_check = True
        self.start_time = time.time()
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    def clean_registration_number(self, reg_no):
        cleaned = reg_no.strip()
        return cleaned if len(cleaned) == 11 and cleaned.isdigit() else ""

    async def fetch_result_html(self, reg_no):
        url = RESULT_URL_TEMPLATE.format(reg_no=reg_no)
        try:
            async with self.session.get(url, timeout=10) as response:
                if response.status == 200:
                    html = await response.text()
                    return None if "Invalid Registration Number" in html else html
        except Exception as e:
            logger.error(f"Error fetching {reg_no}: {e}")
        return None

    async def send_discord_message(self, content, filename=None, file_content=None):
        try:
            data = aiohttp.FormData()
            data.add_field('content', content[:2000])
            
            if filename and file_content:
                data.add_field('file', file_content, filename=filename)
            
            async with self.session.post(DISCORD_WEBHOOK_URL, data=data) as response:
                return response.status in [200, 204]
        except Exception as e:
            logger.error(f"Failed to send Discord message: {e}")
            return False

    async def send_health_check(self):
        """Send periodic health check to Discord"""
        uptime = time.time() - self.start_time
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)
        
        await self.send_discord_message(
            f"❤️ Health Check - Uptime: {hours}h {minutes}m\n"
            f"Last check: {time.strftime('%Y-%m-%d %H:%M:%S')}"
        )

    async def process_batch(self, batch):
        tasks = [self.fetch_result_html(reg_no) for reg_no in batch]
        results = await asyncio.gather(*tasks)
        
        successful = []
        for reg_no, html_content in zip(batch, results):
            if html_content:
                bio = io.BytesIO(html_content.encode('utf-8'))
                if await self.send_discord_message(
                    f"Result for {reg_no}", 
                    f"{reg_no}_result.html", 
                    bio
                ):
                    successful.append(reg_no)
                    
        return successful

    async def process_registration_file(self):
        if not os.path.exists(REG_NO_FILE):
            await self.send_discord_message(f"❌ File not found: {REG_NO_FILE}")
            return []

        try:
            with open(REG_NO_FILE, 'r') as f:
                reg_nos = [self.clean_registration_number(line) for line in f if line.strip()]
                reg_nos = [reg_no for reg_no in reg_nos if reg_no]
        except Exception as e:
            logger.error(f"File read error: {e}")
            await self.send_discord_message(f"⚠️ File error: {e}")
            return []

        if not reg_nos:
            await self.send_discord_message("❌ No valid registration numbers found")
            return []

        total = len(reg_nos)
        await self.send_discord_message(f"🚀 Processing {total} numbers...")

        all_successful = []
        for i in range(0, total, BATCH_SIZE):
            batch = reg_nos[i:i + BATCH_SIZE]
            successful = await self.process_batch(batch)
            all_successful.extend(successful)
            await asyncio.sleep(1)

        return all_successful

    async def monitor_website(self):
        health_check_interval = 3600  # 1 hour
        last_health_check = time.time()
        
        await self.send_discord_message("🔍 Monitoring started...")
        
        while True:
            current_time = time.time()
            
            # Health check
            if current_time - last_health_check >= health_check_interval:
                await self.send_health_check()
                last_health_check = current_time
            
            try:
                async with self.session.get(URL, timeout=10) as response:
                    if response.status == 200:
                        if self.is_first_check or current_time - self.last_notification_time >= NOTIFICATION_INTERVAL:
                            await self.send_discord_message("🌐 Website is LIVE! Processing results...")
                            successful = await self.process_registration_file()
                            
                            await self.send_discord_message(
                                f"✅ Processing complete! {len(successful)} results found."
                            )
                            
                            self.last_notification_time = current_time
                            self.is_first_check = False
                            
                            await asyncio.sleep(300)
                            continue
                    
            except Exception as e:
                if current_time - self.last_notification_time >= NOTIFICATION_INTERVAL:
                    await self.send_discord_message(f"❌ Website error: {type(e).__name__}")
                    self.last_notification_time = current_time

            await asyncio.sleep(CHECK_INTERVAL)


async def main():
    logger.info("Starting Results Monitor...")
    
    async with ResultsMonitor() as monitor:
        try:
            await monitor.send_discord_message("🚀 Results Monitor Started!")
            await monitor.monitor_website()
        except KeyboardInterrupt:
            await monitor.send_discord_message("⏹️ Bot stopped by user")
        except Exception as e:
            await monitor.send_discord_message(f"💥 Critical error: {str(e)}")
            raise


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application terminated")
    except Exception as e:
        logger.error(f"Application failed: {e}")
