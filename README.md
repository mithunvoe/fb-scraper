# fb-scraper

A Facebook image scraper built with Python and Playwright for collecting high-resolution images from Facebook **pages** and **groups**. Designed for ML dataset collection (e.g., fake photocard detection).

It uses browser automation to navigate Facebook's Photos tab, click each photo to trigger the full-resolution CDN load, and saves images directly to disk. Supports parallel downloads via multiple browser tabs and graceful shutdown (Ctrl+C saves all progress).

## Features

- Full-resolution image downloads (not thumbnails)
- Parallel scraping with configurable worker count (multiple browser tabs)
- Cookie-based authentication (log in once, reuse session)
- Graceful Ctrl+C handling (images saved immediately, nothing lost)
- SHA-256 deduplication (no duplicate images)
- Anti-detection measures (stealth patches, human-like delays)
- Works with both Facebook **pages** and **groups**

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- A Facebook account

## Quick Start

```bash
# Clone the repo
git clone https://github.com/mithunvoe/fb-scraper.git
cd fb-scraper

# Install dependencies
uv sync

# Install the browser engine
uv run playwright install chromium

# Scrape a page
uv run fb-scraper https://www.facebook.com/SomePage
```

## First Run (Authentication)

On the first run, the scraper opens a Chromium browser window and navigates to Facebook's login page.

1. **Log in to Facebook** in the browser window that opens
2. Complete any security checks (2FA, CAPTCHA, etc.) - take your time
3. Once you see your Facebook feed/homepage, **switch back to the terminal**
4. **Press Enter** in the terminal to confirm login

Your session cookies are saved to `.fb_cookies.json`. Future runs will reuse them automatically - no login needed.

> If cookies expire (you get redirected to login again), delete `.fb_cookies.json` and repeat the login process.

## Usage

```bash
# Scrape a single page
uv run fb-scraper https://www.facebook.com/SomePage

# Scrape a Facebook group
uv run fb-scraper https://www.facebook.com/groups/SomeGroup

# Scrape multiple pages/groups at once
uv run fb-scraper https://www.facebook.com/Page1 https://www.facebook.com/groups/Group1

# Limit to 100 images per page
uv run fb-scraper https://www.facebook.com/Page1 --max-images 100

# Custom output directory
uv run fb-scraper https://www.facebook.com/Page1 -o ./dataset/photocards

# Use 6 parallel browser tabs (faster, but more resource-heavy)
uv run fb-scraper https://www.facebook.com/Page1 -w 6

# More scrolling to find more photos (default: 50 scrolls)
uv run fb-scraper https://www.facebook.com/Page1 --scroll-count 100
```

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `-o, --output` | `./scraped_images` | Output directory |
| `--max-images` | `0` (unlimited) | Max images per page/group |
| `--scroll-count` | `50` | Max scrolls to discover photos |
| `-w, --workers` | `4` | Number of parallel browser tabs |
| `--headless / --no-headless` | `--no-headless` | Run without visible browser |
| `--cookies` | `.fb_cookies.json` | Path to session cookies file |

## Parallelism

The scraper uses multiple browser tabs working concurrently. Each worker opens the same Photos page and handles a subset of the photos:

- Worker 0: photos 1, 5, 9, 13, ...
- Worker 1: photos 2, 6, 10, 14, ...
- Worker 2: photos 3, 7, 11, 15, ...
- Worker 3: photos 4, 8, 12, 16, ...

Increase workers with `-w` for faster scraping. More workers = more RAM usage. 4 workers is a good default; 6-8 works well on machines with 8GB+ RAM.

## Graceful Shutdown

Press **Ctrl+C** once to stop gracefully. Workers finish their current photo and exit. All images downloaded up to that point are already saved to disk.

Press **Ctrl+C** twice to force-exit immediately.

## Output Structure

```
scraped_images/
  PageName/
    PageName_0001.jpg
    PageName_0002.jpg
    ...
  GroupName/
    GroupName_0001.jpg
    ...
```

Images are saved immediately as they're downloaded. Each page/group gets its own subdirectory.

## How It Works

1. **Authentication**: Loads saved cookies or prompts for manual login
2. **Discovery**: Navigates to the Photos tab and scrolls to find all photo thumbnails
3. **Parallel capture**: Opens multiple browser tabs, each clicking photos to trigger Facebook's full-resolution CDN image load
4. **Network interception**: Captures the largest image from each CDN response (typically 100KB-1MB+ vs 10KB thumbnails)
5. **Immediate save**: Each image is written to disk as soon as it's downloaded
6. **Deduplication**: SHA-256 hash check prevents saving duplicate images

## Troubleshooting

**"Cookies expired" / redirected to login**: Delete `.fb_cookies.json` and run again to re-login.

**Too few images found**: Increase `--scroll-count` (default 50). Some pages have thousands of photos that require more scrolling.

**Facebook blocks or rate-limits**: Reduce workers with `-w 2` and increase scroll delay by waiting longer between runs.

## License

MIT
