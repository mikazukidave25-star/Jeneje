import aiohttp
import asyncio

from modules.utils.logger import get_logger

logger = get_logger('oauth')


class DiscordOAuth:
    DEFAULT_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/111.0',
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Content-Type': 'application/json',
        'Origin': 'https://discord.com',
        'Connection': 'keep-alive',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
    }

    @staticmethod
    async def authorize(token, client_id, redirect_uri, scope, referer=None, permissions='0', retries=2):
        url = (
            'https://discord.com/api/v9/oauth2/authorize'
            f'?response_type=code&redirect_uri={redirect_uri}&scope={scope}&client_id={client_id}'
        )
        headers = dict(DiscordOAuth.DEFAULT_HEADERS)
        headers['Authorization'] = token
        headers['Referer'] = referer or f'https://discord.com/oauth2/authorize?client_id={client_id}'
        timeout = aiohttp.ClientTimeout(total=30, connect=10)

        for attempt in range(retries + 1):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, headers=headers, json={'permissions': permissions, 'authorize': True}) as resp:
                        if resp.status == 200:
                            return (await resp.json()).get('location')
                        logger.error(f'OAuth authorize failed: {resp.status}')
                        return None
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                logger.warning(f'OAuth authorize attempt {attempt + 1}/{retries + 1} failed: {exc}')
                if attempt == retries:
                    return None
                await asyncio.sleep(2 ** attempt)
            except Exception:
                logger.exception('OAuth authorize failed')
                return None

    @staticmethod
    async def submit_redirect(location, host, referer='https://discord.com/', retries=2):
        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'accept-language': 'en-US,en;q=0.5',
            'connection': 'keep-alive',
            'host': host,
            'referer': referer,
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'cross-site',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': DiscordOAuth.DEFAULT_HEADERS['User-Agent'],
        }
        timeout = aiohttp.ClientTimeout(total=30, connect=10)

        for attempt in range(retries + 1):
            session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(), timeout=timeout)
            try:
                async with session.get(location, headers=headers, allow_redirects=False) as resp:
                    if resp.status in (302, 307):
                        return session
                    logger.error(f'OAuth redirect failed: {resp.status}')
                    await session.close()
                    return None
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                logger.warning(f'OAuth redirect attempt {attempt + 1}/{retries + 1} failed: {exc}')
                await session.close()
                if attempt == retries:
                    return None
                await asyncio.sleep(2 ** attempt)
            except Exception:
                logger.exception('OAuth redirect failed')
                await session.close()
                return None

    @staticmethod
    async def post_json(session, url, payload, headers=None):
        try:
            async with session.post(url, headers=headers or {}, json=payload, timeout=aiohttp.ClientTimeout(total=30, connect=10)) as resp:
                if resp.status == 200:
                    return True
                logger.error(f'OAuth POST failed: {resp.status}')
                return False
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.warning(f'OAuth POST failed: {exc}')
            return False
        except Exception:
            logger.exception('OAuth POST error')
            return False