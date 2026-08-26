import random
import asyncio


class Spam:
    @staticmethod
    async def send_owo(client):
        if not client.can_run() or not client.current_channel:
            return
        say = random.choice(['owo', 'uwu'])
        await client.current_channel.send(say)
        client.logger.info(f'Sent {say}')

    @staticmethod
    async def send_hunt(client):
        if not client.can_run() or not client.current_channel:
            return
        await client.current_channel.send(f'{client.prefix}h')
        client.logger.info(f'Sent {client.prefix}h')

    @staticmethod
    async def send_battle(client):
        if not client.can_run() or not client.current_channel:
            return
        if client.block_battle:
            return
        await client.current_channel.send(f'{client.prefix}b')
        client.logger.info(f'Sent {client.prefix}b')

    @staticmethod
    async def spam_cycle(client):
        spam = client.config['spam']
        delay_min = float(spam['delay']['min'])
        delay_max = float(spam['delay']['max'])

        try:
            if spam['owo/uwu'] or client.checklist_spam or client.quest_flags.get('owo'):
                await Spam.send_owo(client)
                await asyncio.sleep(random.uniform(delay_min, delay_max))
            if spam['hunt'] or client.checklist_spam or client.quest_flags.get('hunt'):
                await Spam.send_hunt(client)
                await asyncio.sleep(random.uniform(delay_min, delay_max))
            if spam['battle'] or client.checklist_spam or client.quest_flags.get('battle'):
                await Spam.send_battle(client)
                await asyncio.sleep(random.uniform(delay_min, delay_max))
        except Exception:
            client.logger.exception('Spam error')