"""Playwright scraper for Wine Enthusiast links and review details.

This module provides utilities to collect review links from search results
(optionally filtered by style and publication year) and to parse structured
fields from individual review pages. It persists a browser profile between runs,
uses small randomized pauses and scrolling, and supports checkpointing during
detail scraping.

Outputs:
  Links CSV columns: ["Wine Name", "URL"].
  Details CSV columns: ["Wine Name", "Region 1", "Region 2", "Region 3",
  "Country", "Score", "Price", "Winery", "Variety", "Wine Type", "URL"].
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from random import randint, random
from time import sleep
from typing import Iterable, Optional

import pandas as pd
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


@dataclass(slots=True)
class BrowserConfig:
    """Runtime configuration for the Playwright browser context.

    Attributes:
        headless: Whether to run the browser in headless mode.
        user_data_dir: Directory for a persistent browser profile.
        use_chrome_channel: Whether to run the real Chrome channel.
        storage_state_path: Deprecated when user_data_dir is set; kept for compatibility.
        user_agent: User-Agent header.
        locale: Preferred locale (for example, "en-US").
        timezone_id: IANA timezone ID.
        viewport_min: Minimum viewport width and height.
        viewport_max: Maximum viewport width and height.
        manual_challenge: If True, wait for manual captcha solve.
        challenge_timeout_s: Max seconds to wait for a challenge to clear.
        cooldown_range_s: Backoff window (min, max) when a challenge is detected.
    """

    headless: bool = False
    user_data_dir: str | None = ".we_profile"
    use_chrome_channel: bool = True

    storage_state_path: str | None = None  # optional legacy mode
    user_agent: str = _DEFAULT_UA
    locale: str = "en-US"
    timezone_id: str = "America/Los_Angeles"
    viewport_min: tuple[int, int] = (1200, 750)
    viewport_max: tuple[int, int] = (1600, 1000)

    manual_challenge: bool = True
    challenge_timeout_s: int = 180
    cooldown_range_s: tuple[int, int] = (12, 22)


_BASE = "https://www.wineenthusiast.com/"


def _build_search_url(page: int, style: str | None = None, year: int | None = None) -> str:
    """Compose a Wine Enthusiast search URL.

    Args:
        page: One-based page number.
        style: Optional wine style (for example, "Red", "White", "Sparkling",
            "Rose", "Dessert", "Port%252FSherry", "Fortified").
        year: Optional publication year.

    Returns:
        Fully qualified search URL string.
    """
    params: list[str] = ["?s=", "search_type=ratings", f"page={page}", "drink_type=wine"]
    if style:
        params.append(f"wine_style={style}")
    if year:
        # Wine Enthusiast encodes the colon for the year parameter as %253A{year}.
        params.append(f"pub_date=%253A{year}")
    return _BASE + ("&".join(params))


def _human_pause(a: float = 0.6, b: float = 1.4) -> None:
    """Sleep a small random interval between ``a`` and ``b`` seconds."""
    lo, hi = (a, b) if a <= b else (b, a)
    sleep(lo + random() * (hi - lo))


def _viewport(cfg: BrowserConfig) -> dict[str, int]:
    """Return a randomized viewport based on the provided configuration."""
    w = randint(cfg.viewport_min[0], cfg.viewport_max[0])
    h = randint(cfg.viewport_min[1], cfg.viewport_max[1])
    return {"width": w, "height": h}


def _incremental_scroll(page, steps: int = 3) -> None:
    """Scroll the page in several small steps to trigger lazy content."""
    for _ in range(steps):
        page.mouse.wheel(0, randint(400, 900))
        _human_pause(0.2, 0.6)


def _looks_like_challenge(page) -> bool:
    """Return True if the page shows a bot or captcha challenge."""
    body = (page.locator("body").first.text_content() or "").lower()
    if "unusual activity" in body or "verify you are a human" in body or "captcha" in body:
        return True
    if page.locator("iframe[src*='captcha'], iframe[src*='challenge']").count() > 0:
        return True
    return False


def _handle_challenge(page, cfg: BrowserConfig) -> None:
    """Handle a challenge by waiting, optional manual solve, then cooling down.

    Args:
        page: Playwright Page instance.
        cfg: Browser configuration (expects manual_challenge, challenge_timeout_s,
            and cooldown_range_s attributes).
    """
    if not _looks_like_challenge(page):
        return
    deadline = datetime.utcnow() + timedelta(seconds=cfg.challenge_timeout_s)

    if cfg.manual_challenge:
        print("Challenge detected. Solve it in the visible browser window.", file=sys.stderr)
        while datetime.utcnow() < deadline:
            _human_pause(1.0, 2.0)
            if not _looks_like_challenge(page):
                return

    wait_s = randint(*cfg.cooldown_range_s)
    print(f"Cooling down for {wait_s}s due to challenge...", file=sys.stderr)
    sleep(wait_s)


class WEPlaywrightScraper:
    """Scraper for Wine Enthusiast listings and review pages.

    This class exposes methods to collect review links from search listings and
    to parse structured fields from individual review pages.
    """

    def __init__(self, cfg: BrowserConfig | None = None) -> None:
        """Initialize the scraper with a browser configuration.

        Args:
            cfg: Browser configuration. If None, defaults are used.
        """
        self.cfg = cfg or BrowserConfig()

    def _new_context(self, p):
        """Create and return browser, context, and page for a session.

        In persistent-profile mode the browser handle is None; closing the
        context is sufficient to tear down the session.
        """
        viewport = _viewport(self.cfg)

        # Persistent profile (recommended).
        if self.cfg.user_data_dir:
            pdir = Path(self.cfg.user_data_dir)
            pdir.mkdir(parents=True, exist_ok=True)
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(pdir),
                headless=self.cfg.headless,
                channel=("chrome" if self.cfg.use_chrome_channel else None),
                user_agent=self.cfg.user_agent,
                locale=self.cfg.locale,
                timezone_id=self.cfg.timezone_id,
                viewport=viewport,
                extra_http_headers={"Accept-Language": self.cfg.locale},
            )
            page = context.new_page()
            return None, context, page  # browser is None in persistent mode

        # Ephemeral context (fallback).
        browser = p.chromium.launch(
            headless=self.cfg.headless,
            channel=("chrome" if self.cfg.use_chrome_channel else None),
        )
        storage_state_arg = None
        if self.cfg.storage_state_path and Path(self.cfg.storage_state_path).exists():
            storage_state_arg = str(self.cfg.storage_state_path)
        context = browser.new_context(
            user_agent=self.cfg.user_agent,
            locale=self.cfg.locale,
            timezone_id=self.cfg.timezone_id,
            viewport=viewport,
            storage_state=storage_state_arg,
            extra_http_headers={"Accept-Language": self.cfg.locale},
        )
        page = context.new_page()
        return browser, context, page

    def _save_state(self, context) -> None:
        """Persist storage state if a path is configured."""
        if self.cfg.storage_state_path:
            context.storage_state(path=self.cfg.storage_state_path)

    def collect_links(
        self,
        *,
        max_pages: int = 48,
        styles: Optional[Iterable[str]] = None,
        years: Optional[Iterable[int]] = None,
        out_csv: str | None = None,
    ) -> pd.DataFrame:
        """Collect review links from search listings.

        Args:
            max_pages: Maximum pages to visit per (style, year) combination.
            styles: Optional iterable of style names.
            years: Optional iterable of publication years.
            out_csv: Optional path to write a deduplicated links CSV.

        Returns:
            DataFrame with columns ["Wine Name", "URL"].
        """
        rows: list[dict] = []
        styles_iter = list(styles) if styles else [None]
        years_iter = list(years) if years else [None]

        with sync_playwright() as p:
            browser, context, page = self._new_context(p)
            try:
                for sty in styles_iter:
                    for yr in years_iter:
                        for pg in range(1, max_pages + 1):
                            url = _build_search_url(pg, sty, yr)
                            page.goto(url, wait_until="domcontentloaded")
                            _handle_challenge(page, self.cfg)
                            _human_pause(0.4, 0.9)
                            _incremental_scroll(page, steps=3)
                            try:
                                page.wait_for_selector(
                                    ".ratings-block__info h3.info__title a", timeout=10000
                                )
                            except PlaywrightTimeoutError:
                                continue
                            anchors = page.locator(
                                ".ratings-block__info h3.info__title a"
                            ).all()
                            for a in anchors:
                                name = (a.text_content() or "").strip()
                                href = a.get_attribute("href")
                                if name and href:
                                    rows.append({"Wine Name": name, "URL": href})
                            _human_pause(0.6, 1.4)
                self._save_state(context)
            finally:
                context.close()
                if browser:
                    browser.close()

        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.drop_duplicates(subset=["URL"]).reset_index(drop=True)
        if out_csv:
            Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(out_csv, index=False)
        return df

    def fetch_detail(self, url: str) -> dict:
        """Scrape a single review page into structured fields.

        Args:
            url: Review URL.

        Returns:
            Mapping compatible with the details CSV schema.

        Raises:
            playwright.sync_api.TimeoutError: If required selectors do not appear.
        """
        with sync_playwright() as p:
            browser, context, page = self._new_context(p)
            try:
                page.goto(url, wait_until="domcontentloaded")
                _handle_challenge(page, self.cfg)
                page.wait_for_selector(".review-title", timeout=15000)
                title = (page.locator(".review-title").first.text_content() or "").strip() or None

                region_elems = page.locator(
                    'xpath=//*[@id="single-page"]/header/div/div/div/div/div[2]/span[2]/a'
                ).all()
                region_list = [(e.text_content() or "").strip() for e in region_elems]
                region_list = [x for x in region_list if x]
                region_value = (
                    page.locator("div.region .value a").first.text_content() or ""
                ).strip() or None

                country = region_list[-1] if region_list else None
                region_1 = region_value if region_value and region_value in region_list else None
                region_2 = (
                    region_list[-2]
                    if len(region_list) > 1 and region_list[-2] != region_value
                    else None
                )
                region_3 = (
                    region_list[-3]
                    if len(region_list) > 2 and region_list[-3] != region_value
                    else None
                )

                def _strip_label(text: str | None, label: str) -> str | None:
                    if not text:
                        return None
                    if text.startswith(label):
                        return text.replace(label + "", "", 1).strip()
                    return text.strip()

                score = _strip_label(
                    (page.locator(".score").first.text_content() or "").strip() or None,
                    "RATING",
                )
                price = _strip_label(
                    (page.locator(".price").first.text_content() or "").strip() or None,
                    "PRICE",
                )

                winery = (
                    page.locator("div.winery .value a").first.text_content() or ""
                ).strip() or None
                variety = (
                    page.locator("div.variety .value a").first.text_content() or ""
                ).strip() or None
                wine_type = (
                    page.locator("div.wine-type .value a").first.text_content() or ""
                ).strip() or None

                return {
                    "Wine Name": title,
                    "Region 1": region_1,
                    "Region 2": region_2,
                    "Region 3": region_3,
                    "Country": country,
                    "Score": score,
                    "Price": price,
                    "Winery": winery,
                    "Variety": variety,
                    "Wine Type": wine_type,
                    "URL": url,
                }
            finally:
                self._save_state(context)
                context.close()
                if browser:
                    browser.close()

    def scrape_details_from_csv(
        self,
        links_csv: str,
        *,
        out_csv: str | None = None,
        checkpoint_every: int = 100,
    ) -> pd.DataFrame:
        """Scrape review details for each URL listed in a CSV.

        Args:
            links_csv: Path to a CSV containing columns ["Wine Name", "URL"].
            out_csv: Optional path to write accumulated results periodically.
            checkpoint_every: Number of rows between periodic writes.

        Returns:
            DataFrame with the detail schema.
        """
        df_links = pd.read_csv(links_csv)
        rows: list[dict] = []
        for i, r in df_links.iterrows():
            url = str(r["URL"]) if "URL" in df_links.columns else str(r.get("url", ""))
            if not url:
                continue
            try:
                rec = self.fetch_detail(url)
                rows.append(rec)
            except Exception as exc:  # Keep scraping across failures.
                rows.append({"URL": url, "error": str(exc)})
            if out_csv and (i + 1) % checkpoint_every == 0:
                out_df = pd.DataFrame(rows)
                Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
                out_df.to_csv(out_csv, index=False)
        result = pd.DataFrame(rows)
        if out_csv:
            Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
            result.to_csv(out_csv, index=False)
        return result
