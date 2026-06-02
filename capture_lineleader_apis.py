#!/usr/bin/env python3
"""
Capture LineLeader/ChildCareCRM API calls using Playwright.

Usage:
    python3 capture_lineleader_apis.py

Navigate the browser, then Ctrl+C to stop and save.
"""

import json
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

captured = []

def attach_response_handler(page):
    """Attach response listener to a page."""
    async def on_response(response):
        try:
            url = response.url
            if "childcarecrm.com/api" not in url:
                return
            method = response.request.method
            status = response.status
            try:
                body = await response.text()
                body_preview = body[:500]
            except:
                body_preview = ""

            endpoint = url.split("/api/v3/")[-1].split("?")[0] if "/api/v3/" in url else url
            params = url.split("?")[1][:80] if "?" in url else ""

            captured.append({
                "method": method,
                "endpoint": endpoint,
                "params": params,
                "url": url,
                "status": status,
                "body_preview": body_preview,
            })
            print(f"[{status}] {method:6} {endpoint:45} {params[:50]}")
        except Exception as e:
            pass

    page.on("response", on_response)


def save_results():
    if not captured:
        print("\n❌ Nothing captured.")
        return

    Path("logs").mkdir(exist_ok=True)
    with open("logs/lineleader_apis_captured.json", "w") as f:
        json.dump(captured, f, indent=2)

    print(f"\n{'='*70}")
    print(f"CAPTURED {len(captured)} API CALLS")
    print(f"{'='*70}")

    seen = {}
    for c in captured:
        ep = c["endpoint"]
        seen[ep] = seen.get(ep, 0) + 1
    for ep, count in seen.items():
        print(f"  {count:3}x  {ep}")

    print(f"\n✅ Saved to logs/lineleader_apis_captured.json")


async def capture_apis():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()

        # Attach handler to every new page (handles OAuth redirects)
        context.on("page", lambda page: attach_response_handler(page))

        page = await context.new_page()
        attach_response_handler(page)

        print("\n" + "="*70)
        print("LINELEADER API CAPTURE")
        print("="*70)
        print("\nBrowser opening...")
        print("Navigate to the calendar, find Mina's tour, click around.")
        print("Press Ctrl+C in terminal when done to save.\n")

        await page.goto("https://my.childcarecrm.com", wait_until="domcontentloaded")

        # Keep alive until Ctrl+C
        while True:
            await asyncio.sleep(1)


if __name__ == "__main__":
    try:
        asyncio.run(capture_apis())
    except KeyboardInterrupt:
        pass
    finally:
        save_results()
