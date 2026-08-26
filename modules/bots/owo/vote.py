import asyncio
import random

from modules.utils import topgg


class Vote:
    @staticmethod
    async def vote(client):
        if not client.can_run():
            return
        bot_id = getattr(client.owo_bot, 'id', None)
        if not bot_id:
            return
        client.logger.info('Voting on top.gg')
        if await asyncio.to_thread(topgg.vote, bot_id, client.token):
            client.logger.info('Voted (next in 12h)')
            await asyncio.sleep(12 * 3600)
        else:
            wait = random.randint(600, 1200)
            client.logger.warning(f'Vote failed, retry in {wait}s')
            await asyncio.sleep(wait)