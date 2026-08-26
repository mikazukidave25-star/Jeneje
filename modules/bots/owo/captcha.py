import asyncio
import io
import re
import random
import time

import aiohttp
from PIL import Image

from modules.utils import cache, ws
from modules.utils.logger import get_logger
from modules.utils.webhook import DiscordWebhook
from modules.utils.data_store import read_json
from modules.bots.owo.oauth import CaptchaSolver, CaptchalyBridge

logger = get_logger('owo_captcha')


class Captcha:
    @staticmethod
    async def get_image_height(attachment):
        if attachment.height is not None:
            return attachment.height
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(attachment.url) as resp:
                    data = await resp.read()
                    return Image.open(io.BytesIO(data)).height
        except Exception:
            return 0

    @staticmethod
    async def send_captcha(client, captcha_type, message_url, data, expires_in=600):
        user = client.user
        avatar_url = str(user.avatar.url) if user.avatar else f'https://cdn.discordapp.com/embed/avatars/{random.randint(0, 5)}.png'
        created_at_ts = time.time()
        created_at = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(created_at_ts))
        expires_at = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(created_at_ts + expires_in))

        payload = {
            'id': f'{client.bot_name}_{user.id}',
            'user_id': str(user.id),
            'display_name': user.display_name,
            'username': str(user.name),
            'avatar_url': avatar_url,
            'bot': client.bot_name,
            'type': captcha_type,
            'status': 'pending',
            'answer': None,
            'data': data,
            'message_url': message_url,
            'created_at': created_at,
            'expires_at': expires_at,
            'wrong_answers': [],
        }

        cache.add(client.bot_name, user.id, payload)
        ws.emit('captcha_new', payload)
        ws.emit('captcha_count', {'count': cache.count()})
        ws.emit('notification', {
            'title': f'Captcha [{client.bot_name}] - {user.display_name}',
            'body': f'{captcha_type} captcha detected!',
            'tag': f'captcha-{user.id}',
        })
        client.logger.info(f'Captcha sent to web ({captcha_type}) for {user.name}')

        settings = read_json('data/settings.json', {}) or {}
        if 'discord_webhook' in settings:
            webhook = settings['discord_webhook']
            await DiscordWebhook.send(
                webhook_url=webhook.get('url', ''),
                user_name=user.display_name,
                user_avatar=avatar_url,
                content=webhook.get('content', '@everyone @here'),
                title='CAPTCHA DETECTED',
                description=message_url,
            )

    @staticmethod
    async def detect(client, message):
        if not client.owo_bot:
            return

        content = message.content
        is_owo = message.author.id == client.owo_bot.id

        if client.captcha_pending and is_owo:
            is_dm = client.owo_bot.dm_channel and message.channel.id == client.owo_bot.dm_channel.id
            if is_dm:
                if client.message_contains(message.content, any_of=['\U0001f44d', 'thumbsup']):
                    await Captcha.mark_solved(client)
                    return

                if '\U0001f6ab' in content and client._current_captcha_id:
                    cache.add_wrong_answer(client.bot_name, client.user.id, client._current_answer)
                    cache.update(client.bot_name, client.user.id, {'status': 'pending', 'answer': None})
                    ws.emit('captcha_update', {'id': f'{client.bot_name}_{client.user.id}', 'bot': client.bot_name, 'action': 'wrong'})
                    client._current_captcha_id = None
                    client._current_answer = ''
                    client.logger.info('Wrong answer recorded')
                    return

        if client.captcha_pending or not is_owo:
            return

        clean = re.sub(r'[^0-9a-zA-Z]', '', content)
        is_dm = client.owo_bot.dm_channel and message.channel.id == client.owo_bot.dm_channel.id

        is_image = (
            message.attachments
            and await Captcha.get_image_height(message.attachments[0]) <= 100
            and (is_dm or f'**\u26a0\ufe0f | {client.user.name}**' in content)
        )

        is_hcaptcha = (
            client.user.mention in content
            and hasattr(message, 'components') and message.components
            and any(
                'verify' in getattr(child, 'label', '').lower()
                for row in message.components
                for child in getattr(row, 'children', [])
            )
        )

        if not (is_image or is_hcaptcha):
            return

        client.captcha_pending = True

        if is_image:
            await Captcha.handle_image(client, message, clean)
        elif is_hcaptcha:
            await Captcha.handle_hcaptcha(client, message)

    @staticmethod
    async def handle_image(client, message, clean):
        # Stays on the manual web dashboard - Captchaly's advertised catalog
        # (Turnstile, reCAPTCHA v2/v3, hCaptcha, hCaptcha Enterprise, Geetest)
        # doesn't include plain image-to-text solving.
        client.logger.warning('Image captcha detected')
        image_url = message.attachments[0].url if message.attachments else None
        idx = clean.find('letter')
        length = clean[idx - 1] if idx > 0 else '?'

        await Captcha.send_captcha(
            client, 'image', message.jump_url,
            {'render_type': 'image_input', 'image_url': image_url, 'length': length},
        )

    @staticmethod
    async def handle_hcaptcha(client, message):
        client.logger.warning('hCaptcha detected')
        sitekey = 'a6a1d5ce-612d-472d-8e37-7601408fbc09'
        siteurl = 'https://owobot.com/captcha'

        settings = read_json('data/settings.json', {}) or {}
        captchaly_key = (settings.get('captchaly') or {}).get('api_key')

        if captchaly_key:
            if await Captcha.try_captchaly_solve(client, sitekey, siteurl, captchaly_key):
                return
            client.logger.warning('Captchaly auto-solve did not succeed, falling back to manual dashboard')

        await Captcha.send_captcha(
            client, 'hcaptcha', message.jump_url,
            {'render_type': 'widget', 'widget_provider': 'hcaptcha', 'sitekey': sitekey},
        )

    @staticmethod
    async def try_captchaly_solve(client, sitekey, siteurl, api_key):
        """Attempts a full auto-solve+verify via Captchaly. Returns True only
        if owobot.com actually accepted the solved token."""
        try:
            client.logger.info('Solving hCaptcha via Captchaly...')
            token = await CaptchalyBridge.solve_hcaptcha(api_key, sitekey, siteurl)
        except Exception:
            client.logger.exception('Captchaly failed to solve the hCaptcha')
            return False

        solver = CaptchaSolver(client.token, client.owo_bot.id)
        for attempt in range(3):
            oauth_session = await solver.get_oauth()
            if not oauth_session:
                client.logger.warning(f'OAuth attempt {attempt + 1}/3 failed')
                if attempt < 2:
                    await asyncio.sleep(5 * (attempt + 1))
                continue

            try:
                success = await solver.verify_captcha(oauth_session, token)
            except Exception:
                client.logger.exception('hCaptcha verification error')
                success = False
            finally:
                await oauth_session.close()

            if success:
                client.logger.info('hCaptcha auto-solved via Captchaly and verified')
                await Captcha.mark_solved(client)
                return True

            client.logger.warning(f'Verification attempt {attempt + 1}/3 failed')
            if attempt < 2:
                await asyncio.sleep(3)

        client.logger.error('Captchaly-solved token was rejected by owobot.com after all retries')
        await solver.reset_hcaptcha()
        return False

    @staticmethod
    async def mark_solved(client):
        client.captcha_pending = False
        client._current_captcha_id = None
        client._current_answer = ''
        cache.remove(client.bot_name, client.user.id)
        ws.emit('captcha_update', {'id': f'{client.bot_name}_{client.user.id}', 'bot': client.bot_name, 'action': 'solved'})
        ws.emit('captcha_count', {'count': cache.count()})
        client.logger.info('Captcha solved, resuming')

    @staticmethod
    async def process_pending(client):
        pending = cache.list(client.bot_name)
        account_pending = [c for c in pending if str(c.get('user_id', '')) == str(client.user.id)]
        if not account_pending:
            return

        client.captcha_pending = True
        client.logger.warning('Has pending captcha')

        for captcha in account_pending:
            if captcha.get('status') == 'solved' and captcha.get('answer'):
                ok = await Captcha.handle_web_solve(client, captcha, captcha.get('answer'))
                if ok:
                    cache.remove(client.bot_name, client.user.id)

    @staticmethod
    async def handle_web_solve(client, captcha, answer=None):
        captcha_type = captcha.get('type', 'unknown')

        if captcha_type == 'image' and answer:
            try:
                wrong = cache.get_wrong_answers(client.bot_name, client.user.id)
                if answer in wrong:
                    client.logger.warning('Answer already known as wrong, skipping')
                    return False

                client._current_captcha_id = captcha.get('id')
                client._current_answer = answer

                if client.owo_bot and client.owo_bot.dm_channel:
                    await client.owo_bot.dm_channel.send(answer)
                    client.logger.info('Sent image captcha answer')
                    return True
                client.logger.error('OWO DM channel not ready')
            except Exception:
                client.logger.exception('Failed to send image captcha answer')
            return False

        if captcha_type == 'hcaptcha' and answer:
            client.logger.info('hCaptcha token received, attempting to verify')
            solver = CaptchaSolver(client.token, client.owo_bot.id)

            for attempt in range(3):
                oauth_session = await solver.get_oauth()
                if not oauth_session:
                    client.logger.warning(f'OAuth attempt {attempt + 1}/3 failed')
                    if attempt < 2:
                        await asyncio.sleep(5 * (attempt + 1))
                    continue

                try:
                    success = await solver.verify_captcha(oauth_session, answer)
                except Exception:
                    client.logger.exception('hCaptcha verification error')
                    success = False
                finally:
                    await oauth_session.close()

                if success:
                    client.logger.info('hCaptcha verified via owobot.com')
                    return True

                client.logger.warning(f'Verification attempt {attempt + 1}/3 failed')
                if attempt < 2:
                    await asyncio.sleep(3)

            client.logger.error('hCaptcha verification failed after all retries')
            await solver.reset_hcaptcha()
            cache.update(client.bot_name, client.user.id, {'status': 'pending', 'answer': None})
            ws.emit('captcha_update', {'id': f'{client.bot_name}_{client.user.id}', 'bot': client.bot_name, 'action': 'failed'})
            return False

        client.logger.error(f'Unsupported captcha: type={captcha_type}')
        return False

    @staticmethod
    async def handle_web_delete(client):
        client.captcha_pending = False
        client._current_captcha_id = None
        client._current_answer = ''
        client.logger.info('Captcha cleared, resuming')
        return True