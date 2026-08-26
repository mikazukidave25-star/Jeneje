import asyncio
import json
from pathlib import Path

import aiohttp

from modules.utils.logger import get_logger
from modules.utils.oauth import DiscordOAuth

logger = get_logger('owo_oauth')


class CaptchalyBridge:
    """Solves hCaptcha challenges via Captchaly by shelling out to a small
    Node.js helper (node_captcha_solver/) that wraps the official Captchaly
    SDK. No verified native Python client for Captchaly exists, so this reuses
    the same SDK/call pattern already confirmed working in the companion
    TypeScript bot, instead of guessing the raw HTTP API from Python."""

    SOLVER_PATH = Path(__file__).resolve().parents[3] / 'node_captcha_solver' / 'solve.js'

    @staticmethod
    async def solve_hcaptcha(api_key, sitekey, siteurl):
        if not CaptchalyBridge.SOLVER_PATH.exists():
            raise RuntimeError(
                f'Captchaly bridge script not found at {CaptchalyBridge.SOLVER_PATH}. '
                'Run "npm install" inside node_captcha_solver/ first.'
            )

        payload = json.dumps({'apiKey': api_key, 'sitekey': sitekey, 'siteurl': siteurl})

        proc = await asyncio.create_subprocess_exec(
            'node', str(CaptchalyBridge.SOLVER_PATH),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(payload.encode('utf-8'))

        try:
            result = json.loads(stdout.decode('utf-8'))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f'Captchaly bridge returned invalid output: stdout={stdout!r} stderr={stderr!r}') from exc

        if 'error' in result:
            raise RuntimeError(f'Captchaly failed to solve hCaptcha: {result["error"]}')

        return result['token']


class CaptchaSolver:
    REDIRECT_URI = 'https%3A%2F%2Fowobot.com%2Fapi%2Fauth%2Fdiscord%2Fredirect'
    SCOPE = 'identify%20guilds%20email%20guilds.members.read'
    VERIFY_URL = 'https://owobot.com/api/captcha/verify'

    def __init__(self, user_token, bot_id):
        self.user_token = user_token
        self.bot_id = bot_id

    async def get_oauth(self):
        for attempt in range(3):
            referer = (
                'https://discord.com/oauth2/authorize'
                f'?response_type=code&redirect_uri={self.REDIRECT_URI}&scope={self.SCOPE}&client_id={self.bot_id}'
            )
            location = await DiscordOAuth.authorize(
                token=self.user_token,
                client_id=self.bot_id,
                redirect_uri=self.REDIRECT_URI,
                scope=self.SCOPE,
                referer=referer,
            )
            if not location:
                if attempt < 2:
                    await asyncio.sleep(5 * (attempt + 1))
                continue
            session = await DiscordOAuth.submit_redirect(location, host='owobot.com')
            if session:
                return session
            if attempt < 2:
                await asyncio.sleep(5 * (attempt + 1))
        return None

    @staticmethod
    async def verify_captcha(oauth_session, captcha_token, retries=2):
        headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US;en;q=0.8',
            'Content-Type': 'application/json;charset=UTF-8',
            'Origin': 'https://owobot.com',
            'Referer': 'https://owobot.com/captcha',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': DiscordOAuth.DEFAULT_HEADERS['User-Agent'],
        }
        for attempt in range(retries):
            success = await DiscordOAuth.post_json(oauth_session, CaptchaSolver.VERIFY_URL, {'token': captcha_token}, headers)
            if success:
                return True
            if attempt < retries - 1:
                await asyncio.sleep(1 + attempt)
        return False

    @staticmethod
    async def reset_hcaptcha():
        headers = {'User-Agent': DiscordOAuth.DEFAULT_HEADERS['User-Agent']}
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        for attempt in range(3):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get('https://owobot.com/captcha', headers=headers) as resp:
                        logger.info(f'Reset captcha page: {resp.status}')
                        return
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                logger.warning(f'Reset hcaptcha attempt {attempt + 1}/3 failed: {exc}')
                if attempt < 2:
                    await asyncio.sleep(5 * (attempt + 1))
            except Exception:
                logger.exception('Failed to reset hcaptcha')
                return