import asyncio
import time
import datetime

import discord

from modules.bots.owo.daily import Daily
from modules.utils.component import Component


class Boss:
    @staticmethod
    async def handle(client, message):
        if not client.can_run():
            return
        if not client.is_owo_message(message):
            return
        if time.time() < client.cooldown_boss:
            return
        if not message.components:
            return

        children = getattr(message.components[0], 'children', None)
        if not children:
            return

        if 'A Guild Boss Appeared!' not in Component.text(children[0]):
            return

        boss_channel_id = client.config.get('boss_channel_id')
        if boss_channel_id and message.channel.id != int(boss_channel_id):
            return

        fight = getattr(children[-1], 'accessory', None)
        if fight is None or getattr(fight, 'disabled', False):
            return

        channel = message.channel
        watch_task = asyncio.create_task(Boss._watch_ticket_response(client, channel))
        try:
            await fight.click()
        except discord.HTTPException:
            watch_task.cancel()
            await asyncio.gather(watch_task, return_exceptions=True)
            client.logger.exception('Failed to click boss fight')
            return

        client.logger.info(f'Joined boss battle in #{channel}')
        await watch_task

    @staticmethod
    async def _watch_ticket_response(client, channel):
        def is_ticket_response(message):
            if message.channel.id != channel.id:
                return False
            for component in message.components:
                try:
                    if "You don't have any boss tickets!" in Component.text(component):
                        return True
                except Exception:
                    continue
            return False

        try:
            await client.wait_for('message', check=is_ticket_response, timeout=5)
        except asyncio.TimeoutError:
            return

        wait = Daily.reset_time(client.cooldown_reset)
        client.cooldown_boss = wait + time.time()
        client.logger.info(f'Run out of boss tickets (reset in {datetime.timedelta(seconds=wait)})')