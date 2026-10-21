"""udb's own browser for Stream: one login, then every class without clicks.

Stream needs a real Google Chrome (H.264/AAC; Playwright's Chromium cannot play
it). On WSL this drives the Windows Chrome through its debugging port, with a
separate profile only for udb, so the student's everyday Chrome is untouched.
`udb browser login` opens it once to sign in to Microsoft; the session stays in
that profile. Nothing is downloaded: it reads the transcript panel and takes
stills of the player, see stream.py.
"""
import shutil
import subprocess
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from ...core import settings

PORT = 9333
WINDOWS_CHROME = Path("/mnt/c/Program Files/Google/Chrome/Application/chrome.exe")
LOGIN_HOSTS = ("login.microsoftonline.com", "login.live.com")


class BrowserError(RuntimeError):
    pass


def chrome_binary() -> str:
    cfg = (settings.get().data.get("browser") or {})
    if cfg.get("chrome"):
        return cfg["chrome"]
    for name in ("google-chrome", "google-chrome-stable"):
        found = shutil.which(name)
        if found:
            return found
    if WINDOWS_CHROME.exists():
        return str(WINDOWS_CHROME)
    raise BrowserError("Google Chrome not found (Chromium cannot play Stream videos). "
                       "Install Chrome or set browser.chrome in udb.yaml")


def profile_dir(binary: str) -> str:
    """Windows Chrome needs a Windows path; Linux Chrome a Linux one."""
    if binary.endswith(".exe"):
        out = subprocess.run(["powershell.exe", "-NoProfile", "-Command", "$env:LOCALAPPDATA"],
                             capture_output=True, text=True).stdout.strip()
        return out + r"\udb\chrome-profile"
    path = settings.get().secrets / "chrome-profile"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def _ready(port: int) -> bool:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1)
        return True
    except OSError:
        return False


@contextmanager
def chrome(headless: bool = True, url: str = "about:blank", port: int = PORT):
    """Start udb's Chrome and yield a Playwright browser connected to it."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserError("needs: uv tool install 'udb-copilot[browser]'") from exc
    binary = chrome_binary()
    args = [binary, f"--user-data-dir={profile_dir(binary)}", f"--remote-debugging-port={port}",
            "--no-first-run", "--no-default-browser-check", "--mute-audio",
            "--autoplay-policy=no-user-gesture-required"]
    if headless:
        args.append("--headless=new")
    proc = None
    if not _ready(port):
        proc = subprocess.Popen(args + [url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            if _ready(port):
                break
            time.sleep(0.5)
        else:
            raise BrowserError("Chrome did not open its debugging port")
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        try:
            yield browser
        finally:
            if proc:  # only close a Chrome this call started
                try:
                    browser.new_browser_cdp_session().send("Browser.close")
                except Exception:  # noqa: BLE001 - closing is best effort
                    proc.terminate()


def login() -> None:
    """Open udb's Chrome so the student signs in to Microsoft once."""
    with chrome(headless=False, url="https://www.microsoft365.com/") as browser:
        print("Sign in with your UDB account in the Chrome window that opened "
              "(tick 'Stay signed in'). Press Enter here when you see your Microsoft 365 home.")
        input()
        page = browser.contexts[0].pages[0]
        if any(h in page.url for h in LOGIN_HOSTS):
            raise BrowserError("still on the Microsoft sign-in page; run udb browser login again")


def _open_stream(browser, url: str):
    page = browser.contexts[0].new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=90_000)
    page.wait_for_timeout(4000)
    if any(h in page.url for h in LOGIN_HOSTS):
        raise BrowserError("the Microsoft session expired. Run: udb browser login")
    page.wait_for_selector("video", timeout=90_000)
    page.wait_for_function("document.querySelector('video').readyState >= 2", timeout=90_000)
    if not page.query_selector('[id^="sub-entry-"]'):
        for name in ("Transcripción", "Transcript"):
            button = page.get_by_role("button", name=name)
            if button.count():
                button.first.click()
                break
        page.wait_for_selector('[id^="sub-entry-"]', timeout=60_000)
    return page


def read_stream(url: str, boards: bool = True, fine: int = 2, coarse: int = 6,
                on_transcript=None) -> tuple[dict, dict | None]:
    """Transcript (always) and board stills (optional) of one Stream recording."""
    from .stream import BOARDS_FN, TRANSCRIPT_FN, segments_from, solving_spans
    with chrome(headless=True) as browser:
        page = _open_stream(browser, url)
        transcript = page.evaluate(TRANSCRIPT_FN)
        if on_transcript:
            on_transcript(transcript)
        if not boards:
            return transcript, None
        spans = solving_spans(segments_from(transcript["entries"], transcript["duration"]))
        page.set_default_timeout(0)
        stills = page.evaluate(BOARDS_FN, {"fine": fine, "coarse": coarse, "spans": spans})
        page.close()
        return transcript, stills
