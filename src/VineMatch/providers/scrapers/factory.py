"""Factories for scraper instances.

Provides convenience constructors for scraper implementations.
"""
from __future__ import annotations

from .we_playwright import BrowserConfig, WEPlaywrightScraper


def get_wine_enthusiast_scraper(
    *,
    headless: bool = False,
    storage_state_path: str | None = ".we_storage_state.json",
    user_agent: str | None = None,
    locale: str = "en-US",
    timezone_id: str = "America/Los_Angeles",
) -> WEPlaywrightScraper:
    """Return a configured scraper instance for Wine Enthusiast.

    Args:
        headless: Whether to run the browser in headless mode.
        storage_state_path: Path to a JSON file to persist cookies and localStorage.
            If None, storage state is not persisted.
        user_agent: Optional user-agent string. If None, the default is used.
        locale: Locale for the browser context.
        timezone_id: IANA timezone for the browser context.

    Returns:
        Configured ``WEPlaywrightScraper`` instance.
    """
    base = BrowserConfig()
    cfg = BrowserConfig(
        headless=headless,
        storage_state_path=storage_state_path,
        user_agent=user_agent or base.user_agent,
        locale=locale,
        timezone_id=timezone_id,
    )
    return WEPlaywrightScraper(cfg)
