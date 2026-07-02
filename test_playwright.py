import asyncio
from playwright.async_api import async_playwright

async def debug_truth_social():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        # use domcontentloaded and a short sleep
        await page.goto("https://truthsocial.com/@realDonaldTrump", wait_until="domcontentloaded", timeout=60000)
        
        await asyncio.sleep(10) # give it time to render js
        
        # Save HTML
        html = await page.content()
        with open("truth_social_debug.html", "w", encoding="utf-8") as f:
            f.write(html)
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_truth_social())
