import asyncio
import random
import re
import time
import datetime

from modules.bots.owo.daily import Daily


class Gem:
    @staticmethod
    async def _send_use(client, gem_to_use):
        if not gem_to_use:
            client.no_gem = True
            wait = Daily.reset_time(client.cooldown_reset)
            client.no_gem_since = wait + time.time()
            client.logger.info(f'No gem available, retry in {datetime.timedelta(seconds=wait)}')
            return
        if not client.can_run() or not client.current_channel:
            return
        await client.current_channel.send(f'{client.prefix}use {gem_to_use}')
        client.logger.info(f'Sent {client.prefix}use {gem_to_use}')
        try:
            await client.wait_for(
                'message',
                check=lambda message: (
                    client.is_owo_message(message, in_channel=True)
                    and client.message_contains(message.content, all_of=[str(client.nickname), 'active Special gem or you do not own'])
                ),
                timeout=5,
            )
            client.special_pet_available = False
        except asyncio.TimeoutError:
            pass

    @staticmethod
    async def _couple_gem(client, gem):
        inv = await Gem.get_inventory(client)
        if not inv:
            return
        gem_tiers = {
            'gem1': range(51, 58),
            'gem3': range(65, 72),
            'gem4': range(72, 79),
        }
        if gem['star'] and client.special_pet_available:
            gem_tiers['star'] = range(79, 86)
        start_values = {
            'gem1': 51,
            'gem3': 65,
            'gem4': 72,
            'star': 79,
        }
        active = [tier for tier in gem_tiers if tier in start_values]
        max_n = min(gem_tiers[tier].stop - start_values[tier] for tier in active)
        valid = [
            [start_values[tier] + n for tier in active]
            for n in range(max_n)
            if all((start_values[tier] + n) in inv and (start_values[tier] + n) in gem_tiers[tier] for tier in active)
        ]
        selected = valid[-1] if valid and gem['best'] else (valid[0] if valid else [])
        gem_to_use = ' '.join(map(str, selected)) if selected else None
        await Gem._send_use(client, gem_to_use)

    @staticmethod
    async def _single_gem(client, gem, empty_gem):
        inv = await Gem.get_inventory(client)
        if not inv:
            return
        gem_tiers = {}
        if 'gem1' in empty_gem:
            gem_tiers['gem1'] = range(51, 58)
        if 'gem3' in empty_gem:
            gem_tiers['gem3'] = range(65, 72)
        if 'gem4' in empty_gem:
            gem_tiers['gem4'] = range(72, 79)
        if 'star' in empty_gem and gem['star'] and client.special_pet_available:
            gem_tiers['star'] = range(79, 86)
        selected = [
            (max if gem['best'] else min)([candidate for candidate in inv if candidate in tier], default=None)
            for tier in gem_tiers.values()
        ]
        gem_to_use = ' '.join(str(gem_value) for gem_value in selected if gem_value is not None)
        await Gem._send_use(client, gem_to_use)

    @staticmethod
    async def check_gem(client, message):
        if not client.can_run():
            return
        if not client.is_owo_message(message, in_channel=True):
            return
        if not client.message_contains(message.content, all_of=[str(client.nickname), '🌱', 'gained']):
            return

        if client.no_gem and time.time() < client.no_gem_since:
            return

        client.no_gem = False
        gem = client.config['gem']
        await asyncio.sleep(5)

        if gem['couple']:
            if 'spent 5 <:cowoncy:416043450337853441> and caught a' in message.content:
                await Gem._couple_gem(client, gem)
            return

        inventory = client.inventory_str
        empty_gem = []
        if 'gem1' not in message.content and 'gem1' in inventory:
            empty_gem.append('gem1')
        if 'gem3' not in message.content and 'gem3' in inventory:
            empty_gem.append('gem3')
        if 'gem4' not in message.content and 'gem4' in inventory:
            empty_gem.append('gem4')
        if 'star' not in message.content and 'star' in inventory and gem['star'] and client.special_pet_available:
            empty_gem.append('star')
        if not empty_gem:
            return
        await Gem._single_gem(client, gem, empty_gem)

    @staticmethod
    async def get_inventory(client):
        if not client.can_run() or not client.current_channel:
            return []
        await client.current_channel.send(f'{client.prefix}inv')
        client.logger.info(f'Sent {client.prefix}inv')
        try:
            message = await client.wait_for(
                'message',
                check=lambda message: (
                    client.is_owo_message(message, in_channel=True)
                    and f"{client.nickname}'s Inventory" in message.content
                ),
                timeout=5,
            )
            client.inventory_str = message.content
            inv = [int(item) for item in re.findall(r'`(.*?)`', message.content) if item.isnumeric()]
            await Gem._open_items(client, inv)
            return inv
        except asyncio.TimeoutError:
            client.logger.warning("Couldn't get inventory")
            return []

    @staticmethod
    async def _open_items(client, inv):
        if not client.can_run() or not client.current_channel:
            return
        opening = client.config['gem']['openning']
        if opening['box'] and 50 in inv and client.can_run():
            await client.current_channel.send(f'{client.prefix}lb all')
            client.logger.info(f'Sent {client.prefix}lb all')
            await asyncio.sleep(2)
        if opening['crate'] and 100 in inv and client.can_run():
            await client.current_channel.send(f'{client.prefix}wc all')
            client.logger.info(f'Sent {client.prefix}wc all')
            await asyncio.sleep(2)
        if opening['flootbox'] and 49 in inv and client.can_run():
            await client.current_channel.send(f'{client.prefix}lb f')
            client.logger.info(f'Sent {client.prefix}lb f')
        await asyncio.sleep(2)

    @staticmethod
    def glitch_available(client):
        return client.config['gem']['glitch'] and client.cooldown_glitch > time.time()

    @staticmethod
    async def check_glitch(client):
        if not client.can_run() or not client.current_channel:
            return
        if client.cooldown_glitch > time.time():
            return
        await client.current_channel.send(f'{client.prefix}dt')
        client.logger.info(f'Sent {client.prefix}dt')
        try:
            message = await client.wait_for(
                'message',
                check=lambda message: (
                    client.is_owo_message(message, in_channel=True)
                    and client.message_contains(message.content, any_of=['are available', 'not available'])
                ),
                timeout=5,
            )
            if 'are available' in message.content:
                parts = re.findall(r'\*\*(.*?)\*\*', message.content)
                glitch_end = re.findall('[0-9]+', parts[2]) if len(parts) >= 3 else []
                if len(glitch_end) == 1:
                    duration = int(glitch_end[0])
                elif len(glitch_end) == 2:
                    duration = int(int(glitch_end[0]) * 60 + int(glitch_end[1]))
                elif len(glitch_end) == 3:
                    duration = int(int(glitch_end[0]) * 3600 + int(glitch_end[1]) * 60 + int(glitch_end[2]))
                else:
                    duration = 600
                client.cooldown_glitch = duration + time.time()
                client.logger.info(f'Glitch is available for {datetime.timedelta(seconds=duration)}')
            elif 'not available' in message.content:
                wait = random.randint(600, 1200)
                client.logger.info(f"Glitch isn't available, retry in {datetime.timedelta(seconds=wait)}")
                await asyncio.sleep(wait)
        except asyncio.TimeoutError:
            client.logger.warning("Couldn't get glitch message")