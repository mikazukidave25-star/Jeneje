import asyncio
import aiohttp
import re
import io
import os
import glob
import time
import datetime

import numpy as np
from PIL import Image


class Huntbot:
    _templates = None

    @staticmethod
    def _load_templates():
        if Huntbot._templates is not None:
            return Huntbot._templates

        templates = []
        for img_path in sorted(glob.glob(os.path.join('assets/owo/huntbot', '**', '*.png'), recursive=True)):
            img = Image.open(img_path)
            letter = img_path.replace('\\', '/').split('/')[-1].split('.')[0]
            templates.append((np.array(img), img.size, letter))
        Huntbot._templates = templates
        return templates

    @staticmethod
    async def solve_password(captcha_url):
        templates = Huntbot._load_templates()
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        for attempt in range(3):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(captcha_url) as resp:
                        large_image = Image.open(io.BytesIO(await resp.read()))
                        large_array = np.array(large_image)
                break
            except (aiohttp.ClientError, asyncio.TimeoutError):
                if attempt < 2:
                    await asyncio.sleep(5 * (attempt + 1))
                else:
                    raise

        matches = []
        for small_array, (sw, sh), letter in templates:
            mask = small_array[:, :, 3] > 0
            for y in range(large_array.shape[0] - sh + 1):
                for x in range(large_array.shape[1] - sw + 1):
                    segment = large_array[y:y + sh, x:x + sw]
                    if np.array_equal(segment[mask], small_array[mask]):
                        if not any(
                            (m[0] - sw < x < m[0] + sw) and (m[1] - sh < y < m[1] + sh)
                            for m in matches
                        ):
                            matches.append((x, y, letter))

        return ''.join(m[2] for m in sorted(matches, key=lambda t: t[0]))

    @staticmethod
    async def claim_submit(client):
        if not client.can_run():
            return
        if time.time() < client.cooldown_huntbot:
            return
        if not client.current_channel:
            return

        await client.current_channel.send(f'{client.prefix}hb 1d')
        client.logger.info(f'Sent {client.prefix}hb 1d')

        try:
            message = await client.wait_for(
                'message',
                check=lambda m: (
                    client.is_owo_message(m, in_channel=True)
                    and client.message_contains(m.content, any_of=[
                        'Please include your password', 'Here is your password!',
                        'STILL HUNTING', 'BACK WITH',
                    ])
                ),
                timeout=5,
            )
            content = message.content
            nick = str(client.nickname)

            if 'Please include your password' in content and nick in content:
                minutes = re.findall(r'Password will reset in (\d+)', content)
                if minutes:
                    wait = int(minutes[0]) * 60
                    client.cooldown_huntbot = wait + time.time()
                    client.logger.info(f'Huntbot password reset in {datetime.timedelta(seconds=wait)}')

            elif 'Here is your password!' in content and nick in content and message.attachments:
                answer = await Huntbot.solve_password(message.attachments[0].url)
                if not client.can_run() or not client.current_channel:
                    return
                await client.current_channel.send(f'{client.prefix}hb 1d {answer}')
                client.logger.info(f'Sent {client.prefix}hb 1d {answer}')

                try:
                    verify = await client.wait_for(
                        'message',
                        check=lambda m: (
                            client.is_owo_message(m, in_channel=True)
                            and client.message_contains(m.content, all_of=[nick])
                            and client.message_contains(m.content, any_of=['YOU SPENT', 'Wrong password'])
                        ),
                        timeout=5,
                    )
                    if 'YOU SPENT' in verify.content:
                        client.logger.info('Huntbot submitted successfully')
                    elif 'Wrong password' in verify.content:
                        client.logger.warning('Huntbot wrong password')
                except asyncio.TimeoutError:
                    client.logger.warning('Huntbot verification timeout')

            elif 'STILL HUNTING' in content:
                match = re.search(r'`(.*?)`', content)
                nums = re.findall(r'[0-9]+', match.group(1)) if match else []
                if len(nums) == 1:
                    wait = int(nums[0]) * 60
                elif len(nums) >= 2:
                    wait = int(nums[0]) * 3600 + int(nums[1]) * 60
                else:
                    wait = 3600
                client.cooldown_huntbot = wait + time.time()
                client.logger.info(f'Huntbot returns in {datetime.timedelta(seconds=wait)}')

            elif 'BACK WITH' in content:
                client.logger.info('Claimed huntbot')

        except asyncio.TimeoutError:
            client.logger.warning('Huntbot claim timeout')