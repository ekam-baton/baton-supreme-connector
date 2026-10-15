import asyncio
from typing import Optional
import httpx

# Browser automation using Playwright for full JS-rendered page interaction
# Falls back gracefully if playwright is not installed

_playwright_available = False
try:
    from playwright.async_api import async_playwright
    _playwright_available = True
except ImportError:
    pass


async def take_screenshot(url: str, output_path: str = "/tmp/screenshot.png") -> dict:
    """Navigate to a URL and take a screenshot of the rendered page."""
    if not _playwright_available:
        return {"error": "Playwright is not installed. Run: pip install playwright && playwright install chromium"}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.screenshot(path=output_path, full_page=True)
            return {"status": "success", "screenshot_path": output_path}
        except Exception as e:
            return {"error": f"Screenshot failed: {str(e)}"}
        finally:
            await browser.close()


async def get_rendered_text(url: str) -> dict:
    """Navigate to a URL and extract the fully rendered text content (including JS-rendered content)."""
    if not _playwright_available:
        return {"error": "Playwright is not installed. Run: pip install playwright && playwright install chromium"}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            # Get the fully rendered text content
            text = await page.inner_text("body")
            # Truncate to prevent massive token usage
            return {"status": "success", "text": text[:8000], "url": url}
        except Exception as e:
            return {"error": f"Page render failed: {str(e)}"}
        finally:
            await browser.close()


async def click_element(url: str, selector: str) -> dict:
    """Navigate to a URL and click an element matching the CSS selector."""
    if not _playwright_available:
        return {"error": "Playwright is not installed."}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.click(selector, timeout=5000)
            await page.wait_for_load_state("networkidle")
            text = await page.inner_text("body")
            return {"status": "success", "text_after_click": text[:5000]}
        except Exception as e:
            return {"error": f"Click failed: {str(e)}"}
        finally:
            await browser.close()


async def fill_form(url: str, selector: str, value: str) -> dict:
    """Navigate to a URL and fill an input field matching the CSS selector."""
    if not _playwright_available:
        return {"error": "Playwright is not installed."}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.fill(selector, value, timeout=5000)
            return {"status": "success", "filled": True, "selector": selector}
        except Exception as e:
            return {"error": f"Fill failed: {str(e)}"}
        finally:
            await browser.close()
