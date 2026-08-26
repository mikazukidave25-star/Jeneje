import asyncio
import random
import time

import discord

from modules.bots.owo.daily import Daily
from modules.utils.component import Component


class Checklist:
    @staticmethod
    def _lines(message):
        for child in Component.descendants(message):
            text = Component.text(child)
            if text:
                yield from text.splitlines()

    @staticmethod
    def _has_header(message, user, header):
        if header in message.content and user in message.content:
            return True
        for child in Component.descendants(message):
            text = Component.text(child)
            if header in text and user in text:
                return True
        return False

    @staticmethod
    def scan(message):
        spam = cookie = False
        for line in Checklist._lines(message):
            if '<:blank_box:' not in line:
                continue
            if any(k in line for k in ('<:box:', '<:crate:', '🌱', '⚔️')):
                spam = True
            if '<a:cookieeat:' in line:
                cookie = True
        return spam, cookie

    @staticmethod
    async def _claim(client, message):
        for button in Component.buttons(message):
            if button.custom_id in ('checklist:claim', 'weeklyChecklist:claim') and not button.disabled:
                try:
                    await button.click()
                    client.logger.info('Claimed checklist reward')
                except discord.HTTPException:
                    client.logger.warning('Failed to claim checklist reward')

    @staticmethod
    async def _switch_to_weekly(client, message):
        for button in Component.buttons(message):
            if button.custom_id == 'quest_tabs_weekly':
                try:
                    await button.click()
                    return True
                except discord.HTTPException:
                    client.logger.warning('Failed to switch to weekly tab')
                return False
        return False

    @staticmethod
    async def _fetch_weekly(client, message_id):
        for _ in range(5):
            await asyncio.sleep(2)
            try:
                message = await client.current_channel.fetch_message(message_id)
            except discord.HTTPException:
                continue
            if Checklist._has_header(message, client.user.mention, 'Weekly Checklist'):
                return message
        return None

    @staticmethod
    async def check(client):
        if not client.can_run() or not client.current_channel:
            return False
        await client.current_channel.send(f'{client.prefix}cl')
        client.logger.info(f'Sent {client.prefix}cl')

        try:
            message = await client.wait_for(
                'message',
                check=lambda m: (
                    client.is_owo_message(m, in_channel=True)
                    and Checklist._has_header(m, client.user.mention, 'Daily Checklist')
                ),
                timeout=5,
            )
        except asyncio.TimeoutError:
            client.logger.warning('Daily checklist fetch timeout')
            return False

        daily = Checklist.scan(message)
        client.cookie_available = bool(daily[1])
        client.logger.info(f'Cookie is {client.cookie_available}')
        await Checklist._claim(client, message)
        await asyncio.sleep(2)

        week = (False, False)
        if await Checklist._switch_to_weekly(client, message):
            message = await Checklist._fetch_weekly(client, message.id)
            if message is None:
                client.logger.warning('Weekly checklist fetch timeout')
                return False
            week = Checklist.scan(message)
            await Checklist._claim(client, message)

        client.checklist_spam = bool(daily[0] or week[0])
        client.logger.info(f'Checklist turn {'ON' if client.checklist_spam else 'OFF'} spam')
        return True

    @staticmethod
    def schedule(client):
        if client.checklist_spam:
            return random.randint(600, 1200)
        now = time.time()
        next_reset = now + Daily.reset_time(client.cooldown_reset)
        prev_reset = next_reset - 86400
        windows = [
            prev_reset - 7200 + random.randint(0, 3600),
            prev_reset + 3600 + random.randint(0, 3600),
            next_reset - 7200 + random.randint(0, 3600),
            next_reset + 3600 + random.randint(0, 3600),
        ]
        return int(min(w for w in windows if w > now) - now)