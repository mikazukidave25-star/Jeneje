import asyncio
import random

import discord
from discord.components import Button, SelectMenu

from modules.utils.component import Component
from modules.utils.data_store import read_text
from modules.utils.logger import get_logger

logger = get_logger('command')

running = False

STAGGER_MIN = 0.5
STAGGER_MAX = 1.0
TYPING_MIN = 0.5
TYPING_MAX = 1.0


def read_entries():
    entries = []
    for raw in read_text('data/command.txt').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split()
        if len(parts) < 3:
            logger.warning('Skipping malformed line (need TOKEN owners prefixes)')
            continue
        try:
            owners = {int(item) for item in parts[1].split(',') if item}
        except ValueError:
            logger.warning('Skipping line with invalid owner id')
            continue
        prefixes = tuple(prefix for prefix in parts[2].split(',') if prefix)
        if owners and prefixes:
            entries.append({'token': parts[0], 'owners': owners, 'prefixes': prefixes})
        else:
            logger.warning('Skipping line without valid owners or prefixes')
    return entries


_active_ids = set()
_command_lock = None


class CommandClient(discord.Client):
    def __init__(self, entry):
        super().__init__()
        self.token = entry['token']
        self.owners = entry['owners']
        self.prefixes = entry['prefixes']
        self.logger = None

    async def on_ready(self):
        _active_ids.add(self.user.id)
        if not self.logger:
            self.logger = get_logger(self.user.name)
            self.logger.info(f'Ready | {len(self.owners)} owner(s) | prefixes: {" ".join(self.prefixes)}')
        for owner_id in self.owners:
            try:
                owner = self.get_user(owner_id) or await self.fetch_user(owner_id)
                await owner.create_dm()
            except Exception:
                self.logger.exception(f'Failed to open owner DM ({owner_id})')

    async def on_message(self, message):
        author_id = message.author.id
        if author_id in _active_ids or author_id not in self.owners:
            return

        prefix = next((p for p in (*self.prefixes, self.user.mention, f'<@{self.user.id}>')
                       if message.content.startswith(p)), None)
        if not prefix:
            return

        name, _, args = message.content[len(prefix):].strip().partition(' ')
        handler = HANDLERS.get(name.lower())
        if not handler:
            return

        async with _command_lock:
            try:
                await handler(self, message, args.strip())
                await asyncio.sleep(random.uniform(STAGGER_MIN, STAGGER_MAX))
            except Exception as exc:
                self.logger.warning(f'{name} failed: {exc}')


async def find_target(client, message, ref):
    ref = ref.strip()
    if not ref or ref == '.':
        async for msg in message.channel.history(limit=1):
            return msg
        raise ValueError('no recent message found')

    marker = '/channels/'
    if marker in ref:
        tail = ref.split(marker, 1)[1].split('/')
        channel_id, message_id = int(tail[-2]), int(tail[-1])
    elif ref.isdigit():
        async for msg in message.channel.history(limit=100):
            if str(msg.id) == ref:
                return msg
        raise ValueError('message id not found in recent history')
    else:
        left, sep, right = ref.rpartition('-')
        if not sep:
            raise ValueError('invalid target, use . / message id / jump link / channelID-messageID')
        channel_id, message_id = int(left), int(right)

    channel = client.get_channel(channel_id) or await client.fetch_channel(channel_id)
    return await channel.fetch_message(message_id)


def interactive(message):
    buttons, menus = [], []
    for node in Component.descendants(message):
        if isinstance(node, Button):
            buttons.append(node)
        elif isinstance(node, SelectMenu):
            menus.append(node)
    return buttons, menus


def pick(items, selector):
    if not items:
        raise ValueError('nothing to choose from')
    selector = selector.strip().lower()
    if selector.isdigit():
        index = int(selector) - 1
        if not 0 <= index < len(items):
            raise ValueError(f'index out of range ({len(items)} item(s))')
        return items[index]
    for item in items:
        keys = (str(getattr(item, 'label', '') or '').lower(),
                str(getattr(item, 'custom_id', '') or '').lower())
        if selector and selector in keys:
            return item
    return items[0]


async def _typing(channel):
    async with channel.typing():
        await asyncio.sleep(random.uniform(TYPING_MIN, TYPING_MAX))


async def cmd_say(client, message, args):
    head, sep, content = args.partition(' ')
    channel, text = message.channel, args
    if sep and head.isdigit():
        channel = client.get_channel(int(head)) or await client.fetch_channel(int(head))
        text = content
    if not text:
        raise ValueError('nothing to send')
    await _typing(channel)
    await channel.send(text)


async def cmd_reply(client, message, args):
    target, _, content = args.partition(' ')
    if not content:
        raise ValueError('nothing to send')
    ref = await find_target(client, message, target)
    await _typing(ref.channel)
    await ref.reply(content)


async def cmd_edit(client, message, args):
    target, _, content = args.partition(' ')
    ref = await find_target(client, message, target)
    if ref.author.id != client.user.id:
        raise ValueError('can only edit your own message')
    await ref.edit(content=content)


async def cmd_delete(client, message, args):
    ref = await find_target(client, message, args)
    if ref.author.id != client.user.id:
        raise ValueError('can only delete your own message')
    await ref.delete()


async def cmd_react(client, message, args):
    emoji, _, target = args.partition(' ')
    ref = await find_target(client, message, target)
    await ref.add_reaction(emoji)


async def cmd_unreact(client, message, args):
    emoji, _, target = args.partition(' ')
    ref = await find_target(client, message, target)
    await ref.remove_reaction(emoji, client.user)


async def cmd_click(client, message, args):
    target, _, selector = args.partition(' ')
    ref = await find_target(client, message, target)
    buttons, _ = interactive(ref)
    button = pick(buttons, selector)
    await button.click()
    client.logger.info(f'Clicked "{getattr(button, "label", None) or "button"}" on message {ref.id}')


async def cmd_select(client, message, args):
    target, _, rest = args.partition(' ')
    option_selector, _, menu_selector = rest.partition(' ')
    ref = await find_target(client, message, target)
    _, menus = interactive(ref)
    menu = pick(menus, menu_selector)
    option = pick(list(menu.options), option_selector)
    await menu.choose(option)
    client.logger.info(f'Selected "{getattr(option, "label", None) or option}" in menu {menu.placeholder or menu.custom_id}')


async def cmd_items(client, message, args):
    ref = await find_target(client, message, args)
    buttons, menus = interactive(ref)
    parts = []
    if buttons:
        parts.append('buttons: ' + ', '.join(
            f'{i}. {getattr(b, "label", None) or getattr(b, "custom_id", "")}'
            for i, b in enumerate(buttons, 1)))
    if menus:
        parts.append('menus: ' + ', '.join(
            f'{i}. {m.placeholder or m.custom_id} ({len(m.options)} option(s))'
            for i, m in enumerate(menus, 1)))
    await message.author.send(
        f'Message {ref.id}: ' + (' | '.join(parts) if parts else 'no interactive component'))


async def cmd_accounts(client, message, args):
    await message.author.send('Online')


HANDLERS = {
    'say': cmd_say,
    'reply': cmd_reply,
    'edit': cmd_edit,
    'delete': cmd_delete,
    'react': cmd_react,
    'unreact': cmd_unreact,
    'click': cmd_click,
    'select': cmd_select,
    'items': cmd_items,
    'accounts': cmd_accounts,
}


async def run_client(client):
    try:
        await client.start(client.token)
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.warning(f'{type(exc).__name__}: {exc}')
    finally:
        if not client.is_closed():
            try:
                await client.close()
            except Exception:
                pass


async def main():
    global running, _command_lock
    _command_lock = asyncio.Lock()
    entries = read_entries()
    if not entries:
        logger.warning('No command accounts configured')
        running = False
        return

    logger.info(f'Loaded {len(entries)} account(s)')
    tasks = [asyncio.create_task(run_client(CommandClient(entry))) for entry in entries]
    while running and any(not task.done() for task in tasks):
        await asyncio.sleep(0.5)

    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    _active_ids.clear()
    running = False