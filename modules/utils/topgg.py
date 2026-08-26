import json
import os
import subprocess
import sys
import threading

from modules.utils.data_store import read_json
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

VOTE_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'node_captcha_solver', 'vote.js')


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


def _vote(bot_id, token):
    """Runs node_captcha_solver/vote.js (puppeteer-extra + stealth plugin) to
    do the actual voting. DrissionPage's plain Chromium automation was
    reliably blocked by Cloudflare's bot check on top.gg ("Just a moment...")
    - the stealth plugin patches the headless-detection signals Cloudflare
    looks for, which DrissionPage has no equivalent for. This reuses a script
    the user already had working, instead of trying to replicate that
    stealth layer in Python."""
    path = find_browser()
    if not path:
        logger.error('Browser not found for voting')
        return False
    if not os.path.isfile(VOTE_SCRIPT):
        logger.error(f'vote.js not found at {VOTE_SCRIPT}. Run "npm install" inside node_captcha_solver/ first.')
        return False

    settings = read_json('data/settings.json', {}) or {}
    captchaly_key = (settings.get('captchaly') or {}).get('api_key')

    logger.info(f'Voting for bot {bot_id}')
    payload = json.dumps({'token': token, 'botId': bot_id, 'chromePath': path, 'captchalyApiKey': captchaly_key})

    try:
        proc = subprocess.run(
            ['node', VOTE_SCRIPT],
            input=payload, capture_output=True, text=True, timeout=180,
        )
    except subprocess.TimeoutExpired:
        logger.error('vote.js timed out after 180s')
        return False

    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        logger.error(f'vote.js returned invalid output: stdout={proc.stdout!r} stderr={proc.stderr!r}')
        return False

    if result.get('success'):
        logger.info(f'Vote: {result.get("message")}')
        return True

    logger.warning(f'Vote failed: {result.get("message")}')
    if proc.stderr:
        logger.warning(f'vote.js stderr: {proc.stderr.strip()}')
    return False


def vote(bot_id, token):
    with _lock:
        if _stop.is_set():
            logger.warning('Vote skipped (stop requested)')
            return False
        return _vote(bot_id, token)
