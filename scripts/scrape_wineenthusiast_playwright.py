"""Command-line entry points for the Wine Enthusiast Playwright scraper.

This script exposes two subcommands:
  links   Collect review links and write them to CSV.
  details Scrape review details for a CSV of links.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from vinematch.providers.scrapers.we_playwright import BrowserConfig, WEPlaywrightScraper


def _ts_folder(prefix: str) -> str:
    """Return a dated output path under the raw scraped data folder."""
    ts = datetime.utcnow().strftime("%Y%m%d")
    return f"data/raw/scraped/wineenthusiast/{ts}/{prefix}"


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the scraper CLI.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Playwright scraper for Wine Enthusiast (links and details)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_links = sub.add_parser("links", help="Collect review links")
    p_links.add_argument("--max-pages", type=int, default=48)
    p_links.add_argument("--styles", nargs="*", default=None, help="Style names")
    p_links.add_argument("--years", nargs="*", type=int, default=None, help="Publication years")
    p_links.add_argument("--headless", action="store_true")
    p_links.add_argument("--out", default=None, help="Output CSV path")

    p_det = sub.add_parser("details", help="Scrape details for a links CSV")
    p_det.add_argument("--links-csv", required=True)
    p_det.add_argument("--headless", action="store_true")
    p_det.add_argument("--out", default=None, help="Output CSV path")
    p_det.add_argument("--checkpoint-every", type=int, default=100)

    return parser.parse_args()


def main() -> None:
    """Execute the requested scraper subcommand."""
    args = parse_args()
    cfg = BrowserConfig(headless=bool(args.headless))
    scraper = WEPlaywrightScraper(cfg)

    if args.cmd == "links":
        out = args.out or _ts_folder("wine_links.csv")
        df = scraper.collect_links(
            max_pages=int(args.max_pages),
            styles=args.styles,
            years=args.years,
            out_csv=out,
        )
        print(f"Collected {len(df)} links → {out}")
    elif args.cmd == "details":
        out = args.out or _ts_folder("wine_info.csv")
        df = scraper.scrape_details_from_csv(
            links_csv=args.links_csv,
            out_csv=out,
            checkpoint_every=int(args.checkpoint_every),
        )
        print(f"Scraped {len(df)} reviews → {out}")


if __name__ == "__main__":
    main()
