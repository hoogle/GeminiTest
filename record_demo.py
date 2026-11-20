import asyncio
import os
import subprocess
from pathlib import Path
from playwright.async_api import async_playwright

FRONTEND_URL = "https://local-travel-concierge-frontend-418081633286.us-east1.run.app"
OUTPUT_DIR = Path("/config/.gemini/antigravity/brain/91139e74-a282-4131-af60-8851212c72a4")
VIDEO_TMP = Path("/tmp/demo_raw_video")
VIDEO_TMP.mkdir(parents=True, exist_ok=True)

PROMPT_1 = "我想規劃一趟慢活的京都一日遊，請從景點庫推薦特色景點與漫步路線。"
PROMPT_2 = "太棒了！請幫我生成一張嵐山竹林清晨陽光灑落的專屬明信片意象，並查詢京都當前的即時氣溫與穿著建議。"

async def type_slowly(locator, text, delay=0.04):
    for char in text:
        await locator.press_sequentially(char, delay=delay * 1000)

async def run_demo():
    print("Starting Playwright browser...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--font-render-hinting=medium",
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            record_video_dir=str(VIDEO_TMP),
            record_video_size={"width": 1280, "height": 720},
        )
        page = await context.new_page()

        print(f"Navigating to {FRONTEND_URL}...")
        await page.goto(FRONTEND_URL, wait_until="networkidle")
        await asyncio.sleep(2)

        # Prompt 1: Core capability (Travel itinerary + Firestore catalog + A2UI card)
        print("Typing Prompt 1...")
        input_box = page.locator("#input")
        await input_box.click()
        await type_slowly(input_box, PROMPT_1, delay=0.03)
        await asyncio.sleep(1)
        await page.locator("button:has-text('Send')").click()
        print("Waiting for Agent response to Prompt 1...")

        # Wait until the placeholder "…" disappears and content renders
        await page.wait_for_function(
            "() => { const bubbles = document.querySelectorAll('.msg.agent .bubble'); return bubbles.length >= 1 && bubbles[0].textContent !== '…'; }",
            timeout=120000
        )
        await asyncio.sleep(4)  # Give time to view the rendered card

        # Prompt 2: Richer prompt with Tool Call (get_weather) & Generated Image (generate_attraction_image)
        print("Typing Prompt 2...")
        await input_box.click()
        await type_slowly(input_box, PROMPT_2, delay=0.03)
        await asyncio.sleep(1)
        await page.locator("button:has-text('Send')").click()
        print("Waiting for Agent response to Prompt 2 (including Image Gen & Weather)...")

        await page.wait_for_function(
            "() => { const bubbles = document.querySelectorAll('.msg.agent .bubble'); return bubbles.length >= 2 && bubbles[1].textContent !== '…'; }",
            timeout=180000
        )
        await asyncio.sleep(6)  # Pause to display the generated card & image

        # Scroll smoothly to show full conversation
        await page.evaluate("() => { const log = document.getElementById('log'); log.scrollTo({top: log.scrollHeight, behavior: 'smooth'}); }")
        await asyncio.sleep(3)

        video_path = await page.video.path()
        await page.close()
        await context.close()
        await browser.close()
        print(f"Raw video recorded at: {video_path}")

        # Convert webm to polished mp4 in artifact directory
        target_mp4 = OUTPUT_DIR / "local_travel_concierge_demo.mp4"
        print(f"Converting video with ffmpeg to {target_mp4}...")
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "medium",
            "-crf", "22",
            str(target_mp4)
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0:
            print(f"Demo video successfully created at: {target_mp4}")
        else:
            print(f"FFmpeg error: {res.stderr}")

if __name__ == "__main__":
    asyncio.run(run_demo())
