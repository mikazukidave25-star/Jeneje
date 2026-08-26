import asyncio
import collections
import random
import time

from modules.bots.owo.daily import Daily

FLAGS = {'pray': 'pray', 'curse': 'curse', 'battle': 'battle_friend', 'action': 'action_you', 'cookie': 'cookie'}

CD = {'pray': 300, 'curse': 300, 'battle': 15, 'action': 10}

class Interaction:
    def __init__(self, clients):
        self._clients = clients
        self._queue = collections.defaultdict(collections.deque)
        self._current = {}
        self._tasks = {}

    def ensure(self, kind):
        if kind in self._tasks:
            return

        if kind == 'action':
            task = self._worker_action()
        elif kind == 'cookie':
            task = self._worker_cookie()
        else:
            task = self._worker(kind)

        self._tasks[kind] = asyncio.create_task(task, name=f'owo-interaction-{kind}')

    def register(self, client, kind):
        queue = self._queue[kind]
        if client not in queue and self._current.get(kind) is not client:
            queue.append(client)
        self.ensure(kind)

    def unregister(self, client, kind):
        queue = self._queue.get(kind)
        if queue and client in queue:
            queue.remove(client)
        if self._current.get(kind) is client:
            self._advance(kind)

    def stop(self):
        for task in self._tasks.values():
            task.cancel()
        self._tasks.clear()

    def reset(self):
        self.stop()
        self._queue.clear()
        self._current.clear()

    def _needs(self, client, kind):
        return client.quest_flags.get(FLAGS[kind])

    def _advance(self, kind):
        self._current[kind] = None
        if kind == 'battle':
            for client in self._clients:
                client.block_battle = False

    async def _pick(self, kind):
        while True:
            queue = self._queue.get(kind)
            if queue:
                queue.rotate(-random.randrange(len(queue)))
                target = queue.popleft()
                self._current[kind] = target
                if kind == 'battle':
                    target.block_battle = True
                    for sender in self._clients:
                        if sender is not target:
                            sender.block_battle = True
                return
            await asyncio.sleep(5)

    def _ready(self, sender, kind):
        return time.time() >= sender.interaction_cd.get(kind, 0)

    def _mark(self, sender, kind):
        sender.interaction_cd[kind] = time.time() + CD[kind]

    def _command(self, kind, sender, target):
        if kind == 'battle':
            return f'{sender.prefix}b {target.user.mention}'
        return f'{sender.prefix}{kind} {target.user.id}'

    async def _notice(self, sender):
        try:
            await sender.wait_for(
                'message',
                check=lambda m: (
                    sender.is_owo_message(m, in_channel=True)
                    and sender.message_contains(m.content, any_of=['You need to wait', 'You got a cookie'])
                ),
                timeout=5,
            )
        except asyncio.TimeoutError:
            pass

    async def _cycle(self, kind, target):
        for sender in self._clients:
            if sender is target or not sender.can_run():
                continue
            if not sender.current_channel:
                continue
            if kind == 'cookie':
                if not time.time() >= sender.cookie_cooldown:
                    continue
            elif not self._ready(sender, kind):
                continue
            command = self._command(kind, sender, target)
            await sender.current_channel.send(command)
            sender.logger.info(f'Sent {command}')
            self._mark(sender, kind)
            if kind == 'cookie':
                sender.cookie_cooldown = time.time() + Daily.reset_time(sender.cooldown_reset)
                await self._notice(sender)
            await asyncio.sleep(random.uniform(2, 5))

    async def _worker(self, kind):
        try:
            while True:
                target = self._current.get(kind)
                if target is None:
                    await self._pick(kind)
                    continue
                if not self._needs(target, kind):
                    self._advance(kind)
                    await asyncio.sleep(1)
                    continue
                await self._cycle(kind, target)
                await asyncio.sleep(random.uniform(2, 5))
        except asyncio.CancelledError:
            pass

    async def _worker_action(self):
        try:
            while True:
                target = self._current.get('action')
                if target is not None and not self._needs(target, 'action'):
                    self._advance('action')
                    continue
                if target is None and self._queue.get('action'):
                    target = self._queue['action'].popleft()
                    self._current['action'] = target
                if target is not None:
                    senders = [c for c in self._clients if c.quest_flags.get('action_someone') and c.can_run()]
                    senders = senders or [c for c in self._clients if c is not target and c.can_run()]
                else:
                    senders = [c for c in self._clients if c.quest_flags.get('action_someone') and c.can_run()]
                if not senders:
                    await asyncio.sleep(5)
                    continue
                for sender in list(senders):
                    if not sender.can_run() or not self._ready(sender, 'action'):
                        continue
                    if not sender.current_channel:
                        continue
                    subject = target.user if target is not None else sender.owo_bot
                    if subject is None:
                        continue
                    command = f'{sender.prefix}{random.choice(sender.owo_actions)} {subject.mention}'
                    await sender.current_channel.send(command)
                    sender.logger.info(f'Sent {command}')
                    self._mark(sender, 'action')
                    await asyncio.sleep(random.uniform(2, 5))
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

    async def _worker_cookie(self):
        try:
            while True:
                senders = [c for c in self._clients if c.can_run() and time.time() >= c.cookie_cooldown]
                pending = [c for c in self._clients if self._needs(c, 'cookie')]
                unfetched = [c for c in self._clients if c.config['quest'] and not c.quest_fetched]
                checklist = any(c.cookie_available for c in self._clients)
                if pending or (checklist and not unfetched):
                    if not senders:
                        client = next((c for c in self._clients if c is not None), None)
                        wait = Daily.reset_time(client.cooldown_reset if client else 0)
                        await asyncio.sleep(wait)
                        continue
                    for sender in list(senders):
                        if not sender.can_run() or not time.time() >= sender.cookie_cooldown:
                            continue
                        if not sender.current_channel:
                            continue
                        helpers = [c for c in pending if c is not sender]
                        if not sender.cookie_available and not helpers:
                            continue
                        partners = helpers or \
                                   [c for c in self._clients if c is not sender and c.can_run()]
                        if not partners:
                            continue
                        partner = random.choice(partners)
                        command = f'{sender.prefix}cookie {partner.user.id}'
                        await sender.current_channel.send(command)
                        sender.logger.info(f'Sent {command}')
                        sender.cookie_cooldown = time.time() + Daily.reset_time(sender.cooldown_reset)
                        await self._notice(sender)
                        await asyncio.sleep(random.uniform(2, 5))
                    await asyncio.sleep(30)
                else:
                    await asyncio.sleep(30)
        except asyncio.CancelledError:
            pass