from dataclasses import dataclass
from pathlib import Path


DEFAULT_OUTPUT_DIR = Path("./scraped_images")
COOKIES_FILE = Path("./.fb_cookies.json")

# Delay ranges (seconds) for human-like behavior
MIN_ACTION_DELAY = 2.0
MAX_ACTION_DELAY = 5.0
MIN_SCROLL_DELAY = 1.5
MAX_SCROLL_DELAY = 3.5

# How many times to scroll before giving up on finding new content
MAX_STALE_SCROLLS = 5

# Max retries for downloading a single image
DOWNLOAD_RETRIES = 3

# Browser viewport
VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 900


@dataclass(frozen=True)
class ScrapeConfig:
    page_urls: tuple[str, ...]
    output_dir: Path = DEFAULT_OUTPUT_DIR
    cookies_file: Path = COOKIES_FILE
    headless: bool = False
    max_images: int = 0  # 0 = unlimited
    scroll_count: int = 50  # max scrolls per page
    workers: int = 4  # parallel browser tabs
