#!/usr/bin/env python3
"""
Playwright script to capture ALL network requests/responses during MyStudio login.

Run this script, complete the login + 2FA manually in the browser window,
then paste the output here so we can identify the correct API endpoints and cookies.

Usage:
    python3 capture_mystudio_login.py
"""

import asyncio
import json
from datetime import datetime
from playwright.async_api import async_playwright

LOGIN_URL = "https://cn.mystudio.io/v43/WebPortal/"
LOG_FILE = "logs/mystudio_network_capture.json"

captured_calls = []


async def main():
    print("=" * 70)
    print("MyStudio Network Capture")
    print("=" * 70)
    print("A browser window will open. Complete the login + 2FA manually.")
    print("All API calls will be logged automatically.")
    print(f"Output saved to: {LOG_FILE}")
    print("=" * 70)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        # Capture every request — log full body for getClassdatatabledetails
        async def on_request(request):
            if "PortalApi" in request.url:
                entry = {
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "direction": "REQUEST",
                    "method": request.method,
                    "url": request.url,
                    "headers": dict(request.headers),
                }
                try:
                    body = request.post_data
                    if body:
                        # Full body for datatable, truncated for others
                        if "getClassdatatabledetails" in request.url:
                            entry["body"] = body  # NO truncation
                        else:
                            entry["body"] = body[:500]
                except:
                    pass
                captured_calls.append(entry)
                print(f"  → {request.method} {request.url.split('mystudio.io')[-1]}")

        # Capture every response — log full body for PortalApi calls
        async def on_response(response):
            if "PortalApi" in response.url:
                entry = {
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "direction": "RESPONSE",
                    "status": response.status,
                    "url": response.url,
                }
                try:
                    body = await response.text()
                    entry["body"] = body[:2000]
                except:
                    pass
                captured_calls.append(entry)
                print(f"  ← {response.status} {response.url.split('mystudio.io')[-1]}")

        page.on("request", on_request)
        page.on("response", on_response)

        print(f"\nOpening: {LOGIN_URL}")
        await page.goto(LOGIN_URL)

        print("\n>>> Complete login + 2FA in the browser window.")
        print(">>> Press ENTER here once you're on the dashboard.\n")
        await asyncio.get_event_loop().run_in_executor(None, input)

        # Save all captured calls
        import os
        os.makedirs("logs", exist_ok=True)
        with open(LOG_FILE, "w") as f:
            json.dump(captured_calls, f, indent=2)

        print(f"\n✅ Captured {len(captured_calls)} network calls → {LOG_FILE}")
        print("\n--- PortalApi calls (requests + responses) ---")
        for entry in captured_calls:
            if entry["direction"] == "REQUEST":
                print(f"\n→ {entry['method']} {entry['url'].split('mystudio.io')[-1]}")
                if entry.get("headers"):
                    for k, v in entry["headers"].items():
                        if k.lower() in ("authorization", "content-type", "x-requested-with", "cookie"):
                            print(f"    {k}: {v[:120]}")
                if entry.get("body"):
                    print(f"    Body: {entry['body'][:300]}")
            else:
                print(f"← {entry['status']} {entry['url'].split('mystudio.io')[-1]}")
                if entry.get("body"):
                    print(f"    {entry['body'][:200]}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
