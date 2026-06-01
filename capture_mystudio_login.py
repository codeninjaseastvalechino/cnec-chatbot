#!/usr/bin/env python3
"""
MyStudio login via Playwright + capture all API calls to logs.

Usage:
    python3 capture_mystudio_login.py

This will:
  1. Log in to MyStudio (headless browser)
  2. Navigate to schedule view
  3. Capture ALL API calls to logs/mystudio_apis.log
  4. Print each API call with status code

Then paste the logs here and we can analyze which ones work.
"""

import json
import asyncio
from datetime import date
from playwright.async_api import async_playwright, Response

from config.settings import settings
from core.logger import get_logger

logger = get_logger(__name__)

BASE_URL = "https://cn.mystudio.io/v43/Api/PortalApi"
PORTAL_URL = "https://cn.mystudio.io/v43/WebPortal/"


async def capture_mystudio_apis():
    """Log in and capture all API calls."""

    captured_apis = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        # Intercept ALL responses
        async def on_response(response: Response):
            url = response.url
            method = response.request.method
            status = response.status

            # Capture ALL API calls
            try:
                if "/Api/" in url or "/api/" in url.lower():
                    body_preview = ""
                    try:
                        body = await response.text()
                        body_preview = body[:500] if body else ""
                    except:
                        pass

                    api_record = {
                        "method": method,
                        "url": url,
                        "status": status,
                        "body_preview": body_preview,
                    }
                    captured_apis.append(api_record)

                    endpoint = url.split('/')[-1]
                    print(f"[{status:3}] {method:6} {endpoint:50}")
                    logger.info(f"API: {method} {endpoint} → {status}")
            except Exception as e:
                logger.error(f"Error capturing response: {e}")

        page.on("response", on_response)

        print("\n" + "="*70)
        print("MYSTUDIO LOGIN + API CAPTURE (via Playwright)")
        print("="*70)
        print("\nBrowser is opening — please log in manually:")
        print("  1. Navigate to the login form")
        print("  2. Enter credentials")
        print("  3. Complete 2FA")
        print("  4. Go to the calendar/schedule view")
        print("  5. Close the browser when done")
        print("\nAll API calls are being captured...")
        print("="*70 + "\n")

        # Navigate to portal
        await page.goto(PORTAL_URL, wait_until="domcontentloaded")

        # Wait for user to manually complete login
        print("⏳ Waiting for browser to close...")

        # Keep browser open — user navigates manually while we capture
        # When user closes browser, we continue
        while not page.is_closed():
            await asyncio.sleep(1)
            try:
                # Check if page is still active
                _ = await page.title()
            except:
                break

        print("✅ Capture complete")

    # Print summary
    print("\n" + "="*70)
    print("CAPTURED API CALLS")
    print("="*70 + "\n")

    api_calls_by_status = {}
    for api in captured_apis:
        status = api["status"]
        if status not in api_calls_by_status:
            api_calls_by_status[status] = []
        api_calls_by_status[status].append(api)

    for status in sorted(api_calls_by_status.keys()):
        apis = api_calls_by_status[status]
        print(f"\n{status} ({len(apis)} calls):")
        for api in apis:
            endpoint = api["url"].split('/')[-1]
            print(f"  {api['method']:6} {endpoint:50}")

    # Save to JSON for inspection
    with open("logs/mystudio_apis_captured.json", "w") as f:
        json.dump(captured_apis, f, indent=2)

    print(f"\n✅ Saved {len(captured_apis)} API calls to logs/mystudio_apis_captured.json")


if __name__ == "__main__":
    asyncio.run(capture_mystudio_apis())
