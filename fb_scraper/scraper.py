"""Core Facebook page image scraper - full resolution via parallel async tabs."""

import asyncio
import hashlib
import re
import signal
from pathlib import Path
from urllib.parse import urlparse
from random import uniform, randint

from playwright.async_api import async_playwright, Page, BrowserContext
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

from fb_scraper.config import (
    DOWNLOAD_RETRIES,
    MAX_ACTION_DELAY,
    MAX_SCROLL_DELAY,
    MAX_STALE_SCROLLS,
    MIN_ACTION_DELAY,
    MIN_SCROLL_DELAY,
    ScrapeConfig,
    VIEWPORT_HEIGHT,
    VIEWPORT_WIDTH,
)

console = Console()

# Shutdown flag
_shutdown = False


def _setup_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    def handler():
        global _shutdown
        if _shutdown:
            raise SystemExit(1)
        console.print("\n[yellow]Shutting down gracefully... (Ctrl+C again to force)[/yellow]")
        _shutdown = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handler)


def extract_page_name(url: str) -> str:
    parsed = urlparse(url.rstrip("/"))
    path = parsed.path.strip("/")
    name = path.split("/")[0] if "/" in path else path
    name = re.sub(r"[^\w\-]", "_", name)
    return name or "unknown_page"


def get_photos_tab_url(page_url: str) -> str:
    url = page_url.rstrip("/")
    if "/photos" in url:
        return url
    return f"{url}/photos"


async def async_random_delay(page: Page) -> None:
    await page.wait_for_timeout(uniform(MIN_ACTION_DELAY, MAX_ACTION_DELAY) * 1000)


async def async_human_scroll(page: Page) -> None:
    distance = randint(600, 1200)
    await page.evaluate(f"window.scrollBy(0, {distance})")
    await page.wait_for_timeout(uniform(MIN_SCROLL_DELAY, MAX_SCROLL_DELAY) * 1000)


async def dismiss_login_popup(page: Page) -> None:
    try:
        close_btn = await page.query_selector('[aria-label="Close"]')
        if close_btn:
            await close_btn.click()
            await page.wait_for_timeout(1000)
    except Exception:
        pass


async def apply_stealth_async(page: Page) -> None:
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => false });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        delete window.__playwright;
        delete window.__pw_manual;
    """)


# -- Auth (async versions) --

import json

async def load_cookies_async(context: BrowserContext, cookies_file: Path) -> bool:
    if not cookies_file.exists():
        return False
    try:
        cookies = json.loads(cookies_file.read_text())
        await context.add_cookies(cookies)
        console.print("[green]Loaded saved cookies[/green]")
        return True
    except (json.JSONDecodeError, KeyError):
        console.print("[yellow]Cookie file corrupted, need fresh login[/yellow]")
        return False


async def save_cookies_async(context: BrowserContext, cookies_file: Path) -> None:
    cookies = await context.cookies()
    cookies_file.write_text(json.dumps(cookies, indent=2))
    console.print(f"[green]Cookies saved to {cookies_file}[/green]")


async def is_logged_in_async(page: Page) -> bool:
    await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30_000)
    await page.wait_for_timeout(3000)
    login_form = await page.query_selector('input[name="email"]')
    return login_form is None


async def wait_for_manual_login_async(page: Page) -> None:
    await page.goto("https://www.facebook.com/login", wait_until="domcontentloaded", timeout=30_000)
    console.print()
    console.print("[bold yellow]Please log in to Facebook in the browser window.[/bold yellow]")
    console.print("[bold yellow]Take your time - 2FA, security checks, whatever you need.[/bold yellow]")
    console.print()
    console.print("[bold cyan]>>> Press ENTER here in the terminal when you are fully logged in <<<[/bold cyan]")
    console.print()
    await asyncio.get_event_loop().run_in_executor(None, input)
    console.print("[green]Login confirmed![/green]")


# -- Discovery --

async def discover_photo_thumbnails(page: Page, config: ScrapeConfig) -> list[str]:
    collected: list[str] = []
    seen: set[str] = set()
    stale_count = 0
    prev_count = 0

    for scroll_num in range(1, config.scroll_count + 1):
        if _shutdown:
            break

        await dismiss_login_popup(page)
        await async_human_scroll(page)

        imgs = await page.query_selector_all("img")
        for img in imgs:
            src = await img.get_attribute("src") or ""
            if "scontent" not in src:
                continue
            base = src.split("?")[0].split("/")[-1]
            if base not in seen:
                seen.add(base)
                collected.append(src)

        current_count = len(collected)
        if current_count == prev_count:
            stale_count += 1
        else:
            stale_count = 0
        prev_count = current_count

        if stale_count >= MAX_STALE_SCROLLS:
            console.print(f"[yellow]No new photos after {MAX_STALE_SCROLLS} scrolls, stopping[/yellow]")
            break
        if config.max_images > 0 and current_count >= config.max_images:
            break
        if scroll_num % 5 == 0:
            console.print(f"[dim]Scroll {scroll_num}/{config.scroll_count} - found {current_count} photos so far[/dim]")

    if config.max_images > 0:
        collected = collected[: config.max_images]
    return collected


# -- Per-photo high-res capture --

async def click_and_capture_highres(page: Page, thumb_src: str) -> str | None:
    # Find the thumbnail element
    base_name = thumb_src.split("?")[0].split("/")[-1]

    img_el = None
    imgs = await page.query_selector_all("img")
    for img in imgs:
        src = await img.get_attribute("src") or ""
        if base_name in src:
            img_el = img
            break

    if not img_el:
        return None

    try:
        await img_el.scroll_into_view_if_needed()
        await page.wait_for_timeout(500)
    except Exception:
        pass

    captured: list[tuple[str, int]] = []

    def on_response(response):
        url = response.url
        if "scontent" not in url:
            return
        ct = response.headers.get("content-type", "")
        if "image" not in ct:
            return
        try:
            cl = int(response.headers.get("content-length", "0"))
        except ValueError:
            cl = 0
        captured.append((url, cl))

    page.on("response", on_response)

    try:
        await img_el.click()
        await page.wait_for_timeout(4000)
    except Exception:
        page.remove_listener("response", on_response)
        return None

    page.remove_listener("response", on_response)

    # Fallback: grab from viewer DOM
    if not captured:
        all_imgs = await page.query_selector_all("img")
        for img in all_imgs:
            src = await img.get_attribute("src") or ""
            if "scontent" not in src:
                continue
            box = await img.bounding_box()
            if box and box["width"] > 400:
                captured.append((src, 1))
                break

    # Close viewer
    try:
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(1000)
    except Exception:
        pass

    if not captured:
        return None

    captured.sort(key=lambda x: x[1], reverse=True)
    return captured[0][0]


async def download_url(page: Page, url: str, filepath: Path) -> bool:
    for attempt in range(1, DOWNLOAD_RETRIES + 1):
        try:
            response = await page.request.get(url)
            if response.status != 200:
                if attempt < DOWNLOAD_RETRIES:
                    await page.wait_for_timeout(1000)
                    continue
                return False
            data = await response.body()
            if len(data) < 10_240:
                return False
            filepath.write_bytes(data)
            return True
        except Exception:
            if attempt == DOWNLOAD_RETRIES:
                return False
            await page.wait_for_timeout(1000)
    return False


# -- Worker --

async def worker(
    worker_id: int,
    context: BrowserContext,
    photos_url: str,
    thumbnails: list[str],
    output_dir: Path,
    page_name: str,
    seen_hashes: set[str],
    counter: dict,
    progress: Progress,
    task_id,
) -> None:
    page = await context.new_page()
    await apply_stealth_async(page)

    try:
        await page.goto(photos_url, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(3000)
        await dismiss_login_popup(page)

        for thumb_src in thumbnails:
            if _shutdown:
                break

            highres_url = await click_and_capture_highres(page, thumb_src)

            if highres_url:
                idx = counter["next_idx"]
                counter["next_idx"] += 1

                ext = "jpg"
                if ".png" in highres_url.lower():
                    ext = "png"
                elif ".webp" in highres_url.lower():
                    ext = "webp"

                filename = f"{page_name}_{idx:04d}.{ext}"
                filepath = output_dir / filename

                if await download_url(page, highres_url, filepath):
                    data = filepath.read_bytes()
                    h = hashlib.sha256(data).hexdigest()
                    if h in seen_hashes:
                        filepath.unlink()
                        counter["dupes"] += 1
                    else:
                        seen_hashes.add(h)
                        counter["saved"] += 1

            progress.advance(task_id)

    except Exception as e:
        if not _shutdown:
            console.print(f"[red]Worker {worker_id} error: {e}[/red]")
    finally:
        try:
            await page.close()
        except Exception:
            pass


# -- Main scrape logic --

async def scrape_page(
    context: BrowserContext,
    main_page: Page,
    page_url: str,
    config: ScrapeConfig,
) -> None:
    page_name = extract_page_name(page_url)
    photos_url = get_photos_tab_url(page_url)

    console.rule(f"[bold]Scraping: {page_name}[/bold]")
    console.print(f"URL: {photos_url}")

    await main_page.goto(photos_url, wait_until="domcontentloaded", timeout=60_000)
    await async_random_delay(main_page)
    await dismiss_login_popup(main_page)

    console.print("[cyan]Scrolling to discover photos...[/cyan]")
    thumbnails = await discover_photo_thumbnails(main_page, config)
    console.print(f"[green]Found {len(thumbnails)} photos[/green]")

    if not thumbnails or _shutdown:
        return

    output_dir = config.output_dir / page_name
    output_dir.mkdir(parents=True, exist_ok=True)

    num_workers = config.workers
    # Round-robin distribution
    worker_batches: list[list[str]] = [[] for _ in range(num_workers)]
    for i, thumb in enumerate(thumbnails):
        worker_batches[i % num_workers].append(thumb)

    seen_hashes: set[str] = set()
    counter = {"saved": 0, "dupes": 0, "next_idx": 1}

    console.print(f"[cyan]Downloading with {num_workers} parallel workers...[/cyan]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task(f"Scraping {page_name}", total=len(thumbnails))

        tasks = []
        for wid, batch in enumerate(worker_batches):
            if not batch:
                continue
            tasks.append(
                worker(
                    wid, context, photos_url, batch,
                    output_dir, page_name, seen_hashes,
                    counter, progress, task_id,
                )
            )

        await asyncio.gather(*tasks)

    console.print(
        f"[green]Done:[/green] {counter['saved']} saved, "
        f"{counter['dupes']} duplicates skipped"
    )


async def async_main(config: ScrapeConfig) -> None:
    _setup_signal_handlers(asyncio.get_event_loop())

    console.print("[bold]Facebook Image Scraper[/bold]")
    console.print(f"Pages to scrape: {len(config.page_urls)}")
    console.print(f"Output directory: {config.output_dir}")
    console.print(f"Workers: {config.workers}")
    console.print()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=config.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )
        context = await browser.new_context(
            viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )
        main_page = await context.new_page()
        await apply_stealth_async(main_page)

        # Auth
        cookies_loaded = await load_cookies_async(context, config.cookies_file)
        if cookies_loaded and await is_logged_in_async(main_page):
            console.print("[green]Already logged in via saved cookies[/green]")
        else:
            await wait_for_manual_login_async(main_page)
            await save_cookies_async(context, config.cookies_file)

        # Scrape
        for page_url in config.page_urls:
            if _shutdown:
                break
            try:
                await scrape_page(context, main_page, page_url, config)
            except Exception as e:
                console.print(f"[red]Error scraping {page_url}: {e}[/red]")
                console.print_exception()
                continue

        await save_cookies_async(context, config.cookies_file)

        saved = len(list(config.output_dir.rglob("*.*"))) if config.output_dir.exists() else 0
        console.print(f"\n[bold green]All done! Total images on disk: {saved}[/bold green]")
        await browser.close()


def run_scraper(config: ScrapeConfig) -> None:
    asyncio.run(async_main(config))
