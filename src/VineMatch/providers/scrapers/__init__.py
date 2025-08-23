"""Scrapers for external wine data sources.

Exposes a stable public API for scraper implementations.
"""
from __future__ import annotations

from .we_playwright import BrowserConfig, WEPlaywrightScraper

__all__ = [
    "BrowserConfig",
    "WEPlaywrightScraper",
]
