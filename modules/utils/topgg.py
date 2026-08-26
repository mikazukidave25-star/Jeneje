import os
import sys
import threading
import time
from urllib.parse import urlparse

from curl_cffi import requests as curl
from DrissionPage import ChromiumOptions, ChromiumPage

from modules.utils.logger import get_logger

logger = get_logger('top.gg')

_lock = threading.Lock()
_stop = threading.Event()

BROWSERS = [
    ('chrome-win64', 'chrome.exe'),
    ('chrome-win32', 'chrome.exe'),
    ('chrome-linux64', 'chrome'),
    ('chrome-linux', 'chrome'),
    ('chrome-mac-arm64', 'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'),
    ('chrome-mac-x64', 'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'),
    ('chrome', 'chrome.exe'),
    ('chrome', 'chrome'),
    ('chrome', 'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'),
]

# Fallback for a system-installed browser (e.g. Chromium installed via apt in a
# Docker image), checked after the portable/bundled BROWSERS list above.
SYSTEM_BROWSER_PATHS = [
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    '/usr/bin/google-chrome',
    '/usr/bin/google-chrome-stable',
]


def stop():
    _stop.set()


def clear_stop():
    _stop.clear()


def find_browser():
    base = os.path.dirname(os.path.abspath(sys.argv[0]))
    for folder, binary in BROWSERS:
        path = os.path.join(base, folder, binary)
        if os.path.isfile(path):
            return path
    for path in SYSTEM_BROWSER_PATHS:
        if os.path.isfile(path):
            return path
    return None


def _wait_url(page, text, timeout):
    for _ in range(timeout):
        if _stop.is_set():
            return False
        if text in page.url:
            return True
        time.sleep(0.5)
    return False


def _vote(bot_id, token):
    path = find_browser()
    if not path:
        logger.error('Browser not found for voting')
        return False
    logger.info(f'Voting for bot {bot_id}')

    vote_url = f'https://top.gg/bot/{bot_id}/vote'
    login_url = f'https://top.gg/auth/login?redir=%2Fbot%2F{bot_id}%2Fvote'

    options = ChromiumOptions().set_browser_path(path).auto_port()
    options.headless(True)
    options.set_argument('--no-sandbox')
    options.set_argument('--disable-dev-shm-usage')
    options.set_argument('--disable-gpu')
    # Newer Chrome versions reject DevTools Protocol (remote debugging)
    # connections from an unrecognized origin unless this is set - without it,
    # Chrome launches fine on its own but DrissionPage's connection to it fails.
    options.set_argument('--remote-allow-origins=*')

    # The launch/connect step itself is what fails intermittently under
    # resource contention (e.g. the bot busy hunting/battling at the same
    # moment, on a resource-limited free instance) - retry it specifically,
    # separately from the login-flow retry loop below.
    page = None
    for launch_attempt in range(3):
        try:
            page = ChromiumPage(options)
            break
        except Exception as e:
            logger.warning(f'Browser launch attempt {launch_attempt + 1}/3 failed: {e}')
            if launch_attempt < 2:
                time.sleep(5)
    if page is None:
        logger.error('Failed to launch/connect to the browser after 3 attempts')
        return False
    try:
        for attempt in range(3):
            if _stop.is_set():
                return False
            logger.info(f'Attempt {attempt + 1}/3, opening login')
            page.get(login_url)
            if not page.wait.ele_displayed('xpath://button[contains(., "Login with Discord")]', timeout=25):
                continue
            page.run_js('document.querySelectorAll("button").forEach(e=>{let t=(e.textContent||"").trim().toLowerCase();if(t.indexOf("login with discord")>=0)e.click();});')
            if _wait_url(page, 'discord.com/oauth2/authorize', 30):
                break
        auth = page.url
        if 'discord.com/oauth2/authorize' not in auth:
            logger.error('No oauth url')
            return False
        logger.info('Discord authorize ok')

        r = curl.post(
            'https://discord.com/api/v9/oauth2/authorize?' + urlparse(auth).query,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/111.0',
                     'Accept': '*/*', 'Accept-Language': 'en-US,en;q=0.5',
                     'Content-Type': 'application/json', 'Origin': 'https://discord.com',
                     'Referer': auth, 'Authorization': token,
                     'Sec-Fetch-Dest': 'empty', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Site': 'same-origin'},
            json={'permissions': '0', 'authorize': True}, impersonate='chrome', timeout=30)
        if r.status_code != 200:
            logger.error(f'Consent failed ({r.status_code})')
            return False
        logger.info('Oauth consent ok')

        if _stop.is_set():
            return False
        page.get(r.json()['location'])
        page.wait.doc_loaded(timeout=20)
        if _stop.is_set():
            return False
        page.get(vote_url)
        page.wait.doc_loaded(timeout=20)
        logger.info('On vote page')

        _dismiss_consent(page)
        button = _wait_vote_ready(page)
        if button == 'already':
            logger.info('Already voted')
            return True
        if button is None:
            logger.warning('Vote button never became ready within timeout')
            return False

        if not _click_vote(page, button):
            logger.warning('Failed to click vote button')
            return False
        logger.info('Clicked, waiting for confirmation...')

        success = _wait_confirmation(page)
        logger.info(f'Vote: {success}')
        time.sleep(1)
        return success
    finally:
        try:
            page.quit()
        except Exception:
            pass


def _click_containing(page, *words):
    for b in (page.eles('css:button') or []):
        try:
            if any(w in (b.text or '').lower() for w in words):
                b.click()
                return True
        except Exception:
            pass
    return False


def _dismiss_consent(page):
    _click_containing(page, 'agree', 'accept')
    _click_containing(page, 'reject', 'refuse', 'decline')
    time.sleep(0.5)


def _body(page):
    try:
        el = page.ele('tag:body')
        return (el.text or '').lower() if el else ''
    except Exception:
        return ''


def _wait_vote_ready(page):
    for _ in range(35):
        if _stop.is_set():
            return None
        try:
            button = page.ele('css:button.button-primary', timeout=1)
        except Exception:
            button = None
        if button is not None:
            try:
                if button.states.is_enabled:
                    return button
            except Exception:
                pass
        if 'already' in _body(page) or 'vote again' in _body(page):
            return 'already'
        _dismiss_consent(page)
        time.sleep(1)
    return None


def _click_vote(page, button):
    try:
        button.click()
        return True
    except Exception:
        pass
    try:
        page.run_js('let b=document.querySelector("button.button-primary");if(b)b.click();')
        return True
    except Exception:
        return False


def _wait_confirmation(page):
    for _ in range(15):
        if _stop.is_set():
            return False
        time.sleep(1)
        body_text = _body(page)
        if any(k in body_text for k in ('thanks for voting', 'thank you for voting', 'voted for', 'vote received')):
            return True
        try:
            button = page.ele('css:button.button-primary', timeout=1)
            if button is not None and not button.states.is_enabled:
                return True
        except Exception:
            pass
        if 'already' in body_text or 'vote again' in body_text:
            return False
    return False


def vote(bot_id, token):
    with _lock:
        if _stop.is_set():
            logger.warning('Vote skipped (stop requested)')
            return False
        return _vote(bot_id, token)
