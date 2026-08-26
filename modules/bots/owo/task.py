import asyncio
import datetime
import random
import time

from modules.bots.owo.checklist import Checklist
from modules.bots.owo.quest import Quest
from modules.bots.owo.vote import Vote
from modules.bots.owo.daily import Daily
from modules.bots.owo.huntbot import Huntbot
from modules.bots.owo.spam import Spam
from modules.bots.owo.gem import Gem
from modules.bots.owo.gamble import Gamble
from modules.bots.owo.channel import Channel


class TaskManager:
    def __init__(self, client):
        self.client = client
        self._tasks = []
        self._running = False


    async def start(self):
        if self._running:
            return
        self._running = True

        if self.client.config['quest'] and self.client.interaction:
            self.client.interaction.ensure('cookie')

        todo = []
        if self.client.config['channels_id'] and len(self.client.config['channels_id']) > 1:
            todo.append(self._loop_channel)
        if self.client.config['checklist']:
            todo.append(self._loop_checklist)
        if self.client.config['quest']:
            todo.append(self._loop_quest)
        if self.client.config['vote']:
            todo.append(self._loop_vote)
        if self.client.config['daily']:
            todo.append(self._loop_daily)
        if self.client.config['huntbot']:
            todo.append(self._loop_huntbot)
        spam = self.client.config['spam']
        if self.client.config['quest'] or spam['hunt'] or spam['battle'] or spam['owo/uwu']:
            todo.append(self._loop_spam)
        if self.client.config['gem']['glitch']:
            todo.append(self._loop_glitch)
        gamble = self.client.config['gamble']
        if (
            self.client.config['quest']
            or gamble['lottery']['mode'] or gamble['slot']['mode']
            or gamble['coinflip']['mode'] or gamble['blackjack']['mode']
            or gamble['highlow']['mode']
        ):
            todo.append(self._loop_gamble)
        if self.client.config['check_status']:
            todo.append(self._loop_offline_check)

        for coro_func in todo:
            await asyncio.sleep(random.uniform(5, 10))
            self._tasks.append(asyncio.create_task(coro_func()))

        self.client.logger.info('All tasks started')

    def create_background(self, coro, name=None):
        task = asyncio.create_task(coro, name=name)
        self._tasks.append(task)
        return task

    async def stop(self):
        self._running = False
        for task in self._tasks:
            if not task.done():
                task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        self.client.logger.info('All tasks stopped')

    async def _loop_channel(self):
        try:
            while self._running:
                channels = self.client.config['channels_id']
                if self.client.can_run() and len(channels) > 1:
                    changing_channel = self.client.config['changing_channel']
                    cooldown = random.randint(int(changing_channel['after_elapsed_time']['min']), int(changing_channel['after_elapsed_time']['max']))
                    self.client.logger.info(f'Next channel change in {datetime.timedelta(seconds=cooldown)}')
                    await asyncio.sleep(cooldown)
                    try:
                        await Channel.change_channel(self.client)
                    except Exception:
                        self.client.logger.exception('Channel change error')
                else:
                    await asyncio.sleep(random.uniform(30, 60))
        except asyncio.CancelledError:
            pass

    async def _loop_checklist(self):
        try:
            while self._running:
                if self.client.can_run():
                    try:
                        if await Checklist.check(self.client):
                            wait = Checklist.schedule(self.client)
                            self.client.logger.info(f'Next checklist check in {datetime.timedelta(seconds=wait)}')
                            await asyncio.sleep(wait)
                    except Exception:
                        self.client.logger.exception('Checklist error')
                await asyncio.sleep(random.uniform(30, 60))
        except asyncio.CancelledError:
            pass

    async def _loop_quest(self):
        try:
            while self._running:
                if self.client.can_run():
                    try:
                        await Quest.do_quest(self.client)
                    except Exception:
                        self.client.logger.exception('Quest error')
                await asyncio.sleep(random.uniform(30, 60))
        except asyncio.CancelledError:
            pass

    async def _loop_vote(self):
        try:
            while self._running:
                if self.client.can_run():
                    try:
                        await Vote.vote(self.client)
                    except Exception:
                        self.client.logger.exception('Vote error')
                await asyncio.sleep(random.uniform(30, 60))
        except asyncio.CancelledError:
            pass

    async def _loop_daily(self):
        try:
            while self._running:
                if self.client.can_run():
                    try:
                        await Daily.claim(self.client)
                    except Exception:
                        self.client.logger.exception('Daily error')
                await asyncio.sleep(random.uniform(30, 60))
        except asyncio.CancelledError:
            pass

    async def _loop_huntbot(self):
        try:
            while self._running:
                if self.client.can_run():
                    try:
                        await Huntbot.claim_submit(self.client)
                    except Exception:
                        self.client.logger.exception('Huntbot error')
                await asyncio.sleep(random.uniform(30, 60))
        except asyncio.CancelledError:
            pass

    async def _loop_spam(self):
        try:
            while self._running:
                if self.client.can_run():
                    try:
                        await Spam.spam_cycle(self.client)
                    except Exception:
                        self.client.logger.exception('Spam error')
                    spam = self.client.config['spam']
                    await asyncio.sleep(random.uniform(int(spam['cooldown']['min']), int(spam['cooldown']['max'])))
                else:
                    await asyncio.sleep(random.uniform(30, 60))
        except asyncio.CancelledError:
            pass

    async def _loop_glitch(self):
        try:
            while self._running:
                if self.client.can_run():
                    try:
                        await Gem.check_glitch(self.client)
                    except Exception:
                        self.client.logger.exception('Glitch error')
                await asyncio.sleep(random.uniform(30, 60))
        except asyncio.CancelledError:
            pass

    async def _loop_gamble(self):
        try:
            while self._running:
                if self.client.can_run():
                    gamble = self.client.config['gamble']
                    try:
                        await Gamble.gamble_cycle(self.client)
                    except Exception:
                        self.client.logger.exception('Gamble error')
                    await asyncio.sleep(random.uniform(int(gamble['cooldown']['min']), int(gamble['cooldown']['max'])))
                else:
                    await asyncio.sleep(random.uniform(30, 60))
        except asyncio.CancelledError:
            pass

    async def _loop_offline_check(self):
        try:
            while self._running:
                if self.client.can_run():
                    if time.time() - self.client.last_owo_message_time > 60:
                        try:
                            await self._check_owo_alive()
                        except Exception:
                            self.client.logger.exception('Offline check error')
                await asyncio.sleep(random.uniform(30, 60))
        except asyncio.CancelledError:
            pass

    async def _check_owo_alive(self):
        if not self.client.current_channel:
            return

        action = random.choice(self.client.owo_actions)
        await self.client.current_channel.send(f'{self.client.prefix}{action} {self.client.owo_bot.mention}')
        self.client.logger.info(f'Offline check: sent {self.client.prefix}{action} {self.client.owo_bot.mention}')

        try:
            await self.client.wait_for(
                'message',
                check=lambda m: m.author.id == self.client.owo_bot.id,
                timeout=5,
            )
            self.client.logger.info('OWO bot is online')
        except asyncio.TimeoutError:
            wait = random.randint(300, 600)
            self.client.logger.warning(f'OWO bot is offline, pausing for {datetime.timedelta(seconds=wait)}')
            self.client.paused = True
            await asyncio.sleep(wait)
            self.client.paused = False
            self.client.logger.info('Resuming after offline pause')