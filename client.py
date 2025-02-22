import asyncio
import json
import logging
import os
from typing import Optional

import aiohttp
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BrowserClient:
    def __init__(self, api_url: str = "http://localhost:8000"):
        self.api_url = api_url
        self.session_id: Optional[str] = None
        self.cdp_url: Optional[str] = None

    async def create_session(self, user_id: str = "demo-user") -> bool:
        """Create a new browser session through the management API"""
        try:
            async with aiohttp.ClientSession() as session:
                response = await session.post(
                    f"{self.api_url}/sessions", json={"user_id": user_id}
                )

                if response.status != 201:
                    logger.error(f"Failed to create session: {await response.text()}")
                    return False

                data = await response.json()
                self.session_id = data["session_id"]
                self.cdp_url = data["cdp_url"]
                logger.info(
                    f"Created session {self.session_id} with CDP: {self.cdp_url}"
                )
                return True

        except Exception as e:
            logger.error(f"Session creation failed: {e}")
            return False

    async def run_automation(self):
        """Perform browser automation using Playwright"""
        if not self.cdp_url or not self.session_id:
            logger.error("No active session")
            return False

        try:
            async with async_playwright() as p:
                logger.info("Connecting to browser via CDP...")
                browser = await p.chromium.connect_over_cdp(self.cdp_url)
                context = browser.contexts[0]
                page = context.pages[0] if context.pages else await context.new_page()

                actions = [
                    ("goto", "https://example.com"),
                    ("type", "input", "test search query"),
                    ("click", "button"),
                    ("goto", "https://httpbin.org/get"),
                    ("evaluate", "() => { console.log('Hello from browser!'); }"),
                ]

                for action in actions:
                    try:
                        await self._perform_action(page, action)
                        await asyncio.sleep(1)
                    except Exception as e:
                        logger.warning(f"Action failed: {action[0]} - {e}")
                        continue

                await browser.close()
                return True

        except Exception as e:
            logger.error(f"Automation error: {e}")
            return False

    async def _perform_action(self, page, action):
        """Execute individual browser actions"""
        action_type, *args = action
        logger.info(f"Performing {action_type.upper()} {args}")

        if action_type == "goto":
            await page.goto(args[0], timeout=15000)
        elif action_type == "type":
            await page.fill(args[0], args[1])
        elif action_type == "click":
            await page.click(args[0], timeout=5000)
        elif action_type == "evaluate":
            await page.evaluate(args[0])
        else:
            logger.warning(f"Unknown action type: {action_type}")

    async def get_session_logs(self, limit: int = 20):
        """Retrieve session logs from the management API"""
        if not self.session_id:
            return None

        try:
            async with aiohttp.ClientSession() as session:
                response = await session.get(
                    f"{self.api_url}/sessions/{self.session_id}/logs?limit={limit}"
                )
                return await response.json() if response.status == 200 else None
        except Exception as e:
            logger.error(f"Failed to get logs: {e}")
            return None

    async def cleanup(self):
        """Terminate the browser session"""
        if not self.session_id:
            return

        try:
            async with aiohttp.ClientSession() as session:
                await session.delete(f"{self.api_url}/sessions/{self.session_id}")
                logger.info(f"Session {self.session_id} terminated")
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")


async def main():
    api_url = os.getenv("MANAGEMENT_API_URL", "http://localhost:8000")
    client = BrowserClient(api_url)

    try:
        if not await client.create_session():
            return

        if not await client.run_automation():
            return

        logs = await client.get_session_logs()
        if logs:
            print("\nSession Logs:")
            for idx, event in enumerate(logs.get("events", [])[:10]):
                print(f"{idx+1}. {json.dumps(event, indent=2)[:200]}...")

    finally:
        await client.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
