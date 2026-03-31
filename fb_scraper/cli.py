"""CLI interface for the Facebook image scraper."""

from pathlib import Path

import click
from rich.console import Console

from fb_scraper.config import COOKIES_FILE, DEFAULT_OUTPUT_DIR, ScrapeConfig
from fb_scraper.scraper import run_scraper

console = Console()


@click.command()
@click.argument("page_urls", nargs=-1, required=True)
@click.option(
    "-o", "--output",
    type=click.Path(path_type=Path),
    default=DEFAULT_OUTPUT_DIR,
    help="Output directory for downloaded images.",
    show_default=True,
)
@click.option(
    "--max-images",
    type=int,
    default=0,
    help="Max images per page (0 = unlimited).",
    show_default=True,
)
@click.option(
    "--scroll-count",
    type=int,
    default=50,
    help="Max number of scrolls per page.",
    show_default=True,
)
@click.option(
    "-w", "--workers",
    type=int,
    default=4,
    help="Number of parallel browser tabs.",
    show_default=True,
)
@click.option(
    "--headless/--no-headless",
    default=False,
    help="Run browser in headless mode (not recommended).",
    show_default=True,
)
@click.option(
    "--cookies",
    type=click.Path(path_type=Path),
    default=COOKIES_FILE,
    help="Path to cookies file.",
    show_default=True,
)
def main(
    page_urls: tuple[str, ...],
    output: Path,
    max_images: int,
    scroll_count: int,
    workers: int,
    headless: bool,
    cookies: Path,
) -> None:
    """Scrape images from Facebook pages for ML dataset collection.

    First run: a browser opens, you log in to Facebook manually,
    then press Enter in the terminal. Cookies are saved for future runs.

    Examples:

        uv run fb-scraper https://facebook.com/SomePage

        uv run fb-scraper https://facebook.com/Page1 https://facebook.com/Page2 -w 4

        uv run fb-scraper https://facebook.com/Page1 -o ./dataset --max-images 100
    """
    config = ScrapeConfig(
        page_urls=page_urls,
        output_dir=output,
        cookies_file=cookies,
        headless=headless,
        max_images=max_images,
        scroll_count=scroll_count,
        workers=workers,
    )

    run_scraper(config)


if __name__ == "__main__":
    main()
