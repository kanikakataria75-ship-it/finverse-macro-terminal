import asyncio
import httpx
import logging
from datetime import datetime, timezone
import json
from bs4 import BeautifulSoup
import hashlib

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [SCRAPER] - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Configuration
# Instead of truthsocial.com which has aggressive Cloudflare blocking,
# we scrape trumpstruth.org which serves an unblocked mirror of Donald Trump's exact posts.
PROFILE_URL = "https://trumpstruth.org"
BACKEND_INGEST_URL = "http://localhost:8000/api/macro/ingest"
POLL_INTERVAL_SECONDS = 60

# In-memory deduplication set
processed_post_ids = set()

async def fetch_latest_posts_html():
    posts = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            logger.info(f"Fetching posts from {PROFILE_URL} ...")
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
            response = await client.get(PROFILE_URL, headers=headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find the post content divs
            elements = soup.find_all("div", class_="status")
            
            for el in elements[:5]:
                content_div = el.find("div", class_="status__content")
                if not content_div:
                    continue
                    
                text_content = content_div.get_text(separator=' ', strip=True)
                if not text_content or len(text_content) < 5:
                    continue
                
                # Extract time
                time_str = "Just now"
                meta_items = el.find_all("a", class_="status-info__meta-item")
                if len(meta_items) > 1:
                    time_str = meta_items[1].get_text(strip=True)
                
                # Create a pseudo-ID by hashing the content to deduplicate
                post_id = hashlib.md5(text_content.encode()).hexdigest()
                
                posts.append({
                    "post_id": post_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "published_at": time_str,
                    "raw_text": text_content
                })
            
            return posts
            
        except Exception as e:
            logger.error(f"Scraping Error: {e}")
            return []

async def process_and_forward(post: dict, force: bool = False):
    post_id = post["post_id"]
    if not force and post_id in processed_post_ids:
        return
        
    is_new = post_id not in processed_post_ids
    logger.info(f"{'Force pushing' if force else 'New real post detected!'} Hash ID: {post_id}")
    
    payload = {
        "post_id": post_id,
        "timestamp": post["timestamp"],
        "published_at": post.get("published_at", "Unknown"),
        "is_new": is_new,
        "raw_text": post["raw_text"],
        "source": "TRUTH_SOCIAL_TRUMP"
    }
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(BACKEND_INGEST_URL, json=payload)
            response.raise_for_status()
            logger.info(f"Backend Response:\n{json.dumps(response.json(), indent=2)}")
            processed_post_ids.add(post_id)
        except Exception as e:
            logger.error(f"Error forwarding to backend: {e}")

async def main():
    logger.info(f"Starting Truth Social Mirror Scraper...")
    latest_post = None
    
    while True:
        posts = await fetch_latest_posts_html()
        
        if posts:
            # The first post in the returned list is the absolute most recent
            latest_post = posts[0]
            
            # Process in reverse to send the oldest first if we just booted up
            for post in reversed(posts):
                await process_and_forward(post)
                
        # Persistently serve and maintain the absolute most recent post available
        # It must continuously push this last available post down the active stream connection
        if latest_post:
            await process_and_forward(latest_post, force=True)
        
        await asyncio.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    asyncio.run(main())
