import asyncio
import re
import time
import datetime


class Daily:
    @staticmethod
    def reset_time(cooldown_reset=0):
        if cooldown_reset != 0:
            return cooldown_reset

        now = datetime.datetime.now(datetime.timezone.utc)
        reset = now.replace(hour=7, minute=0, second=0, microsecond=0)
        if now >= reset:
            reset += datetime.timedelta(days=1)

        return int((reset - now).total_seconds()) + 60

    @staticmethod
    async def claim(client):
        if not client.can_run():
            return
        if time.time() < client.cooldown_daily:
            return

        channel = client.current_channel
        if not channel:
            return

        await channel.send(f'{client.prefix}daily')
        client.logger.info(f'Sent {client.prefix}daily')

        try:
            message = await client.wait_for(
                'message',
                check=lambda m: (
                    client.is_owo_message(m, in_channel=True)
                    and client.message_contains(m.content, all_of=[str(client.nickname)])
                    and client.message_contains(m.content, any_of=['next daily', 'Nu'])
                ),
                timeout=5,
            )

            text = message.content.split('!')[-1].strip()
            hours_match = re.search(r'(\d+)H', text)
            minutes_match = re.search(r'(\d+)M', text)
            seconds_match = re.search(r'(\d+)S', text)
            hours = int(hours_match.group(1)) if hours_match else 0
            minutes = int(minutes_match.group(1)) if minutes_match else 0
            seconds = int(seconds_match.group(1)) if seconds_match else 0
            wait = hours * 3600 + minutes * 60 + seconds

            client.cooldown_reset = wait
            client.cooldown_daily = wait + time.time()

            if 'next daily' in message.content:
                client.logger.info(f'Claimed daily (next in {datetime.timedelta(seconds=wait)})')
            elif 'Nu' in message.content:
                client.logger.info(f'Daily not ready (wait {datetime.timedelta(seconds=wait)})')

        except asyncio.TimeoutError:
            client.logger.warning('Daily claim timeout')